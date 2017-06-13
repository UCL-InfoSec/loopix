import core
import sys
import petlib.pack
import os.path

if __name__ == "__main__":

	if not (os.path.exists("secretProvider.prv") or os.path.exists("publicProvider.bin")):

		port = int(sys.argv[1])
		host = sys.argv[2]
		name = sys.argv[3]

		setup = core.setup()
		G, o, g, o_bytes = setup

		secret = o.random()
		file("secretProvider.prv", "wb").write(petlib.pack.encode(secret))

		pub = secret * g
		file("publicProvider.bin", "wb").write(petlib.pack.encode(["provider", name, port, host, pub]))

	else:
		print "Files Exist"
