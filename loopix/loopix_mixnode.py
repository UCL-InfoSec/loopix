from mix_core import MixCore
from sphinxmix.SphinxParams import SphinxParams
from processQueue import ProcessQueue
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, defer
from core import get_group_characteristics, sample_from_exponential

class LoopixMixNode(DatagramProtocol):
    EXP_PARAMS_LOOPS = 2.0

    def __init__(self, name, port, host, privk=None, pubk=None):
        self.name = name
        self.port = port
        self.host = host

        params = SphinxParams(header_len=1024)
        order, generator = get_group_characteristics(params)
        self.privk = privk or order.random()
        self.pubk = pubk or (self.privk * generator)
        self.core = MixCore(params, self.name, self.port, self.host, self.privk, self.pubk)
        self.process_queue = ProcessQueue()
        self.reactor = reactor

    def startProtocol(self):
        print "[%s] > Started" % self.name

    def stopProtocol(self):
        print "[%s] > Stopped" % self.name

    def register_mixes(self, mixes):
        self.mixes = mixes

    def register_providers(self, providers):
        self.providers = providers

    def make_loop_stream(self):
        self.send_loop_message()
        self.schedule_next_call(self.EXP_PARAMS_LOOPS, self.make_loop_stream)

    def send_loop_message(self):
        path = self.construct_full_path(self)
        packet = self.core.create_loop_message(path)
        addr = (path[0].host, path[0].port)
        self.send(packet, addr)

    def construct_full_path(self):
        return self.mixes

    def schedule_next_call(self, param, method):
        interval = self.sample_from_exponential(param)
        self.reactor.callLater(interval, method)

    def datagramReceived(self, data, (host, port)):
        self.process_queue.put((data, (host, port)))

    def turn_on_processing(self):
        self.process_queue.get().addCallback(self.process_packet)

    def process_packet(self, packet):
        ## Can we merge process_packet and read_packet??
        self.read_packet(packet)
        try:
            reactor.callFromThread(self.get_and_addCallback, self.process_packet)
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

    def get_and_addCallback(self, f):
        self.process_queue.get().addCallback(f)

    def send(self, packet, addr):
        encoded_packet = petlib.pack.encode(packet)
        self.transport.write(encoded_packet, addr)
