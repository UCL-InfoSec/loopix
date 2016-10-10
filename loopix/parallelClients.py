import format3
import sys
import petlib
from twisted.internet import stdio
from twisted.protocols import basic
from twisted.internet import reactor, task
from client import Client
import base64
import resource
import codecs
import random
import uuid
import calendar
import time
import random
import os
import databaseConnect as dc
import sqlite3
import socket

MAX_RECEIVERS = 20
GROUPS = 10
COUNTER = 0
MESSAGE_LENGTH = 1000

def readClientData(fileName):
	data = []
	with codecs.open(fileName, 'rb+',"utf-8") as infile:
		lines = infile.readlines()
	for i, element in enumerate(lines):
		element = element[:-1]	
		data.append(petlib.pack.decode(base64.b64decode(element)))
	return data

def eraseFile(fileName):
	open(fileName, 'wb').close()

class ClientGeneratorEcho(basic.LineReceiver):
	from os import linesep as delimiter
	def __init__(self, num):
		target_procs = 5000
		my_procs = 1000
		real_procs = max(target_procs, my_procs)
		resource.setrlimit(resource.RLIMIT_NOFILE, (real_procs, resource.RLIM_INFINITY))

		self.clients = []
		for i in range(num):
			providersNum = numProviders('example.db')
			client = Client(format3.setup(), "Client%d"%(6000+i), 6000+i, "127.0.0.1")
			self.clients.append(client)
			reactor.listenUDP(client.port, client)

	def connectionMade(self):
		self.transport.write('>>> ')

	def lineReceived(self, line):
		if line.upper() == "-T":
			try:
				for client in self.clients:
					client.turnOnMessaging(client.mixnet)
				sender = random.choice(self.clients)
				sender.measureSentBytes()
				sendTagedMessage(sender)
			except Exception, e:
				print str(e)
		elif line.upper() == "-B":
			for client in self.clients:
				client.turnOnMessaging(client.mixnet)
		elif line.upper() == "-E":
			dbConn.close()
			reactor.stop()
		elif line.upper() == "-R":
			# For each client read in the public information about users
			try:
				for client in self.clients:
					client.takeMixnodesData('example.db')
				print client.mixnet
				users = readAllUsersFromDB('example.db')
				for client in self.clients:
					client.usersPubs = users					
			except Exception, e:
				print str(e)
		elif line.upper() == "-PRINT":
			for client in self.clients:
				print client.name
				for i in client.usersPubs:
					print i
		elif line.upper() == "-STAT":
			for client in self.clients:
				print client.getStatistics()
		else:
			print "Command not found"
		self.transport.write(">>> ")

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

def numProviders(database):
	db = sqlite3.connect(database)
	return dc.countRows(db, "Providers")

def createSocialGroups(clients, numGroups):
	socialNetwork = {}
	for c in clients:
		idx = random.randint(0,numGroups)
		if idx in socialNetwork:
			socialNetwork[idx].append(c)
		else:
			socialNetwork[idx] = [c]
	return socialNetwork

def sendTagedMessage(client, receiver=None):
	client.sendTagedMessage(client.mixnet)

def sendingTest(client, receiver=None, predefinedPath = None):
	try:
		receiver = receiver if receiver else client.selectRandomReceiver()
		mixes = predefinedPath if predefinedPath else client.takePathSequence(client.mixnet, client.PATH_LENGTH)
	except Exception, e:
		print str(e)
	else:	
		idt = str(uuid.uuid1())
		randomNoise = os.urandom(MESSAGE_LENGTH)
		client.sendMessage(receiver, mixes, 'Test%s'%idt+randomNoise, 'Test%sBounce'%idt+randomNoise)

def sendToFriends(client, group):
	for u in group:
		if client != u:
			sendTagedMessage(client, u)

def takeFriends(client, group):
	friends = []
	for f in group:
		if client != f:
			friends.append(f)
	return friends

def turnOnBigPayload(clients, flag):
	for client in clients:
		sendingToAll(client, client.mixnet, flag)

def sendingToAll(client, mixes, predefinedFlag):
	length = 3
	fixedMix = takeMix(client)
	for r in client.usersPubs:
		if random.randint(0,1) == 1:
			if predefinedFlag:
				predefinedPath = random.sample(mixes, length-1)
	 			predefinedPath.insert(random.randrange(len(predefinedPath)+1), fixedMix)	 		
	 			sendingTest(client, r, predefinedPath)
	 		else:
	 			sendingTest(client, r)

def takeMix(client):
	for m in client.mixnet:
		if m.name == "MixNode8005":
			return m

def randomSending(friends):
	global COUNTER
	for group in friends.keys():
		for client in friends[group]:
			separated = takeFriends(client, friends[group])
			if separated:
				receiver = random.choice(separated)
				sendingTest(client, receiver)
			else:
				receiver = client.selectRandomReceiver()
				mixes = client.takePathSequence(client.mixnet, client.PATH_LENGTH)
				idt = str(uuid.uuid1())
				#randomNoise = os.urandom(MESSAGE_LENGTH)
				randomNoise = ''
				client.sendMessage(receiver, mixes, 'Test%s'%idt+randomNoise, 'Test%sBounce'%idt+randomNoise)
	COUNTER += 1
	if COUNTER == 3:
		reactor.stop()

if __name__ == "__main__":
	dbConn = dc.connectToDatabase('example.db')
	c = dbConn.cursor()
	dc.dropTabel(dbConn, "Users")
	dc.createUsersTable(dbConn, "Users")

	stdio.StandardIO(ClientGeneratorEcho(int(sys.argv[1])))
	reactor.run()
