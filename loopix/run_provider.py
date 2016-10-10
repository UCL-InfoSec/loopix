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

	port = int(sys.argv[1])
	host = sys.argv[2]
	name = sys.argv[3]

	setup = format3.setup()
	G, o, g, o_bytes = setup

	try:
	 	secret = petlib.pack.decode(file("secretProvider.prv", "rb").read())
	except:
	 	secret = o.random()
	 	file("secretProvider.prv", "wb").write(petlib.pack.encode(secret))

	try:
	 	provider = Provider(name, port, host, setup, privk=secret)
	 	file("publicProvider.bin", "wb").write(petlib.pack.encode(["provider", name, port, host, provider.pubk]))
		
	 	if "--mock" not in sys.argv:
			stdio.StandardIO(ProviderEcho(provider))
			reactor.listenUDP(port, provider)
	 		reactor.run()
	except Exception, e:
		print str(e)



