import os
import sys
current_path = os.getcwd()
print "Current path %s" % current_path
sys.path += [current_path]

from loopix_provider import LoopixProvider
from twisted.internet import reactor
from twisted.application import service, internet
import petlib.pack

if not (os.path.exists("secretMixnode.prv") and os.path.exists("publicMixnode.bin")):
	raise Exception("Key parameter files not found")

secret = petlib.pack.decode(file("secretProvider.prv", "rb").read())
_, name, port, host, _ = petlib.pack.decode(file("publicProvider.bin", "rb").read())

try:
	provider = LoopixProvider(name, port, host, privk=secret)
 	udp_server = internet.UDPServer(port, provider)
 	application = service.Application("Provider")
 	udp_server.setServiceParent(application)

except Exception, e:
	print str(e)
