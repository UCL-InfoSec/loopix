import format3
from twisted.protocols import basic
from twisted.internet import stdio, reactor
import sys

import petlib.pack
from binascii import hexlify
import os.path

if __name__ == "__main__":

	port = int(sys.argv[1])
	host = sys.argv[2]
	name = sys.argv[3]
	prvname = sys.argv[4]

	if not (os.path.exists("secretClient.prv") or os.path.exists("publicClient.bin")):

		setup = format3.setup()
		G, o, g, o_bytes = setup

		secret = o.random()
		file("secretClient.prv", "wb").write(petlib.pack.encode(secret))

		pub = secret * g
		file("publicClient.bin", "wb").write(petlib.pack.encode(["client", name, port, host, pub, prvname]))
	else:
		print "Files exist"
