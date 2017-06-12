import os
import sys
current_path = os.getcwd()
print "Current path %s" % current_path
sys.path += [current_path]

from loopix_provider import LoopixProvider
from twisted.internet import reactor
from twisted.application import service, internet
import petlib.pack
from sphinxmix.SphinxParams import SphinxParams

if not (os.path.exists("secretProvider.prv") and os.path.exists("publicProvider.bin")):
	raise Exception("Key parameter files not found")

secret = petlib.pack.decode(file("secretProvider.prv", "rb").read())
_, name, port, host, _ = petlib.pack.decode(file("publicProvider.bin", "rb").read())
sec_params = SphinxParams(header_len=1024)

try:
	provider = LoopixProvider(sec_params, name, port, host, privk=secret, pubk=None)
	# reactor.listenUDP(port, provider)
	# reactor.run()
 	udp_server = internet.UDPServer(port, provider)
 	application = service.Application("Provider")
 	udp_server.setServiceParent(application)

except Exception, e:
	print str(e)
