import os
import sys
current_path = os.getcwd()
print "Current Path: %s" % current_path
sys.path += [current_path]



from twisted.internet import reactor
from client import Client
import format3
import petlib
from twisted.internet import stdio
from twisted.protocols import basic
from twisted.application import service, internet

import sqlite3
import databaseConnect as dc

def readAllUsersFromDB(database):
        usersList = []
        db = sqlite3.connect(database)
        c = db.cursor()
        c.execute("SELECT * FROM %s" % "Users")
        users = c.fetchall()
        for u in users:
        	p = petlib.pack.decode(u[5])
        	usersList.append(format3.User(str(u[1]), int(u[2]), str(u[3]), petlib.pack.decode(u[4]), 
            	format3.Mix(p[0],p[1],p[2],p[3])))      
        db.close()
        return usersList


class ClientEcho(basic.LineReceiver):
	from os import linesep as delimiter
	def __init__(self, client):
		self.client = client

	def connectionMade(self):
		self.transport.write('>>> ')

	def lineReceived(self, line):
		if line.upper() == "-R":
			try:
				self.client.readInUsersPubs()
				print self.client.usersPubs
			except Exception, e:
				print str(e)
		elif line.upper() == "-E":
			reactor.stop()
		else:
			print "Command not found"
		self.transport.write('>>> ')



if not (os.path.exists("secretClient.prv") and os.path.exists("publicClient.bin")):
	raise Exception("Key parameter files not found")

setup = format3.setup()
G, o, g, o_bytes = setup

secret = petlib.pack.decode(file("secretClient.prv", "rb").read())

try:
	data = file("publicClient.bin", "rb").read()
	_, name, port, host, _, prvname = petlib.pack.decode(data)
 	client = Client(setup, name, port, host, privk = secret, providerId=prvname)
 	
	# reactor.listenUDP(port, client)
	# reactor.run()

	udp_server = internet.UDPServer(port, client)	

	# Create a cmd line controller
	# stdio.StandardIO(MixnodeEcho(mix))

	application = service.Application("Client")
	udp_server.setServiceParent(application)

except Exception, e:
 	print str(e)
