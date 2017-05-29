from mix_core import MixCore
from sphinxmix.SphinxParams import SphinxParams
from processQueue import ProcessQueue
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, defer
from core import get_group_characteristics, sample_from_exponential, group_layered_topology
from databaseConnect import DatabaseManager
import petlib.pack
import random
import pybloom

class LoopixMixNode(DatagramProtocol):
    EXP_PARAMS_LOOPS = 2.0
    DATABSE_NAME = "example.db"

    def __init__(self, name, port, host, group, privk=None, pubk=None):
        self.name = name
        self.port = port
        self.host = host
        self.group = group

        params = SphinxParams(header_len=1024)
        order, generator = get_group_characteristics(params)
        self.privk = privk or order.random()
        self.pubk = pubk or (self.privk * generator)
        self.core = MixCore(params, self.name, self.port, self.host, self.privk, self.pubk)
        self.process_queue = ProcessQueue()
        self.reactor = reactor

    def startProtocol(self):
        print "[%s] > Started" % self.name
        self.get_network_info()
        self.turn_on_processing()
        # turn on sending heartbeats for mixes and providers (by default)

    def get_network_info(self):
        self.dbManager = DatabaseManager(self.DATABASE_NAME)
        mixes = self.dbManager.select_all_mixnodes()
        providers = self.dbManager.select_all_providers()
        self.register_mixes([m for m in mixes if not m.name == self.name ])
        self.register_providers([p for p in providers if not p.name == self.name])

    def register_mixes(self, mixes):
        self.pubs_mixes = group_layered_topology(mixes)

    def register_providers(self, providers):
        self.pubs_providers = providers

    def turn_on_processing(self):
        self.reactor.callLater(20.0, self.get_and_addCallback, self.handle_packet)

    def get_and_addCallback(self, f):
        self.process_queue.get().addCallback(f)

    def make_loop_stream(self):
        self.send_loop_message()
        self.schedule_next_call(self.EXP_PARAMS_LOOPS, self.make_loop_stream)

    def send_loop_message(self):
        path = self.generate_random_path()
        packet = self.core.create_loop_message(path)
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
        self.process_queue.put((data, (host, port)))

    def handle_packet(self, packet):
        self.read_packet(packet)
        try:
            self.reactor.callFromThread(self.get_and_addCallback, self.handle_packet)
        except Exception, e:
            print "[%s] > Exception during scheduling next get: %s" % (self.name, str(e))

    def read_packet(self, packet):
        flag, packet = self.core.process_packet(packet)
        if flag == "ROUT":
            delay, new_header, new_body, next_addr, next_name = packet
            reactor.callFromThread(self.send_or_delay, delay, (new_header, new_body), next_addr)
        elif flag == "LOOP":
            print "[%s] > Received loop message" % self.name

    def send_or_delay(self, delay, packet, addr):
        self.reactor.callLater(delay, self.send, packet, addr)

    def send(self, packet, addr):
        encoded_packet = petlib.pack.encode(packet)
        self.transport.write(encoded_packet, addr)

    def stopProtocol(self):
        print "[%s] > Stopped" % self.name
