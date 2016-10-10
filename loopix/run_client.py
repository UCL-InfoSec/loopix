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
	def __init__(self, port, host):
		try:
			self.client = Client(format3.setup(), "Client%d"%(port), port, host)
			reactor.listenUDP(self.client.port, self.client)
		except Exception, e:
			print str(e)

	def connectionMade(self):
		self.transport.write('>>> ')

	def lineReceived(self, line):
		if line.upper() == "-R":
			try:
				self.client.readInUsersPubs()
				#self.client.usersPubs = readAllUsersFromDB('example.db')
				print self.client.usersPubs
			except Exception, e:
				print str(e)
		elif line.upper() == "-E":
			reactor.stop()
		else:
			print "Command not found"
		self.transport.write('>>> ')


if __name__ == "__main__":
	stdio.StandardIO(ClientEcho(int(sys.argv[1]), sys.argv[2]))
	reactor.run()
