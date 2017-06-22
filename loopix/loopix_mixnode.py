import random
import os
import petlib.pack
from mix_core import MixCore
from processQueue import ProcessQueue
from core import sample_from_exponential, group_layered_topology
from database_connect import DatabaseManager
from json_reader import JSONReader
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, abstract

class LoopixMixNode(DatagramProtocol):
    jsonReader = JSONReader(os.path.join(os.path.dirname(__file__), 'config.json'))
    config_params = jsonReader.get_mixnode_config_params()
    reactor = reactor
    process_queue = ProcessQueue()
    resolvedAdrs = {}

    def __init__(self, sec_params, name, port, host, group, privk=None, pubk=None):
        self.name = name
        self.port = port
        self.host = host
        self.group = group

        self.privk = privk or sec_params.group.G.order().random()
        self.pubk = pubk or (self.privk * sec_params.group.G.generator())
        self.crypto_node = MixCore((sec_params, self.config_params),
                                   self.name, self.port, self.host, self.privk, self.pubk)

    def startProtocol(self):
        print "[%s] > Started" % self.name
        self.get_network_info()
        self.turn_on_processing()
        self.make_loop_stream()

    def get_network_info(self):
        self.dbManager = DatabaseManager(self.config_params.DATABASE_NAME)
        mixes = self.dbManager.select_all_mixnodes()
        providers = self.dbManager.select_all_providers()
        self.register_mixes([m for m in mixes if not m.name == self.name])
        self.register_providers([p for p in providers if not p.name == self.name])

    def register_mixes(self, mixes):
        self.pubs_mixes = group_layered_topology(mixes)

    def register_providers(self, providers):
        self.pubs_providers = providers

    def turn_on_processing(self):
        self.reactor.callLater(20.0, self.get_and_addCallback, self.handle_packet)

    def get_and_addCallback(self, function):
        self.process_queue.get().addCallback(function)

    def make_loop_stream(self):
        self.send_loop_message()
        self.schedule_next_call(self.config_params.EXP_PARAMS_LOOPS, self.make_loop_stream)

    def send_loop_message(self):
        path = self.generate_random_path()
        packet = self.crypto_node.create_loop_message(path)
        addr = (path[0].host, path[0].port)
        self.send(packet, addr)

    def generate_random_path(self):
        return self.construct_full_path()

    def construct_full_path(self):
        sequence = []
        num_all_layers = len(self.pubs_mixes)
        layer = self.group + 1
        while layer != self.group:
            mix = random.choice(self.pubs_mixes[layer % num_all_layers])
            sequence.append(mix)
            layer = (layer + 1) % num_all_layers
        sequence.insert(num_all_layers - 1 - self.group, random.choice(self.pubs_providers))
        return sequence

    def schedule_next_call(self, param, method):
        interval = sample_from_exponential(param)
        self.reactor.callLater(interval, method)

    def datagramReceived(self, data, (host, port)):
        self.process_queue.put(data)

    def handle_packet(self, packet):
        self.read_packet(packet)
        try:
            self.reactor.callFromThread(self.get_and_addCallback, self.handle_packet)
        except Exception, exp:
            print "[%s] > Exception during scheduling next get: %s" % (self.name, str(exp))

    def read_packet(self, packet):
        try:
            decoded_packet = petlib.pack.decode(packet)
            flag, decrypted_packet = self.crypto_node.process_packet(decoded_packet)
            if flag == "ROUT":
                delay, new_header, new_body, next_addr, _ = decrypted_packet
                reactor.callFromThread(self.send_or_delay, delay, (new_header, new_body), next_addr)
            elif flag == "LOOP":
                print "[%s] > Received loop message" % self.name
        except Exception, exp:
            print "ERROR: ", str(exp)

    def send_or_delay(self, delay, packet, addr):
        self.reactor.callLater(delay, self.send, packet, addr)

    def send(self, packet, (host, port)):
        encoded_packet = petlib.pack.encode(packet)
        if abstract.isIPAddress(host):
            self.transport.write(encoded_packet, (host, port))
        else:
            def send_to_ip(ip_addr):
                self.transport.write(encoded_packet, (ip_addr, port))
            try:
                self.transport.write(encoded_packet, (self.resolvedAdrs[host], port))
            except KeyError, e:
                self.reactor.resolve(host).addCallback(send_to_ip)

    def stopProtocol(self):
        print "[%s] > Stopped" % self.name
