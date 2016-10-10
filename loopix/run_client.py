from twisted.internet import reactor
from client import Client
import format3
import sys
import petlib
from twisted.internet import stdio
from twisted.protocols import basic
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


if __name__ == "__main__":

	port = int(sys.argv[1])
	host = sys.argv[2]
	name = sys.argv[3]

	setup = format3.setup()
	G, o, g, o_bytes = setup

	try:
		secret = petlib.pack.decode(file("secretClient.prv", "rb").read())
	except:
		secret = o.random()
		file("secretClient.prv", "wb").write(petlib.pack.encode(secret))

	try:
		client = Client(setup, name, port, host, privk = secret)
		file("publicClient.bin", "wb").write(petlib.pack.encode(["client", name, port, host, client.pubk]))
		
		reactor.listenUDP(port, client)

		stdio.StandardIO(client)
		if "--mock" not in sys.argv:
			reactor.run()

	except Exception, e:
		print str(e)
