import binascii
import format3
from hashlib import sha1
import heapq
import hmac
import io
import msgpack
import numpy
from petlib.ec import EcGroup, EcPt
from petlib.bn import Bn
from petlib.cipher import Cipher
import petlib.pack
import random
import time
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, defer, task
from twisted.internet.defer import DeferredQueue
import uuid
import sqlite3
import supportFunctions as sf
import sys
import csv
from processQueue import ProcessQueue
from sets import Set
import json
import hashlib

from sphinxmix.SphinxParams import SphinxParams
from sphinxmix.SphinxNode import sphinx_process
from sphinxmix.SphinxClient import PFdecode, Relay_flag, Dest_flag, Surb_flag, receive_forward, Nenc, create_forward_message

with open('config.json') as infile:
	_PARAMS = json.load(infile) 

TIME_ACK = float(_PARAMS["parametersMixnodes"]["TIME_ACK"])
TIME_FLUSH = float(_PARAMS["parametersMixnodes"]["TIME_FLUSH"])
TIME_CLEAN = float(_PARAMS["parametersMixnodes"]["TIME_CLEAN"])
MAX_DELAY_TIME = float(_PARAMS["parametersMixnodes"]["MAX_DELAY_TIME"])
NOISE_LENGTH = float(_PARAMS["parametersMixnodes"]["NOISE_LENGTH"])
MEASURE_TIME = float(_PARAMS["parametersMixnodes"]["MEASURE_TIME"])
SAVE_MEASURMENTS_TIME = float(_PARAMS["parametersMixnodes"]["SAVE_MEASURMENTS_TIME"])

