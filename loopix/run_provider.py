from provider import Provider
import format3
from twisted.internet import reactor, stdio
from twisted.protocols import basic
import sys

class ProviderEcho(basic.LineReceiver):
	from os import linesep as delimiter
	def __init__(self, port, host):
		try:
			self.provider = Provider("Provider%d"%port, port, host, format3.setup())
			reactor.listenUDP(self.provider.port, self.provider)
		except Exception, e:
			print str(e)

	def connectionMade(self):
		self.transport.write(">>>")

	def lineReceived(self, line):
		if line.upper() == "-P":
			print self.provider
		elif line.upper() == "-R":
			self.provider.readMixnodesFromDatabase('example.db')
		elif line.upper() == "-E":
			reactor.stop()
		else:
			print "Command not found."
		self.transport.write(">>>")


if __name__ == "__main__":
	stdio.StandardIO(ProviderEcho(int(sys.argv[1]), sys.argv[2]))
	reactor.run()


