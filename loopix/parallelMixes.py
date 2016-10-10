import format3
import sys
import petlib
from twisted.internet import stdio
from twisted.protocols import basic
from twisted.internet import reactor
from mixnode import MixNode
import random
import socket
import databaseConnect as dc

class MixnodeGeneratorEcho(basic.LineReceiver):
	from os import linesep as delimiter
	def __init__(self, num):
		self.mixes = []
		for i in range(num):
			mix = MixNode("MixNode%d"%(8001+i), 8001+i, "127.0.0.1", format3.setup())
			self.mixes.append(mix)
			reactor.listenUDP(mix.port, mix)

	def connectionMade(self):
		self.transport.write('>>> ')

	def lineReceived(self, line):
		if line.upper() == "-B":
			tmp_mix = choice("MixNode8005", self.mixes)
			tmp_mix.measureBandwidth()
		elif line.upper() == "-E":
			reactor.stop()
		elif line.upper() == "-PRINT":
			for mix in self.mixes:
				print mix.mixnet
		elif line.upper() == "-R":
			try:
				for m in self.mixes:
					m.readInData('example.db')
			except Exception, e:
				print str(e)
		elif line.upper() == "-P":
			for mix in self.mixes:
				mix.sendRequest("PULL")
		else:
			print "Command not found."
		self.transport.write(">>> ")

def choice(name, mixes):
	for m in mixes:
		if m.name == name:
			return m

if __name__ == "__main__":
	dbConn = dc.connectToDatabase('example.db')
	c = dbConn.cursor()
	dc.dropTabel(dbConn, "Mixnodes")
	dc.createMixnodesTable(dbConn, "Mixnodes")
	stdio.StandardIO(MixnodeGeneratorEcho(int(sys.argv[1])))
	reactor.run()