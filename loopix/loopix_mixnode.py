from mix_core import MixCore
from sphinxmix.SphinxParams import SphinxParams
from processQueue import ProcessQueue
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, defer

class LoopixMixNode(DatagramProtocol):
    def __init__(self, name, port, host, privk=None, pubk=None):
        self.name = name
        self.port = port
        self.host = host

        params = SphinxParams(header_len=1024)
        gr_order = params.group.G.order()
        gr_generator = params.group.G.generator()

        self.privk = privk or gr_order.random()
        self.pubk = pubk or (self.privk * gr_generator)

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
        pass

    def datagramReceived(self, data, (host, port)):
        self.process_queue.put((data, (host, port)))

    def turn_on_processing(self):
        self.process_queue.get().addCallback(self.process_packet)

    def process_packet(self, packet):
        ## Can we merge process_packet and read_packet
        self.read_packet(packet)
        try:
            reactor.callFromThread(self.get_and_addCallback, self.process_packet)
        except Exception, e:
            print "[%s] > Exception during scheduling next get: %s" % (self.name, str(e))

    def read_packet(self, packet):
        return self.core.process_packet(packet)

    def get_and_addCallback(self, f):
        self.process_queue.get().addCallback(f)

    def send(self, packet, addr):
        self.transport.write(packet, addr)
