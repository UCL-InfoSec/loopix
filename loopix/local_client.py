from client import Client
import format3
import petlib
import os
import sys
from twisted.internet import reactor
from twisted.protocols import basic
from twisted.internet import stdio
import time

class ClientEcho(basic.LineReceiver):
	from os import linesep as delimiter
	def __init__(self, client):
		self.client = client
		reactor.listenUDP(port, self.client)

	def connectionMade(self):
		self.transport.write('>>> ')

	def lineReceived(self, line):
		if line.upper() == "-P":
			print "Hello world"
		elif line.upper() == "-T":
			try:
				self.client.sendTagedMessage()
			except Exception, e :
				print str(e)
		elif line.upper() == "-E":
			reactor.stop()
		else:
			print "Command not found"
		self.transport.write('>>> ')


if __name__ == "__main__":

	if not (os.path.exists('secretClient.prv') and os.path.exists("publicClient.bin")):
		raise Exception("Key parameter files not found")

	setup = format3.setup()
	G, o, g, o_bytes = setup

	secret = petlib.pack.decode(file("secretClient.prv", "rb").read())

	try:
		data = file("publicClient.bin", "rb").read()
		_, name, port, host, _, prvname = petlib.pack.decode(data)
		client = Client(setup, name, port, host, privk = secret, providerId=prvname)

		if "--mock" not in sys.argv:
			stdio.StandardIO(ClientEcho(client))
			reactor.run()

	except Exception, e :
		print str(e)