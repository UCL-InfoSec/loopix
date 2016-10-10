from mixnode import MixNode
import format3
from twisted.protocols import basic
from twisted.internet import stdio, reactor
import sys

import petlib.pack
from binascii import hexlify
import os.path

if __name__ == "__main__":

	if not (os.path.exists("secretClient.prv") or os.path.exists("publicClient.bin")):

		port = int(sys.argv[1])
		host = sys.argv[2]
		name = sys.argv[3]

		setup = format3.setup()
		G, o, g, o_bytes = setup

		secret = o.random()
		file("secretClient.prv", "wb").write(petlib.pack.encode(secret))

		pub = secret * g
		file("publicClient.bin", "wb").write(petlib.pack.encode(["client", name, port, host, pub]))
	else:
		print "Files exist"
