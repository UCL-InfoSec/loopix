import os
import sys
current_path = os.getcwd()
print "Current Path: %s" % current_path
sys.path += [current_path]


from loopix_client import LoopixClient
import petlib
from twisted.application import service, internet
from twisted.python import usage

if not (os.path.exists("secretClient.prv") and os.path.exists("publicClient.bin")):
    raise Exception("Key parameter files not found")

secret = petlib.pack.decode(file("secretClient.prv", "rb").read())

try:
    data = file("publicClient.bin", "rb").read()
    _, name, port, host, _, prvname = petlib.pack.decode(data)

    client = LoopixClient(name, port, host, providerInfo=prvname, privk = secret)
    udp_server = internet.UDPServer(port, client)
    application = service.Application("Client")
    udp_server.setServiceParent(application)

except Exception, e:
 	print str(e)
