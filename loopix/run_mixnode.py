import os
import sys
current_path = os.getcwd()
print "Current Path: %s" % current_path
sys.path += [current_path]

from loopix_mixnode import LoopixMixNode
from twisted.internet import reactor
from twisted.application import service, internet

import petlib.pack
from binascii import hexlify
import os.path
from sphinxmix.SphinxParams import SphinxParams

name = sys.argv[1]

if not (os.path.exists("secretMixnode.prv") and os.path.exists("publicMixnode.bin")):
	raise Exception("Key parameter files not found")

secret = petlib.pack.decode(file("secretMixnode.prv", "rb").read())
sec_params = SphinxParams(header_len=1024)
try:
	data = file("publicMixnode.bin", "rb").read()
	_, name, port, host, group, _ = petlib.pack.decode(data)

	mix = LoopixMixNode(sec_params, name, port, host, group, privk=secret, pubk=None)
	# reactor.listenUDP(port, mix)
	# reactor.run()
	udp_server = internet.UDPServer(port, mix)
	application = service.Application("Mixnode")
	udp_server.setServiceParent(application)

except Exception, e:
	print str(e)