class MixNode(DatagramProtocol):
	"""Class of Mixnode creates an object of a mixnode,
	which can be used in a mixnetwork"""

	def __init__(self, name, port, host, setup, privk=None, pubk=None):
		"""Creates an object of a mix node defined by its name and keypair"""
		self.name = name
		self.port = port
		self.host = host

		self.setup = setup
		self.G, self.o, self.g, self.o_bytes = self.setup

		# Generate a key pair
		self.privk = privk or self.o.random()
		self.pubk = pubk or (self.privk * self.g)

		self.d = defer.Deferred()

		self.mixList = []
		self.prvList = []

		self.seenMacs = set()
		self.bounceInformation = {}
		# self.expectedACK = set()

		self.heartbeatsSent = set()
		self.numHeartbeatsReceived = 0
		self.tagedHeartbeat = {}

		self.bProcessed = 0
		self.pProcessed = 0
		self.otherProc = 0
		# number of all messages mixed together at a time a message is leaving
		self.totalCounter = 0 
		# number of messages which are in the mixnode between previous message leaving and current message leaving
		self.partialCounter = 0

		self.measurments = []
		self.anonSetSizeAll = []
		self.savedLatency = []

		self.PATH_LENGTH = 3
		self.EXP_PARAMS_DELAY = (float(_PARAMS["parametersMixnodes"]["EXP_PARAMS_DELAY"]), None)
		self.EXP_PARAMS_LOOPS = (float(_PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"]), None)
		self.TAGED_HEARTBEATS = _PARAMS["parametersMixnodes"]["TAGED_HEARTBEATS"]
		self.TESTMODE = False

		self.processQueue = ProcessQueue()
		self.resolvedAdrs = {}

		# ====================SPHINX VALUES==================
		self.params = SphinxParams(header_len=1024)

	def startProtocol(self):
		reactor.suggestThreadPoolSize(50)

		print "[%s] > Start protocol" % self.name
		reactor.callLater(10.0, self.turnOnProcessing)

		if self.TAGED_HEARTBEATS == "True":
			self.d.addCallback(self.turnOnTagedHeartbeats)
		else:
			self.d.addCallback(self.turnOnHeartbeats)
		self.d.addErrback(self.errbackHeartbeats)

		# self.turnOnReliableUDP()
		self.readInData('example.db')
		self.turnOnMeasurments()
		self.saveMeasurments()
		
	def stopProtocol(self):
		print "> Protocol stoped."

	def turnOnProcessing(self):
		self.processQueue.get().addCallback(self.do_PROCESS)

	def turnOnTagedHeartbeats(self, mixnet):
		interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
		reactor.callLater(interval, self.sendTagedMessage)

		lc2 = task.LoopingCall(self.saveLatency)
		lc2.start(SAVE_MEASURMENTS_TIME, False)

	def turnOnHeartbeats(self, mixnet):
		""" Function starts a loop calling hearbeat sending.

				Args:
				mixnet (list): list of active mixnodes in the network.
		"""
		interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
		reactor.callLater(interval, self.sendHeartbeat, mixnet)

	def errbackHeartbeats(self, failure):
		print "> Mixnode Errback during sending heartbeat: ", failure

	def datagramReceived(self, data, (host, port)):
		try:
			self.processQueue.put((data, (host, port)))
			self.totalCounter += 1
			self.partialCounter += 1
		except Exception, e:
			print "[%s] > ERROR Datagram Received: %s " % (self.name, str(e))

	def do_PROCESS(self, (data, (host, port))):
		self.processMessage(data, (host, port))
		self.bProcessed += 1

		try:
			reactor.callFromThread(self.get_and_addCallback, self.do_PROCESS)
		except Exception, e:
			print "[%s] > ERROR do_PROCESS: %s" % (self.name, str(e))

	def get_and_addCallback(self, f):
		self.processQueue.get().addCallback(f)

	def processMessage(self, data, (host, port)):
		if data[:4] == "ROUT":
			try:
				(header, body) = petlib.pack.decode(data[4:])
				self.do_ROUT((header, body), (host, port))
			except Exception, e:
				print "ERROR processMessage: ", str(e)
		elif data[:4] == "ACKN":
			#if data in self.expectedACK:
			#	self.expectedACK.remove(data)
			#	self.otherProc += 1
			pass
		else:
			print "[%s] > Processing Message - message not recognized" % self.name

	# def send_ack(self, msg, (host, port)):
	# 	reactor.callLater(0.0, self.sendMessage, msg, (host, port))

	def process_sphinx_packet(self, message):
		header, body = message
		ret_val = sphinx_process(self.params, self.privk, header, body)
		return ret_val

	def do_ROUT(self, data, (host, port)):
		try:
			peeledData = self.process_sphinx_packet(data)
		except Exception, e:
			print "ERROR - during message decryption: ", str(e)
		else:
			(tag, info, (header, body)) = peeledData
			# routing_flag, meta_info = PFdecode(self.params, info)
			routing = PFdecode(self.params, info)
			if routing[0] == Relay_flag:
				routing_flag, meta_info = routing
				next_addr, dropFlag, typeFlag, delay, next_name = meta_info
				if typeFlag == 'P':
					self.pProcessed += 1
				try:
					reactor.callFromThread(self.send_or_delay, delay, "ROUT" + petlib.pack.encode((header, body)), next_addr)
				except Exception, e:
					print "ERROR during message processing", str(e)
			elif routing[0] == Dest_flag:
				dest, message = receive_forward(self.params, body)
				if dest[-1] == self.name:
					if message.startswith('TAG'):
						self.measureLatency(message)
					if message.startswith('HT'):
						# print "[%s] > Heartbeat looped pack" % self.name
						pass
				else:
					raise Exception("Destionation did not match")
			else:
				print 'Flag not recognized' 

	def send_or_delay(self, delay, packet, (xtoHost, xtoPort)):
		if delay > 0:
			reactor.callLater(delay, self.sendMessage, packet, (xtoHost, xtoPort))
		else:
			reactor.callLater(0.0, self.sendMessage, packet, (xtoHost, xtoPort))


	def checkMac(self, mac):
		"""Function validates is the mac of the received message was previously seen

			Args:
			mac (str): value of mac which should be compared with the already seen macs.
		"""
		if mac in self.seenMacs:
			return True
		return False

	def turnOnReliableUDP(self):
		""" Function checks every timestamp which ACKs where received for the sent packets."""
		lc = task.LoopingCall(self.ackListener)
		lc.start(TIME_ACK, False)

	def errbackReliableUDP(self, failure):
		print "> Errback of mix Reliable UDP took care of ", failure


	def sendMessage(self, data, (host, port)):
		""" Function sends the message to the specified place in the network.

			Args:
			data (str): data to be transported,
			host (str): host of the destination,
			port (int): port of the destination.
		"""
		def send_to_ip(IPaddrs):
			self.transport.write(data, (IPaddrs, port))
			self.anonSetSizeAll.append((self.totalCounter, self.partialCounter))
			self.totalCounter -= 1
			self.partialCounter = 0
			self.resolvedAdrs[host] = IPaddrs
		try:
			self.transport.write(data, (self.resolvedAdrs[host], port))
			self.anonSetSizeAll.append((self.totalCounter, self.partialCounter))
			self.totalCounter -= 1
			self.partialCounter = 0 
		except KeyError, e:
			# Resolve and call the send function
			reactor.resolve(host).addCallback(send_to_ip)

	# ================================HEARTBEATS USING SPHINX=================================
	def packIntoSphinxPacket(self, message, path, typeFlag=None):
		keys_nodes = [n.pubk for n in path]
		nodes_routing = []

		for i in range(len(path)):
			delay = sf.sampleFromExponential(self.EXP_PARAMS_DELAY)
			nodes_routing.append(Nenc([(path[i].host, path[i].port), False, typeFlag, delay, path[i].name]))

		dest = (self.host, self.port, self.name)
		header, body = create_forward_message(self.params, nodes_routing, keys_nodes, dest, message)
		return (header, body)


	def createSphinxHeartbeat(self, mixes, timestamp, typeFlag=None):
		""" The message creates the content of a heartbeat message which is later encapsulated in the packet format.

			Args:
			mixes (list): list os mixnode path which will be used to forward the heartbeat message,
			timestamp (time) : timestamp which will be included inside the heartbeat message.
		"""
		try:
			heartMsg = sf.generateRandomNoise(NOISE_LENGTH)
			path = mixes + [self]
			print path
			header, body = self.packIntoSphinxPacket('HT' + heartMsg, path, typeFlag)
			return (header, body)
		except Exception, e:
			print "[%s] > Error during hearbeat creating: %s" % (self.name, str(e))
			return None

	def sendHeartbeat(self, mixnet, predefinedPath=None):
		""" Mixnode sends a heartbeat message.

				Args:
				mixnet (list): list of active mixnodes in the network,
				selectPath (boolean): a flag informing if the path should be selected randomly or not.
		"""
		if not mixnet:
			raise Exception("SendHeartbeat: list of active mixes in the Network is empty!")
		else:
			try:
				mixes = predefinedPath if predefinedPath else self.takePathSequence(mixnet, self.PATH_LENGTH)
			except ValueError, e:
				print "ERROR sendHeartbeat: ", str(e)
			else:
				if self.TESTMODE:
					header, body = self.createSphinxHeartbeat(mixes, time.time(), 'H')
				else:
					header, body = self.createSphinxHeartbeat(mixes, time.time())
				self.sendMessage("ROUT" + petlib.pack.encode((header, body)), (mixes[0].host, mixes[0].port))
				interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
				reactor.callLater(interval, self.sendHeartbeat, mixnet)
	# ========================================================================================

	def sendTagedMessage(self):
		try:
			mixes = self.takePathSequence(self.mixList, self.PATH_LENGTH)
			path = mixes + [self]
			tagedMessage = "TAG" + sf.generateRandomNoise(NOISE_LENGTH)
			header, body = self.packIntoSphinxPacket(tagedMessage, path)
			self.sendMessage("ROUT" + petlib.pack.encode((header, body)), (path[0].host, path[0].port))
			self.tagedHeartbeat[tagedMessage] = time.time()

			interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
			reactor.callLater(interval, self.sendTagedMessage)
		except Exception, e:
			print "ERROR: Send tagged message: ", str(e)

	def measureLatency(self, msg):
		try:
			if msg in self.tagedHeartbeat:
				latency = float(time.time()) - float(self.tagedHeartbeat[msg])
				del self.tagedHeartbeat[msg]
				self.savedLatency.append(latency)
		except Exception, e:
			print str(e)

	def saveLatency(self):
		try:
			with open('latency.csv', 'ab') as outfile:
				csvW = csv.writer(outfile, delimiter='\n')
				csvW.writerow(self.savedLatency)
			self.savedLatency = []
		except Exception, e:
			print str(e)

	def takePathSequence(self, mixnet, length):
		""" Function takes path sequence of a given length. If the length is 
			bigger than the number of registered mixnodes in the network, all
			mixnodes are used to build a path.
		"""
		if len(mixnet) > length:
			randomPath = random.sample(mixnet, length)
		else:
			randomPath = mixnet + []
			numpy.random.shuffle(randomPath) #TO DO: better and more secure
		randomPath.insert(length, random.choice(self.prvList))
		return randomPath

	def printMixData(self):
		"""Function prints the keypair information of a mixnode."""
		print "OPERATED MIXNODE: Name: %s, address: (%d, %s), PubKey: %s" % (self.name, self.port, self.host, self.pubk)

	# def ackListener(self):
	# 	""" Function checks if mixnode received the acknowledgments for the sent packets. """

	# 	if self.expectedACK:
	# 		ack = self.expectedACK.pop()
	# 		if ack in self.bounceInformation:
	# 			try:
	# 				self.do_BOUNCE(self.bounceInformation[ack])
	# 			except Exception, e:
	# 				print "ERROR during ACK checking: ", str(e)
	# 		else:
	# 			print "> For this ACK there is no bounce message."

	def heartbeatListener(self, heartbeat):
		""" Function checks the incoming heartbeat messages if and when this heartbeat was sent.

				Args:
				hearbeat (str): heartbeat message + identifier
		"""
		for element in self.heartbeatsSent:
			if heartbeat in element:
				# print "[%s] > Heartbeat Listener received back a heartbeat. " % self.name
				self.numHeartbeatsReceived += 1
				self.heartbeatsSent.remove(element)

	def saveInDatabase(self, database):
		""" Function saves mixnode's public information in a database.

				Args:
				database (str) - dir and name of the database.
		"""
		try:
			db = sqlite3.connect(database)
			c = db.cursor()
			c.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, name text, port integer, host text, pubk blob)'''%"Mixnodes")
			insertQuery = "INSERT INTO Mixnodes VALUES (?, ?, ?, ?, ?)"
			c.execute(insertQuery, [None, self.name, self.port, self.host, sqlite3.Binary(petlib.pack.encode(self.pubk))])
			db.commit()
			db.close()
		except Exception, e:
			print "[%s] > Error during saving in database: %s" % (self.name, str(e))

	def readMixnodesFromDatabase(self, database):
		"""	Function reads the public information of registered mixnodes from the database.

				Args:
				database (str) - dir and name of the database.
		"""
		try:
			db = sqlite3.connect(database)
			c = db.cursor()
			c.execute("SELECT * FROM Mixnodes")
			mixnodes = c.fetchall()
			for m in mixnodes:
				self.mixList.append(format3.Mix(m[1], m[2], m[3], petlib.pack.decode(m[4])))
		except Exception, e:
			print "[%s] > Error during reading from the database: %s" % (self.name, str(e))


	def readProvidersFromDatabase(self, database):
		""" Function reads the public information of registered providers from the database.

				Args:
				database (str) - dir and name of the database
		"""
		try:
			db = sqlite3.connect(database)
			c = db.cursor()
			c.execute("SELECT * FROM Providers")
			fetched = c.fetchall()
			for p in fetched:
				self.prvList.append(format3.Mix(p[1], p[2], p[3], petlib.pack.decode(p[4])))
		except Exception, e:
			print "[%s] > Error during reading from the database: %s" % (self.name, str(e))

	def readInData(self, database):
		self.readMixnodesFromDatabase(database)
		self.readProvidersFromDatabase(database)
		self.d.callback(self.mixList)

	def takePublicInfo(self):
		return petlib.pack.encode([self.name, self.port, self.host, self.pubk])

	def aes_enc_dec(self, key, iv, inputVal):
		"""A helper function which implements 
		the AES-128 encryption in counter mode CTR

				Args:
				key (str): enc/dec key,
				iv (str): initialization vector,
				inputVal (str): message which should be encrypted / decrypted.
		"""

		aes = Cipher("AES-128-CTR")
		enc = aes.enc(key, iv)
		output = enc.update(inputVal)
		output += enc.finalize()
		return output

	def turnOnMeasurments(self):
		lc = task.LoopingCall(self.takeMeasurments)
		lc.start(MEASURE_TIME, False)

	def takeMeasurments(self):
		self.measurments.append([self.bProcessed, self.pProcessed, self.otherProc])
		self.bProcessed = 0
		self.pProcessed = 0
		self.otherProc = 0

	def saveMeasurments(self):
		lc = task.LoopingCall(self.save_to_file)
		lc.start(SAVE_MEASURMENTS_TIME, False)

	def save_to_file(self):
		try:
			with open("performanceMixnode.csv", "ab") as outfile:
				csvW = csv.writer(outfile, delimiter=',')
				csvW.writerows(self.measurments)
			self.measurments = []
		except Exception, e:
			print "Error while saving: ", str(e)
		try:
			with open("anonSet.csv", "ab") as outfile:
				csvW = csv.writer(outfile)
				csvW.writerow(['TotalCounter', 'PartialCounter'])
				for row in self.anonSetSizeAll:
					csvW.writerow(row)
			self.anonSetSizeAll = []
		except Exception, e:
			print "Error while saving: ", str(e)

