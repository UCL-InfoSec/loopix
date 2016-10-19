import format3
from twisted.protocols import basic
from twisted.internet import stdio, reactor
import sys

import petlib.pack
from binascii import hexlify
import os.path

from shutil import copyfile

def clean_and_setup():
	if os.path.exists("secretClient.prv"):
		os.remove("secretClient.prv")
	if os.path.exists("publicClient.bin"):
		os.remove("publicClient.bin")
	if os.path.exists("example.db"):
		os.remove("example.db")
	if os.path.exists("providersNames.bi2"):
		os.remove("providersNames.bi2")

	copyfile('../aws/example.db', './example.db')
	copyfile('../aws/providersNames.bi2','./providersNames.bi2')



if __name__ == "__main__":

	clean_and_setup()
	if not (os.path.exists("secretClient.prv") or os.path.exists("publicClient.bin")):

		port = int(sys.argv[1])
		host = sys.argv[2]
		name = sys.argv[3]
		prvname = sys.argv[4]

		setup = format3.setup()
		G, o, g, o_bytes = setup

		secret = o.random()
		file("secretClient.prv", "wb").write(petlib.pack.encode(secret))

		pub = secret * g
		file("publicClient.bin", "wb").write(petlib.pack.encode(["client", name, port, host, pub, prvname]))
	else:
		print "Files exist"
