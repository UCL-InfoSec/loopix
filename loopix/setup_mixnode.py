import sys
import core
import petlib.pack
import os.path



if __name__ == "__main__":

	port = int(sys.argv[1])
	host = sys.argv[2]
	name = sys.argv[3]
	group = int(sys.argv[4])

	if not (os.path.exists("secretMixnode.prv") or os.path.exists("publicMixnode.bin")):

		setup = core.setup()
		G, o, g, o_bytes = setup

		secret = o.random()
		file("secretMixnode.prv", "wb").write(petlib.pack.encode(secret))

		pub = secret * g
		file("publicMixnode.bin", "wb").write(petlib.pack.encode(["mixnode", name, port, host, group, pub]))
	else:
		print "Files exist"
