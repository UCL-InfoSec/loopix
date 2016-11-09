from mixnode import MixNode
import format3
from twisted.protocols import basic
from twisted.internet import stdio, reactor
import sys

import petlib.pack
from binascii import hexlify
import os.path


if __name__ == "__main__":

	if not (os.path.exists("secretMixnode.prv") or os.path.exists("publicMixnode.bin")):

		port = int(sys.argv[1])
		host = sys.argv[2]
		name = sys.argv[3]

		setup = format3.setup()
		G, o, g, o_bytes = setup

		secret = o.random()
		file("secretMixnode.prv", "wb").write(petlib.pack.encode(secret))

		pub = secret * g
		def save_resolved(IPAdress):
			file("publicMixnode.bin", "wb").write(petlib.pack.encode(["mixnode", name, port, IPAdress, pub]))
		reactor.resolve(host).addCallback(save_resolved)

	else:
		print "Files exist"

		