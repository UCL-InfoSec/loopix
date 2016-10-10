from mixnode import MixNode
import format3
from twisted.protocols import basic
from twisted.internet import stdio, reactor
import sys

import petlib.pack
from binascii import hexlify

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


if __name__ == "__main__":

	port = int(sys.argv[1])
	host = sys.argv[2]
	name = sys.argv[3]

	setup = format3.setup()
	G, o, g, o_bytes = setup

	try:
		secret = petlib.pack.decode(file("secret.prv", "rb").read())
	except:
		secret = o.random()
		file("secret.prv", "wb").write(petlib.pack.encode(secret))

	try:
		# Create the mix
		mix = MixNode(name, port, host, setup, privk=secret)
		print "Public key: " + hexlify(mix.pubk.export())
		file("public.bin", "wb").write(petlib.pack.encode(["mixnode", name, port, host, mix.pubk]))

		reactor.listenUDP(port, mix)	

		# Create a cmd line controller
		stdio.StandardIO(MixnodeEcho(mix))
		reactor.run()

	except Exception, e:
		print str(e)
