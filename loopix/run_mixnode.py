from mixnode import MixNode
import format3
from twisted.protocols import basic
from twisted.internet import stdio, reactor
import sys

class MixnodeEcho(basic.LineReceiver):
	from os import linesep as delimiter
	def __init__(self, port, host):
		try:
			self.mix = MixNode("Mixnode%d"%port, port, host, format3.setup())
			reactor.listenUDP(self.mix.port, self.mix)
		except Exception, e:
			print str(e)

	def connectionMade(self):
		self.transport.write('>>> ')

	def lineReceived(self, line):
		if line.upper() == "-E":
			reactor.stop()
		elif line.upper() == "-R":
			self.mix.readMixnodesFromDatabase('example.db')
		elif line.upper() == "-P":
			print self.mix
		else:
			print ">> Command not found."
		self.transport.write('>>> ')


if __name__ == "__main__":
	stdio.StandardIO(MixnodeEcho(int(sys.argv[1]), sys.argv[2]))
	reactor.run()