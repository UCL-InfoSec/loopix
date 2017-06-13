import core
import sys
import os.path
import petlib.pack


if __name__ == "__main__":

	port = int(sys.argv[1])
	host = sys.argv[2]
	name = sys.argv[3]
	prvinfo = str(sys.argv[4])

	if not (os.path.exists("secretClient.prv") or os.path.exists("publicClient.bin")):

		setup = core.setup()
		G, o, g, o_bytes = setup

		secret = o.random()
		file("secretClient.prv", "wb").write(petlib.pack.encode(secret))

		pub = secret * g
		file("publicClient.bin", "wb").write(petlib.pack.encode(["client", name, port, host, pub, prvinfo]))
	else:
		print "Files exist"
