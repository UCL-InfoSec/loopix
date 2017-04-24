from client_core import ClientCore
from sphinxmix.SphinxParams import SphinxParams
import random
from Queue import Queue
import time
from processQueue import ProcessQueue
import supportFunctions as sf
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, defer
import numpy

class LoopixClient(DatagramProtocol):
    EXP_PARAMS_LOOPS = 2.0
    EXP_PARAMS_DROP = 2.0
    EXP_PARAMS_PAYLOAD = 2.0
    EXP_PARAMS_DELAY = 2.0

    def __init__(self, name, port, host, privk = None, pubk=None):
        self.name = name
        self.port = port
        self.host = host

        params = SphinxParams(header_len=1024)
        gr_order = params.group.G.order()
        gr_generator = params.group.G.generator()

        self.privk = privk or gr_order.random()
        self.pubk = pubk or (self.privk * gr_generator)
        self.core = ClientCore(params, self.name, self.port, self.host, self.privk, self.pubk)

        self.buffer = Queue()
        self.process_queue = ProcessQueue()

        self.reactor = reactor

    def startProtocol(self):
        print "[%s] > Started" % self.name

    def stopProtocol(self):
        print "[%s] > Stopped" % self.name

    def register_mixnodes(self, mixes):
        self.mixes = mixes

    def register_providers(self, providers):
        self.providers = providers

    def register_friends(self, clients):
        self.befriended_clients = clients

    def assign_provider(self, provider):
        self.provider = provider

    def datagramReceived(self, data, (host, port)):
        self.process_queue.put((data, (host, port)))

    def process_packet(self, packet):
        return self.core.process_packet(packet)

    def send(self, packet):
        self.transport.write(packet, (self.provider.host, self.provider.port))

    def schedule_next_call(self, param, method):
        interval = self.sampleFromExponential(param)
        print interval
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
        header, body = self.core.create_drop_message(random_receiver.core, path)
        self.send((header, body))

    def make_real_stream(self):
        if not self.buffer.empty():
            packet, addr = self.buffer.get()
            self.send(packet)
        else:
            self.send_drop_message()
        self.schedule_next_call(self.EXP_PARAMS_PAYLOAD, self.make_real_stream)

    def construct_full_path(self, receiver):
        mix_chain = self.take_random_mix_chain()
        return [self.provider] + mix_chain + [receiver.provider] + [receiver]

    def take_random_mix_chain(self, length = 3):
        return self.mixes

    def sampleFromExponential(self, lambdaParam):
        return numpy.random.exponential(lambdaParam, size=None)
