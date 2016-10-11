import os
import sys
current_path = os.getcwd()
print "Current path %s" % current_path
sys.path += [current_path]

from provider import Provider
import format3
from twisted.internet import reactor, stdio
from twisted.protocols import basic
from twisted.application import service, internet
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


setup = format3.setup()
G, o, g, o_bytes = setup
secret = petlib.pack.decode(file("secretProvider.prv", "rb").read())
_, name, port, host, _ = petlib.pack.decode(file("publicProvider.bin", "rb").read())

try:
 	provider = Provider(name, port, host, setup, privk=secret)
 	#provider.readInData('example.db')
 	# stdio.StandardIO(ProviderEcho(provider))

 	udp_server = internet.UDPServer(port, provider)

 	application = service.Application("Provider")
 	udp_server.setServiceParent(application)

except Exception, e:
	print str(e)



