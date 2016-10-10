from twisted.internet import reactor
from provider import Provider
import sys
import format3
from twisted.internet import stdio
from twisted.protocols import basic
import resource
import databaseConnect as dc
import random
import socket

def eraseFile(fileName):
	open(fileName, 'wb').close()

class ProviderEcho(basic.LineReceiver):
	from os import linesep as delimiter
	def __init__(self, num):
		self.providers = []
		for i in range(num):
			provider = Provider("ClientProvider%d"%(9000+i), 9000+i, "127.0.0.1", format3.setup())
			self.providers.append(provider)
			reactor.listenUDP(provider.port, provider)
		
	def connectionMade(self):
		self.transport.write('>>> ')

	def lineReceived(self, line):
		if line.upper() == "-M":
			try:
				tmp = self.providers[0]
				print tmp.name
				tmp.measureBandwidth()
			except Exception, e:
				print str(e)
		elif line.upper() == "-R":
			try:
				for p in self.providers:
					p.readInData('example.db')
			except Exception, e:
				print str(e)
		elif line.upper() == "-E":
			reactor.stop()
		elif line.upper() == "-C":
			for provider in self.providers:
				print provider.clientList
		else:
			print "Command not found."
		self.transport.write('>>> ')			

if __name__ == "__main__":
	eraseFile('providerPub.txt')
	dbConn = dc.connectToDatabase('example.db')
	c = dbConn.cursor()
	dc.dropTabel(dbConn, "Providers")
	dc.createProvidersTable(dbConn, "Providers")
	stdio.StandardIO(ProviderEcho(int(sys.argv[1])))
	reactor.run()
