from client_core import ClientCore
from sphinxmix.SphinxParams import SphinxParams
import random
from Queue import Queue
import time
from processQueue import ProcessQueue
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, defer, task
import numpy
from core import get_group_characteristics, sample_from_exponential
import petlib.pack
from databaseConnect import DatabaseManager
from format3 import Provider, Params
from core import make_sphinx_packet

class LoopixClient(DatagramProtocol):
    EXP_PARAMS_LOOPS = 2.0
    EXP_PARAMS_DROP = 2.0
    EXP_PARAMS_PAYLOAD = 2.0
    EXP_PARAMS_DELAY = 2.0
    DATABASE_NAME = 'example.db'
    TIME_PULL = 60.0

    def __init__(self, name, port, host, providerInfo, privk = None, pubk=None):
        self.name = name
        self.port = port
        self.host = host
        self.provider = Provider(*providerInfo)

        params = SphinxParams(header_len=1024)
        order, generator = get_group_characteristics(params)
        self.privk = privk or order.random()
        self.pubk = pubk or (self.privk * generator)
        self.core = ClientCore(params, self.name, self.port, self.host, self.privk, self.pubk)

        self.output_buffer = Queue()
        self.process_queue = ProcessQueue()
        self.reactor = reactor

    def startProtocol(self):
        print "[%s] > Started" % self.name
        self.subscribe_to_provider()
        self.get_network_info()
        self.turn_on_processing()

    def subscribe_to_provider(self):
        ping_packet = 'PING%s'%self.name
        self.send(ping_packet)

    def get_network_info(self):
        self.dbManager = DatabaseManager(self.DATABASE_NAME)
        mixes = self.dbManager.select_all_mixnodes()
        providers = self.dbManager.select_all_providers()
        clients = self.dbManager.select_all_clients()
        self.register_mixes(mixes)
        self.register_providers(providers)
        self.register_friends(clients)

    def register_mixes(self, mixes):
        self.mixes = mixes

    def register_providers(self, providers):
        self.providers = providers

    def register_friends(self, clients):
        self.befriended_clients = clients

    def turn_on_processing(self):
        self.retrieve_messages()
        self.reactor.callLater(20.0, self.get_and_addCallback, self.process_packet)

    def retrieve_messages(self):
        lc = task.LoopingCall(self.send, 'PULL%s' % self.name)
        lc.start(self.TIME_PULL, now=True)

    def get_and_addCallback(self, f):
        self.process_queue.get().addCallback(f)

    def datagramReceived(self, data, (host, port)):
        self.process_queue.put((data, (host, port)))

    def process_packet(self, packet):
        self.read_packet(packet)
        try:
            self.reactor.callFromThread(self.get_and_addCallback, self.process_packet)
        except Exception, e:
            print "[%s] > Exception during scheduling next get: %s" % (self.name, str(e))

    def read_packet(self, packet):
        return self.core.process_packet(packet)

    def send(self, packet):
        encoded_packet = petlib.pack.encode(packet)
        self.transport.write(encoded_packet, (self.provider.host, self.provider.port))

    def schedule_next_call(self, param, method):
        interval = sample_from_exponential(param)
        self.reactor.callLater(interval, method)

    def make_loop_stream(self):
        self.send_loop_message()
        self.schedule_next_call(self.EXP_PARAMS_LOOPS, self.make_loop_stream)

    def send_loop_message(self):
        path = self.construct_full_path(self)
        header, body = self.core.create_loop_message(path)
        self.send((header, body))

    def make_drop_stream(self):
        self.send_drop_message()
        self.schedule_next_call(self.EXP_PARAMS_DROP, self.make_drop_stream)

    def send_drop_message(self):
        random_receiver = random.choice(self.befriended_clients)
        path = self.construct_full_path(random_receiver)
        header, body = self.core.create_drop_message(random_receiver, path)
        self.send((header, body))

    def make_real_stream(self):
        if not self.output_buffer.empty():
            packet = self.output_buffer.get()
            self.send(packet)
        else:
            self.send_drop_message()
        self.schedule_next_call(self.EXP_PARAMS_PAYLOAD, self.make_real_stream)

    def construct_full_path(self, receiver):
        mix_chain = self.take_random_mix_chain()
        return [self.provider] + mix_chain + [receiver.provider] + [receiver]

    def take_random_mix_chain(self, length = 3):
        return self.mixes

    def stopProtocol(self):
        print "[%s] > Stopped" % self.name
