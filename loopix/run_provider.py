from provider import Provider
import format3
from twisted.internet import reactor, stdio
from twisted.protocols import basic
import sys
import petlib.pack

class ProviderEcho(basic.LineReceiver):
	from os import linesep as delimiter
	def __init__(self, provider):
		self.provider = provider

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

	setup = format3.setup()
	G, o, g, o_bytes = setup
	secret = petlib.pack.decode(file("secretProvider.prv", "rb").read())
	_, name, port, host, _ = petlib.pack.decode(file("publicProvider.bin", "rb").read())

	try:
	 	provider = Provider(name, port, host, setup, privk=secret)
	 	# stdio.StandardIO(ProviderEcho(provider))
		reactor.listenUDP(port, provider)
	 	reactor.run()
	except Exception, e:
		print str(e)



