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

with open('config.json') as infile:
	_PARAMS = json.load(infile) 

TIME_ACK = float(_PARAMS["parametersMixnodes"]["TIME_ACK"])
TIME_FLUSH = float(_PARAMS["parametersMixnodes"]["TIME_FLUSH"])
TIME_CLEAN = float(_PARAMS["parametersMixnodes"]["TIME_CLEAN"])
MAX_DELAY_TIME = float(_PARAMS["parametersMixnodes"]["MAX_DELAY_TIME"])
NOISE_LENGTH = float(_PARAMS["parametersMixnodes"]["NOISE_LENGTH"])

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
		self.seenElements = set()
		self.bounceInformation = {}
		# self.expectedACK = set()

		self.heartbeatsSent = set()
		self.numHeartbeatsReceived = 0
		self.hbProcessed = 0
		self.tagedHeartbeat = {}

		self.savedElements = set()

		self.bReceived = 0
		self.bProcessed = 0
		self.gbProcessed = 0
		self.pProcessed = 0
		self.otherProc = 0
		self.hbSent = {}
		self.measurments = []

		self.PATH_LENGTH = 3
		self.EXP_PARAMS_DELAY = (float(_PARAMS["parametersMixnodes"]["EXP_PARAMS_DELAY"]), None)
		self.EXP_PARAMS_LOOPS = (float(_PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"]), None)
		self.TAGED_HEARTBEATS = _PARAMS["parametersMixnodes"]["TAGED_HEARTBEATS"]

		self.processQueue = ProcessQueue()
		self.resolvedAdrs = {}
		self.savedLatency = []
		#self.timeits = []
		self.mixedTogether = 0
		self.anonSetSizeAll = []

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
		print "> Stop Protocol"

	def turnOnProcessing(self):
		self.processQueue.get().addCallback(self.do_PROCESS)

	def turnOnTagedHeartbeats(self, mixnet):
		interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
		reactor.callLater(interval, self.sendTagedMessage)

		lc2 = task.LoopingCall(self.saveLatency)
		lc2.start(300, False)

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
			self.bReceived += 1
		except Exception, e:
			print "[%s] > ERROR: %s " % (self.name, str(e))

	def do_PROCESS(self, (data, (host, port))):
		self.processMessage(data, (host, port))
		self.bProcessed += 1

		try:
			reactor.callFromThread(self.get_and_addCallback, self.do_PROCESS)
		except Exception, e:
			print "[%s] > ERROR: %s" % (self.name, str(e))

	def get_and_addCallback(self, f):
		self.processQueue.get().addCallback(f)

	def processMessage(self, data, (host, port)):
		#ts = time.time()
		if data[:4] == "ROUT":
			try:
				idt, msgData = petlib.pack.decode(data[4:])
				self.do_ROUT(msgData, (host, port))
				self.gbProcessed += 1
			except Exception, e:
				print "ERROR: ", str(e)
		elif data[:4] == "ACKN":
			#if data in self.expectedACK:
			#	self.expectedACK.remove(data)
			self.otherProc += 1
		else:
			print "Processing Message - message not recognized"
		#te = time.time()
		#self.timeits.append(te-ts)

	# def send_ack(self, msg, (host, port)):
	# 	reactor.callLater(0.0, self.sendMessage, msg, (host, port))

	def do_INFO(self, data, (host, port)):
		""" Mixnodes processes the INFO request

			Args:
			data (str): data send in this request,
			(host, port): a tuple of string and int representing the address of the sender of the rqs.
		"""

		resp = "RINF" + petlib.pack.encode([self.name, self.port, self.host, self.pubk])
		self.sendMessage(resp, (host, port))

	def do_ROUT(self, data, (host, port), tag=None):
		""" Mixnodes processes the ROUT request by decrypting a certain layer of encryption, validating the message
		and adding the message to the pool of messages to be sent

			Args:
			data (str): data send in this request,
			(host, port): a tuple of string and int representing the address of the sender of the rqs
		"""
		try:
			peeledData = self.mix_operate(self.setup, data)
		except Exception, e:
			print "ERROR: ", str(e)
		else:
			if peeledData:
				(xtoPort, xtoHost, xtoName), forw_msg, idt, delay = peeledData
				if (xtoName is None and xtoPort is None and xtoHost is None):
					print "[%s] > Message discarded" % self.name
				else:
					try:
						reactor.callFromThread(self.send_or_delay, delay, petlib.pack.encode((idt, forw_msg)), (xtoHost, xtoPort))
						#self.expectedACK.add("ACKN"+idt)
						#reactor.callFromThread(self.send_ack, "ACKN", (host, port))
					except Exception, e:
						print "ERROR during ROUT processing: ", str(e)

	def do_BOUNCE(self, data):
		"""	Mixnode processes the BOUNCE message. This function is called, when the mixnode did not receive the ACK for
		a particular transported packet.

			Args:
			data (str): the saved packet data which should be processed as a bounce.
		"""

		print "> Operating on bounce."
		try:
			peeledData = self.mix_operate(self.setup, data)
		except Exception, e:
			print "ERROR: ", str(e)
		else:
			if peeledData:
				(xtoPort, xtoHost, xtoName), back_msg, idt, delay = peeledData
				if (xtoPort is None and xtoHost is None and xtoName is None) and forw_msg is None:
					print "[%s] > Message discarded" % self.name
				else:
					try:
						reactor.callFromThread(self.send_or_delay, delay, petlib.pack.encode((idt, back_msg)), (xtoHost, xtoPort))
						# self.expectedACK.add("ACKN"+idt)
					except Exception, e:
						print "ERROR during bounce processing: ", str(e)

	def send_or_delay(self, delay, packet, (xtoHost, xtoPort)):
		self.mixedTogether += 1
		if delay > 0:
			reactor.callLater(delay, self.sendMessage, "ROUT" + packet, (xtoHost, xtoPort))
		else:
			reactor.callLater(0.0, self.sendMessage, "ROUT" + packet, (xtoHost, xtoPort))

	def do_RINF(self, data):
		""" Mixnodes processes the RINF request, which returns the network information requested by the user

			Args:
			data (str): data send in this request.
		"""

		for element in petlib.pack.decode(data):
			self.mixList.append(format3.Mix(element[0], element[1], element[2], element[3]))
		if format3.Mix(self.name, self.port, self.host, self.pubk) in self.mixList:
			self.mixList.remove(format3.Mix(self.name, self.port, self.host, self.pubk))

	def mix_operate(self, setup, message):
		""" Mixnode operates on the received packet. It removes the encryption layer of the forward header, builts up the
		new layer of the backward header and performs other collateral operations.

			Args:
			setup (tuple): a setup of a group used in the protocol,
			message (list): a received message which should be enc/dec.
		"""

		G, o, g, o_bytes = setup
		elem = message[0]
		forward = message[1]
		backward = message[2]
		element = EcPt.from_binary(elem, G)
		#if element in self.seenElements:
		#	print "[%s] > Element already seen. This might be a duplicate. Message dropped." % self.name
		#	return None
		#else:
		#	self.seenElements.add(element)
		aes = Cipher("AES-128-CTR")

		# Derive first key
		k1 = format3.KDF((self.privk * element).export())

		# Derive the blinding factor
		b = Bn.from_binary(k1.b) % o
		new_element = b * element
		# Check the forward MAC
		expected_mac = forward[:20]
		# if self.checkMac(expected_mac):
		#	print "[%s] > MAC already seen. Message droped." % self.name
		#	return None
		ciphertext_metadata, ciphertext_body = msgpack.unpackb(forward[20:])
		mac1 = hmac.new(k1.kmac, ciphertext_metadata, digestmod=sha1).digest()
		if not (expected_mac == mac1):
			raise Exception("> WRONG MAC")
		# self.seenMacs.add(mac1)

		# Decrypt the forward message
		enc_metadata = aes.dec(k1.kenc, k1.iv)
		enc_body = aes.dec(k1.kenc, k1.iv)
		pt = enc_body.update(ciphertext_body)
		pt += enc_body.finalize()
		header_en = enc_metadata.update(ciphertext_metadata)
		header_en += enc_metadata.finalize()
		header = petlib.pack.decode(header_en)

		if pt.startswith('HT'):
			if pt[2:] in self.hbSent:
				self.hbSent[pt[2:]] = True
			if pt.startswith('HTTAG'):
				self.measureLatency(pt)
			self.hbProcessed += 1
			return None
		else:
			dropMessage = header[1]
			if dropMessage == '1':
				# print "[%s] > Drop message. This message is droped now." % self.name
				return None

			# typeFlag - auxiliary flag which tells what type of message it is; only used for statistics; 
			typeFlag = header[2]
			if typeFlag == "P":
				self.pProcessed += 1

			# delay - message delay
			delay = header[3]

			# Parse the forward message
			xcode = header[0]
			if not (xcode == "0" or xcode == "1"):
				raise Exception("> Wrong routing code")

			idt = str(uuid.uuid1())
			if xcode == "0":
				xfrom, xto, the_bs, new_forw = header[4], header[5], header[6], pt

				old_bs = the_bs
				if old_bs == Bn(1):
					new_element = element

				k2 = format3.KDF(((self.privk * old_bs) * element).export())
				enc_metadata = aes.dec(k2.kenc, k2.iv)
				enc_body = aes.dec(k2.kenc, k2.iv)

				metadata = petlib.pack.encode(["1", '0', typeFlag, delay, xto, xfrom])
				new_back_metadata = enc_metadata.update(metadata)
				new_back_metadata += enc_metadata.finalize()
				new_back_body = enc_body.update(backward)
				new_back_body += enc_body.finalize()
				new_back_body = msgpack.packb([new_back_metadata, new_back_body])

				mac_back = hmac.new(k2.kmac, new_back_metadata, digestmod=sha1).digest()

				new_back = mac_back + new_back_body

				ret_elem = old_bs * element
				ret_forw = new_back
				ret_back = "None"

				# self.bounceInformation["ACKN"+str(idt)] = ([ret_elem.export(), ret_forw, ret_back])
			else:
				xfrom, xto, new_forw = header[4], header[5], pt
				if not (backward == "None"):
					raise Exception("> Backwards header should be None")

				new_back = "None"

			new_element = new_element.export()
			return (xto, [new_element, new_forw, new_back], idt, delay)

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
			self.mixedTogether -= 1
			self.anonSetSizeAll.append(self.mixedTogether)
			self.resolvedAdrs[host] = IPaddrs
		try:
			self.transport.write(data, (self.resolvedAdrs[host], port))
			self.mixedTogether -= 1
			self.anonSetSizeAll.append(self.mixedTogether)
		except KeyError, e:
			# Resolve and call the send function
			reactor.resolve(host).addCallback(send_to_ip)

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
				print "ERROR: ", str(e)
			else:
				heartbeatPacket = self.createHeartbeat(mixes, time.time())
				self.mixedTogether += 1
				self.sendMessage("ROUT" + petlib.pack.encode((str(uuid.uuid1()), heartbeatPacket)), (mixes[0].host, mixes[0].port))
				interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
				reactor.callLater(interval, self.sendHeartbeat, mixnet)

	def createHeartbeat(self, mixes, timestamp):
		""" The message creates the content of a heartbeat message which is later encapsulated in the packet format.

			Args:
			mixes (list): list os mixnode path which will be used to forward the heartbeat message,
			timestamp (time) : timestamp which will be included inside the heartbeat message.
		"""
		try:
			heartMsg = sf.generateRandomNoise(NOISE_LENGTH)
			delay = [sf.sampleFromExponential(self.EXP_PARAMS_DELAY) for _ in range(len(mixes)+1)]
			packet = format3.create_mixpacket_format(self, self, mixes, self.setup, 'HT'+heartMsg, 'HB'+heartMsg, delay, False, typeFlag='H')
			self.hbSent[heartMsg] = False
			return packet[1:]
		except Exception, e:
			print "[%s] > Error during hearbeat creating: %s" % (self.name, str(e))

	def sendTagedMessage(self):
		try:
			mixes = self.takePathSequence(self.mixList, self.PATH_LENGTH)
			tagedMessage = "TAG" + sf.generateRandomNoise(NOISE_LENGTH)
			delay = [sf.sampleFromExponential(self.EXP_PARAMS_DELAY) for _ in range(len(mixes)+1)]
			message = format3.create_mixpacket_format(self, self, mixes, self.setup,  'HT'+tagedMessage, 'HB'+tagedMessage, delay, False, typeFlag = 'P')
			self.mixedTogether += 1
			self.sendMessage("ROUT" + petlib.pack.encode((str(uuid.uuid1()), message[1:])), (mixes[0].host, mixes[0].port))
			self.tagedHeartbeat[tagedMessage] = time.time()

			interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
			reactor.callLater(interval, self.sendTagedMessage)
		except Exception, e:
			print "ERROR: Send tagged message: ", str(e)

	def measureLatency(self, msg):
		try:
			if msg[2:] in self.tagedHeartbeat:
				latency = float(time.time()) - float(self.tagedHeartbeat[msg[2:]])
				del self.tagedHeartbeat[msg[2:]]
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
			print "[%s] > Error during saveing in database: %s" % (self.name, str(e))

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
		lc.start(60, False)

	def takeMeasurments(self):
		self.measurments.append([self.bProcessed, self.gbProcessed, self.bReceived, self.pProcessed, len(self.hbSent), sum(self.hbSent.values()), self.otherProc, self.mixedTogether, self.hbProcessed])
		self.bProcessed = 0
		self.gbProcessed = 0
		self.bReceived = 0
		self.pProcessed = 0
		self.otherProc = 0
		self.hbSent = {}
		self.hbProcessed = 0

	def saveMeasurments(self):
		lc = task.LoopingCall(self.save_to_file)
		lc.start(300, False)

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
				csvW = csv.writer(outfile, delimiter='\n')
				csvW.writerow(self.anonSetSizeAll)
			self.anonSetSizeAll = []
		except Exception, e:
			print "Error while saving: ", str(e)

