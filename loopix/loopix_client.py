from Queue import Queue
import random
import os
import petlib.pack
from processQueue import ProcessQueue
from client_core import ClientCore
from core import sample_from_exponential, group_layered_topology
from database_connect import DatabaseManager
from support_formats import Provider
from json_reader import JSONReader
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, task, abstract
from twisted.python import log

import twisted.names.client


class LoopixClient(DatagramProtocol):
    jsonReader = JSONReader(os.path.join(os.path.dirname(__file__), 'config.json'))
    config_params = jsonReader.get_client_config_params()
    output_buffer = Queue()
    process_queue = ProcessQueue()
    reactor = reactor
    resolvedAdrs = {}

    def __init__(self, sec_params, name, port, host, provider_id, privk=None, pubk=None):
        self.name = name
        self.port = port
        self.host = host
        self.privk = privk or sec_params.group.G.order().random()
        self.pubk = pubk or (self.privk * sec_params.group.G.generator())
        self.crypto_client = ClientCore((sec_params, self.config_params), self.name,
                                        self.port, self.host, self.privk, self.pubk)
        self.provider = Provider(name=provider_id)


    def startProtocol(self):
        log.msg("[%s] > Started" % self.name)
        self.get_network_info()
        self.get_provider_data()
        self.subscribe_to_provider()
        self.turn_on_packet_processing()
        self.make_loop_stream()
        self.make_drop_stream()
        self.make_real_stream()

    def get_network_info(self):
        self.dbManager = DatabaseManager(self.config_params.DATABASE_NAME)
        self.register_mixes(self.dbManager.select_all_mixnodes())
        self.register_providers(self.dbManager.select_all_providers())
        self.register_friends(self.dbManager.select_all_clients())
        self.provider = self.dbManager.select_provider_by_name(self.provider.name)
        log.msg("[%s] > Registered network information" % self.name)

    def get_provider_data(self):
        self.provider = self.dbManager.select_provider_by_name(self.provider.name)
        d = twisted.names.client.getHostByName(self.provider.host)
        d.addCallback(self.resolve_provider_address)

    def resolve_provider_address(self, result):
        self.provider = self.provider._replace(host = result)

    def subscribe_to_provider(self):
        lc = task.LoopingCall(self.send, ['SUBSCRIBE', self.name, self.host, self.port])
        lc.start(self.config_params.TIME_PULL, now=True)

    def register_mixes(self, mixes):
        self.pubs_mixes = group_layered_topology(mixes)

    def register_providers(self, providers):
        self.pubs_providers = providers

    def register_friends(self, clients):
        self.befriended_clients = clients

    def turn_on_packet_processing(self):
        self.retrieve_messages()
        self.reactor.callLater(20.0, self.get_and_addCallback, self.handle_packet)
        log.msg("[%s] > Turned on retrieving and processing of messages" % self.name)

    def retrieve_messages(self):
        lc = task.LoopingCall(self.send, ['PULL', self.name])
        lc.start(self.config_params.TIME_PULL, now=True)

    def get_and_addCallback(self, function):
        self.process_queue.get().addCallback(function)

    def datagramReceived(self, data, (host, port)):
        self.process_queue.put(data)

    def handle_packet(self, packet):
        self.read_packet(packet)
        try:
            self.reactor.callFromThread(self.get_and_addCallback, self.handle_packet)
        except Exception, exp:
            log.err("[%s] > Exception during scheduling next get: %s" % (self.name, str(exp)))

    def read_packet(self, packet):
        decoded_packet = petlib.pack.decode(packet)
        if not decoded_packet[0] == 'DUMMY':
            flag, decrypted_packet = self.crypto_client.process_packet(decoded_packet)
            return (flag, decrypted_packet)

    def send_message(self, message, receiver):
        path = self.construct_full_path(receiver)
        header, body = self.crypto_client.pack_real_message(message, receiver, path)
        self.send((header, body))

    def send(self, packet):
        encoded_packet = petlib.pack.encode(packet)
        if abstract.isIPAddress(self.provider.host):
            self.transport.write(encoded_packet, (self.provider.host, self.provider.port))

    def schedule_next_call(self, param, method):
        interval = sample_from_exponential(param)
        self.reactor.callLater(interval, method)

    def make_loop_stream(self):
        log.msg("[%s] > Sending loop packet." % self.name)
        self.send_loop_message()
        self.schedule_next_call(self.config_params.EXP_PARAMS_LOOPS, self.make_loop_stream)

    def send_loop_message(self):
        path = self.construct_full_path(self)
        header, body = self.crypto_client.create_loop_message(path)
        self.send((header, body))

    def make_drop_stream(self):
        log.msg("[%s] > Sending drop packet." % self.name)
        self.send_drop_message()
        self.schedule_next_call(self.config_params.EXP_PARAMS_DROP, self.make_drop_stream)

    def send_drop_message(self):
        random_receiver = random.choice(self.befriended_clients)
        path = self.construct_full_path(random_receiver)
        header, body = self.crypto_client.create_drop_message(random_receiver, path)
        self.send((header, body))

    def make_real_stream(self):
        if not self.output_buffer.empty():
            log.msg("[%s] > Sending message from buffer." % self.name)
            packet = self.output_buffer.get()
            self.send(packet)
        else:
            log.msg("[%s] > Sending substituting drop message." % self.name)
            self.send_drop_message()
        self.schedule_next_call(self.config_params.EXP_PARAMS_PAYLOAD, self.make_real_stream)

    def construct_full_path(self, receiver):
        mix_chain = self.take_random_mix_chain()
        return [self.provider] + mix_chain + [receiver.provider] + [receiver]

    def take_random_mix_chain(self):
        mix_chain = []
        num_all_layers = len(self.pubs_mixes)
        for i in range(num_all_layers):
            mix = random.choice(self.pubs_mixes[i])
            mix_chain.append(mix)
        return mix_chain

    def stopProtocol(self):
        log.msg("[%s] > Stopped" % self.name)
