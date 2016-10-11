import os
import sys
current_path = os.getcwd()
print "Current Path: %s" % current_path
sys.path += [current_path]

from mixnode import MixNode
import format3
from twisted.protocols import basic
from twisted.internet import stdio, reactor
from twisted.application import service, internet

import petlib.pack
from binascii import hexlify
import os.path

class MixnodeEcho(basic.LineReceiver):
	from os import linesep as delimiter
	def __init__(self, mix):
		self.mix = mix

	def connectionMade(self):
		self.transport.write('>>> ')

	def lineReceived(self, line):
		if line.upper() == "-E":
			reactor.stop()
		elif line.upper() == "-R":
			self.mix.readInData('example.db')
		elif line.upper() == "-P":
			print self.mix
		else:
			print ">> Command not found."
		self.transport.write('>>> ')


if not (os.path.exists("secretMixnode.prv") and os.path.exists("publicMixnode.bin")):
	raise Exception("Key parameter files not found")

# Read crypto parameters
setup = format3.setup()
G, o, g, o_bytes = setup
secret = petlib.pack.decode(file("secretMixnode.prv", "rb").read())

try:
	data = file("publicMixnode.bin", "rb").read()
	_, name, port, host, _ = petlib.pack.decode(data)

	# Create the mix
	mix = MixNode(name, port, host, setup, privk=secret)
	#mix.readInData('example.db')
	print "Public key: " + hexlify(mix.pubk.export())
	
	udp_server = internet.UDPServer(port, mix)	

	# Create a cmd line controller
	# stdio.StandardIO(MixnodeEcho(mix))

	application = service.Application("Mixnode")
	udp_server.setServiceParent(application)
	
except Exception, e:
	print str(e)


