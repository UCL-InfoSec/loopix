from provider import Provider

import csv
import databaseConnect as dc
import format3
from hashlib import sha512, sha1
import hmac
import io
import json
import msgpack
import numpy
import os
from petlib.cipher import Cipher
from petlib.ec import EcPt, Bn, EcGroup
import petlib.pack
from processQueue import ProcessQueue
import random
import time
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, protocol, task, defer, threads
from twisted.internet.defer import DeferredQueue, DeferredLock
from types import *
import sqlite3
import string
import supportFunctions as sf
import sys
from sets import Set
import uuid
import resource


with open('config.json') as infile:
    _PARAMS = json.load(infile)

TIME_PULL = float(_PARAMS["parametersClients"]["TIME_PULL"])
NOISE_LENGTH = float(_PARAMS["parametersClients"]["NOISE_LENGTH"])
FAKE_MESSAGING = True if _PARAMS["parametersClients"]["FAKE_MESSAGING"] == "True" else False
MEASURE_TIME = float(_PARAMS["parametersClients"]["MEASURE_TIME"])
SAVE_MEASURMENTS_TIME = float(_PARAMS["parametersClients"]["SAVE_MEASURMENTS_TIME"])

class Client(DatagramProtocol):
    def __init__(self, setup, name, port, host, testUser=False,
                 providerId=None, privk=None, pubk=None):
        """A class representing a user client."""

        # Public information about mixnode
        self.name = name
        self.port = port
        self.host = host
        assert type(self.port) is IntType
        assert type(self.host) is StringType

        # Provider information
        self.providerId = providerId
        
        # Setup value
        self.G, self.o, self.g, self.o_bytes = setup
        self.setup = setup

        self.privk = privk or self.o.random()
        self.pubk = pubk or (self.privk * self.g)

        # Key generated for additional encryption
        self.keys = sha512(self.privk.binary()).digest()
        self.kenc = self.keys[:16]
        self.iv = self.keys[16:32]
        self.aes = Cipher.aes_128_gcm()

        self.d = defer.Deferred()

        # Information about active mixnodes and other users in the network
        self.mixnet = []
        self.usersPubs = []

        self.sentElements = set()
        self.heartbeatsSent = set()
        self.buffer = []


        self.PATH_LENGTH = int(_PARAMS["parametersClients"]["PATH_LENGTH"])
        self.EXP_PARAMS_PAYLOAD = (float(_PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"]), None)
        self.EXP_PARAMS_LOOPS = (float(_PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"]), None)
        self.EXP_PARAMS_COVER = (float(_PARAMS["parametersClients"]["EXP_PARAMS_COVER"]), None)
        self.EXP_PARAMS_DELAY = (float(_PARAMS["parametersClients"]["EXP_PARAMS_DELAY"]), None)
        self.TESTMODE = True if _PARAMS["parametersClients"]["TESTMODE"] == "True" else False
        self.TESTUSER = True if _PARAMS["parametersClients"]["TEST_USER"] == "True" else False

        self.numHeartbeatsSent = 0
        self.numHeartbeatsReceived = 0
        self.numMessagesSent = 0

        #self.receivedQueue = DeferredQueue()
        self.processQueue = ProcessQueue()
        self.sendMeasurments = []
        self.resolvedAdrs = {}

    def startProtocol(self):
        print "[%s] > Start Protocol" % self.name
        print "TEST USER MODE: ", self.TESTUSER
        self.provider = self.takeProvidersData("example.db", self.providerId)
        print "Provider: ", self.provider

        self.sendPing()

        self.readInData("example.db")
        reactor.callLater(100.0, self.turnOnProcessing)

    def turnOnProcessing(self):
        #self.receivedQueue.get().addCallback(self.do_PROCESS)
        self.processQueue.get().addCallback(self.do_PROCESS)

    def sendPing(self):
        self.send("PING"+self.name, (self.provider.host, self.provider.port))

    def stopProtocol(self):
        print "[%s] > Stop Protocol" % self.name

    def pullMessages(self):
        """ Sends a request to pull messages from the provider."""

        self.send("PING"+self.name, (self.provider.host, self.provider.port))
        self.send("PULL_MSG"+self.name, (self.provider.host, self.provider.port))

    def turnOnMessagePulling(self):
        """ Function turns on a loop which pulls messages from the provider every timestamp."""

        lc = task.LoopingCall(self.pullMessages)
        lc.start(TIME_PULL)

    def turnOnMessaging(self, mixList):
        """ Function turns on sending cover traffic and real message buffer checking.

            Args:
                mixList (list): a list of active mixnodes in the network.
        """
        self.measureSentMessages()
        self.save_measurments()
        self.turnOnCoverLoops(mixList)
        self.turnOnCoverMsg(mixList)
        self.turnOnBufferChecking(mixList)
        # ====== This is generating fake messages to fake reall traffic=====
        if FAKE_MESSAGING:
            self.turnOnFakeMessaging()
        # ==================================================================

    def turnOnBufferChecking(self, mixList):
        """ Function turns on a loop checking the buffer with messages.

            Args:
                mixList (list): a list of active mixnodes in the network.

        """

        interval = sf.sampleFromExponential(self.EXP_PARAMS_PAYLOAD)
        if self.TESTMODE:
            reactor.callLater(interval, self.generateFakePayload)
        else:
            reactor.callLater(interval, self.checkBuffer, mixList)

    def turnOnCoverLoops(self, mixList):
        """ Function turns on a loop generating a loop cover traffic.

            Args:
                mixList (list): a list of active mixnodes in the network.
        """

        if self.EXP_PARAMS_LOOPS > 0.0:
            interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
            if self.TESTMODE:
                reactor.callLater(interval, self.generateFakeLoopTraffic)
            else:
                reactor.callLater(interval, self.generateLoopTraffic, mixList)

    def turnOnCoverMsg(self, mixList):
        """ Function turns on a loop generating a drop cover traffic.

            Args:
                mixList (list): a list of active mixnodes in the network.
        """
        if self.EXP_PARAMS_COVER > 0.0:
            interval = sf.sampleFromExponential(self.EXP_PARAMS_COVER)
            if self.TESTMODE:
                reactor.callLater(interval, self.generateFakeCoverTraffic)
            else:
                reactor.callLater(interval, self.generateCoverTraffic, mixList)
        else:
            pass

    def checkBuffer(self, mixList):
        """ Function sends message from buffer or drop messages.

                Args:
                mixList (list): a list of active mixnodes in the network.
        """

        try:
            if len(self.buffer) > 0:
                message, addr = self.buffer.pop(0)
                self.send(message, addr)
            else:
                self.sendDropMessage(mixList)
            interval = sf.sampleFromExponential(self.EXP_PARAMS_PAYLOAD)
            reactor.callLater(interval, self.checkBuffer, mixList)
        except Exception, e:
                print "[%s] > ERROR: Something went wrong during buffer checking: %s" % (self.name, str(e))

    def generateLoopTraffic(self, mixList):
        """ Function sends hearbeat message following the Poisson distribution
        with parameters POISSON_PARAMS_LOOPS.

            Args:
            mixList (list): a list of active mixnodes in the network.
        """
        try:
            self.sendHeartBeat(mixList, time.time())
            interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
            reactor.callLater(interval, self.generateLoopTraffic, mixList)
        except Exception, e:
            print "[%s] > ERROR: Loop cover traffic, something went wrong: %s" % (self.name, str(e))

    def generateCoverTraffic(self, mixList):
        """ Function sends hearbeat message following the Poisson distribution
        with parameters POISSON_PARAMS_COVER.

            Args:
            mixList (list): a list of active mixnodes in the network.
        """
        try:
            self.sendDropMessage(mixList)
            interval = sf.sampleFromExponential(self.EXP_PARAMS_COVER)
            reactor.callLater(interval, self.generateCoverTraffic, mixList)
        except Exception, e:
            print "[%s] > ERROR: Drop cover traffic, something went wrong: %s" % (self.name, str(e))

    def generateFakeLoopTraffic(self):
        try:
            packet, addr = random.choice(tuple(self.testHeartbeats))
            self.send("ROUT" + packet, addr)
            interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
            reactor.callLater(interval, self.generateFakeLoopTraffic)
        except Exception, e:
            print "ERROR: ", str(e)

    def generateFakeCoverTraffic(self):
        try:
            packet, addr = random.choice(tuple(self.testDrops))
            self.send("ROUT" + packet, addr)
            interval = sf.sampleFromExponential(self.EXP_PARAMS_COVER)
            reactor.callLater(interval, self.generateFakeCoverTraffic)
        except Exception, e:
            print "ERROR", str(e)

    def generateFakePayload(self):
        try:
            packet, addr = random.choice(tuple(self.testPayload))
            self.send("ROUT" + packet, addr)
            interval = sf.sampleFromExponential(self.EXP_PARAMS_PAYLOAD)
            reactor.callLater(interval, self.generateFakePayload)
        except Exception, e:
            print "ERROR: ", str(e)


    def datagramReceived(self, data, (host, port)):
        #self.receivedQueue.put((data, (host, port)))
        # print "[%s] > datagram Received" % self.name
        try:
            self.processQueue.put((data, (host, port)))
        except Exception, e:
            print "[%s] > ERROR: %s " % (self.name, str(e))

    def do_PROCESS(self, (data, (host, port))): 
        self.processMessage(data, (host, port))
        #self.receivedQueue.get().addCallback(self.do_PROCESS)
        
        try:
            reactor.callFromThread(self.get_and_addCallback, self.do_PROCESS)
        except Exception, e:
            print "[%s] > ERROR: %s" % (self.name, str(e))

    def get_and_addCallback(self, f):
        self.processQueue.get().addCallback(f)

    def processMessage(self, data, (host, port)):
        """ Function starts to processe a received message.

            Args:
            data (str) - a string content of a received packet,
            host (str) - host of the sender,
            port (int) - port of the sender
        """        
        if data[:4] == "PMSG":
            self.do_PMSG(data[4:], host, port)
        if data == "NOMSG":
            print "[%s] > Received NOMSG." % self.name
        if data == "NOASG":
            print "[%s] > Received NOASG from %s" % (self.name, host)

    def do_PMSG(self, data, host, port):

        try:
            encMsg, timestamp = petlib.pack.decode(data)
            msg = self.readMessage(encMsg, (host, port))
            #print "[%s] > New message unpacked: " % self.name
        except Exception, e:
            print "[%s] > ERROR: Message reading error: %s" % (self.name, str(e))
            print data

    def makePacket(self, receiver, mixnet, setup, dest_message='', return_message='', dropFlag=False, typeFlag=None):
        """ Function returns an encapsulated message,
        which clients wants to send, into a mixpacket format.

            Args:
            receiver (namedtuple): a tuple including public receivers information,
            mixnet (list): list of mixnodes which the message should traverse through,
            setup (tuple): a setup contaning information of the currently used EC group,
            dest_message (str): message which we want to send to the receiver,
            return_message (str): message which we want to receive in a bounce,
            dropFlag (boolean): flag, if True, this means a cover message should be created.
        """

        path = [self.provider] + mixnet + [receiver.provider]
        current_time = time.time()
        delay = [sf.sampleFromExponential(self.EXP_PARAMS_DELAY) for _ in range(len(path)+1)]
        package = format3.create_mixpacket_format(self, receiver, path, setup, dest_message, return_message, delay, dropFlag, typeFlag)
        self.sentElements.add(package[0])
        return (petlib.pack.encode((str(uuid.uuid1()), package[1:])), (self.provider.host, self.provider.port))

    def createHeartbeat(self, mixes, timestamp):
        """ Function creates a heartbeat - a noise message for which the sender and the receiver are the same entity.

                Args:
                mixes (list): list of mixnodes which the message should go through,
                timestamp (?): a timestamp at which the message was created.
        """
        try:
            heartMsg = sf.generateRandomNoise(NOISE_LENGTH)
            # self.heartbeatsSent.add((heartMsg, '%.5f' % time.time()))
            if self.TESTMODE:
                readyToSentPacket, addr = self.makePacket(self, mixes, self.setup, 'HT'+heartMsg, 'HB'+heartMsg, False, typeFlag='H')
            else:
                readyToSentPacket, addr = self.makePacket(self, mixes, self.setup, 'HT'+heartMsg, 'HB'+heartMsg, False)
            return (readyToSentPacket, addr)
        except Exception, e:
            print "[%s] > ERROR: %s" % (self.name, str(e))
            return None

    def sendHeartBeat(self, mixnet, timestamp, predefinedPath=None):
        """ Function sends a heartbeat message.

                Args:
                mixnet (list): list of active mixnodes in the network which can be used to build a path,
                timestamp (?): ?,
                predefinedPath (list): predefined path through which the message should be forwarded. If None, then
                                the path is selected automatically.
        """
        if not mixnet:
            raise Exception("SendHeartbeat: list of active mixes in the Network is empty!")
        else:
            try:
                mixes = predefinedPath if predefinedPath else self.takePathSequence(mixnet, self.PATH_LENGTH)
                heartbeatData = self.createHeartbeat(mixes, timestamp)
                if heartbeatData:
                    readyPacket, addr = heartbeatData
                    self.send("ROUT" + readyPacket, addr)
                    self.numHeartbeatsSent += 1
                else:
                    print "[%s] > Heartbeat could not be send." % self.name
            except Exception, e:
                print "[%s] > Send heartbeat ERROR: %s" % (self.name, str(e))

    def createDropMessage(self, mixes):
        """ Function creates a drop cover message, which traverse as an usuall message to one of the providers
        and is droped there.

                Args:
                mixes (list): list of mixnodes which should be traversed by the message.
        """
        try:
            randomReceiver = self.selectRandomReceiver()
            randomMessage = sf.generateRandomNoise(NOISE_LENGTH)
            randomBounce = sf.generateRandomNoise(NOISE_LENGTH)
            if self.TESTMODE:
                readyToSentPacket, addr = self.makePacket(randomReceiver, mixes, self.setup, randomMessage, randomBounce, True, typeFlag='D')
            else:
                readyToSentPacket, addr = self.makePacket(randomReceiver, mixes, self.setup, randomMessage, randomBounce, True)
            return (readyToSentPacket, addr)
        except Exception, e:
            print "[%s] > Create drop message ERROR: %s" % (self.name, str(e))
            return None

    def sendDropMessage(self, mixnet, predefinedPath=None):
        """ Function creates a drop cover message.

                Args:
                mixnet (list): list of active mixnodes which can be used to build a path,
                predefinedPath (list): predefined path of the mixnodes which should be traversed by the message.
                    If None, the path is selected automatically.
        """
        try:
            mixes = predefinedPath if predefinedPath else self.takePathSequence(mixnet, self.PATH_LENGTH)
            dropData = self.createDropMessage(mixes)
            if dropData:
                readyPacket, addr = dropData
                self.send("ROUT" + readyPacket, addr)
            else:
                print "[%s] > Drop message could not be send." % self.name
        except ValueError, e:
            print "[%s] > Send drop message ERROR: %s" % (self.name, str(e))
        except Exception, e:
            print "[%s] > Send drop message ERROR: %s" % (self.name, str(e))

    def sendMessage(self, receiver, mixpath, msgF, msgB):
        """ Function allows to buffer a message which we want to send.

                Args:
                receiver - public information of a receiver,
                mixpath (list) - path of mixnodes which should be traversed by the message,
                msgF (str) - message which we want to send,
                msgB (str) - message which is included in a bounce.
        """
        try:
            timestamp = '%.5f' % time.time()
            if self.TESTMODE:
                message, addr = self.makePacket(receiver, mixpath, self.setup,  msgF + timestamp, msgB + timestamp, False, typeFlag = 'P')
            else:
                message, addr = self.makePacket(receiver, mixpath, self.setup,  msgF + timestamp, msgB + timestamp, False)
            self.buffer.append(("ROUT" + message, addr))
        except Exception, e:
            print "[%s] > ERROR: Message could not be buffered for send: %s" % (self.name, str(e))

    def send(self, packet, (host, port)):
        """ Function sends a packet.

            Args:
            packet (str) - packet which we want to send,
            host (str) - destination host,
            port (int) - destination port.
        """

        def send_to_ip(IPAddrs):
            self.transport.write(packet, (IPAddrs, port))
            self.resolvedAdrs[host] = IPAddrs
            self.numMessagesSent += 1

        try:
            self.transport.write(packet, (self.resolvedAdrs[host], port))
            self.numMessagesSent += 1
        except KeyError, e:
            reactor.resolve(host).addCallback(send_to_ip)
        #if host in self.resolvedAdrs:
        #    self.transport.write(packet, (self.resolvedAdrs[host], port))
        #else:
        #    reactor.resolve(host).addCallback(send_to_ip)

    def readMessage(self, message, (host, port)):
        """ Function allows to decyrpt and read a received message.

                Args:
                message (list) - received packet,
                host (str) - host of a provider,
                port (int) - port of a provider.
        """
        elem = message[0]
        forward = message[1]
        backward = message[2]
        element = EcPt.from_binary(elem, self.G)
        if elem in self.sentElements:
            # print "[%s] > Decrypted bounce:" % self.name
            return forward
        else:
            aes = Cipher("AES-128-CTR")
            k1 = format3.KDF((self.privk * element).export())
            b = Bn.from_binary(k1.b) % self.o
            new_element = b * element
            expected_mac = forward[:20]
            ciphertext_metadata, ciphertext_body = msgpack.unpackb(forward[20:])
            mac1 = hmac.new(k1.kmac, ciphertext_metadata, digestmod=sha1).digest()
            if not (expected_mac == mac1):
                raise Exception("> CLIENT %s : WRONG MAC ON PACKET" % self.name)
            enc_metadata = aes.dec(k1.kenc, k1.iv)
            enc_body = aes.dec(k1.kenc, k1.iv)
            pt = enc_body.update(ciphertext_body)
            pt += enc_body.finalize()
            header = enc_metadata.update(ciphertext_metadata)
            header += enc_metadata.finalize()
            header = petlib.pack.decode(header)
            if pt.startswith('HT'):
                # print "[%s] > Decrypted heartbeat. " % self.name
                return pt
            else:
                # print "[%s] > Decrypted message. " % self.name
                return pt

    def takePathSequence(self, mixnet, length):
        """ Function takes a random path sequence build of active mixnodes. If the
        default length of the path is bigger that the number of available mixnodes,
        then all mixnodes are used as path.

                Args:
                mixnet (list) - list of active mixnodes,
                length (int) - length of the path which we want to build.
        """
        #return random.sample(mixnet, length) if len(mixnet) > length else mixnet
        if len(mixnet) > length:
            randomPath = random.sample(mixnet, length)
        else:
            randomPath = mixnet
            numpy.random.shuffle(randomPath)
        return randomPath

    def encryptData(self, data):
        ciphertext, tag = self.aes.quick_gcm_enc(self.kenc, self.iv, data)
        return (tag + ciphertext)

    def decryptData(self, data):
        dec = self.aes.quick_gcm_dec(self.kenc, self.iv, data[16:], data[:16])
        return dec

    def selectRandomReceiver(self):
        if self.usersPubs:
            return random.choice(self.usersPubs)
        else:
            return None

    def turnOnFakeMessaging(self):
        #friendsGroup = random.sample(self.usersPubs, 5)
        friendsGroup = self.usersPubs
        interval = sf.sampleFromExponential(self.EXP_PARAMS_PAYLOAD)
        reactor.callLater(interval, self.randomMessaging, friendsGroup)

    def randomMessaging(self, group):
        mixpath = self.takePathSequence(self.mixnet, self.PATH_LENGTH)
        msgF = "TESTMESSAGE" + sf.generateRandomNoise(NOISE_LENGTH)
        msgB = "TESTMESSAGE" + sf.generateRandomNoise(NOISE_LENGTH)
        if self.TESTUSER:
            r = group[0]
            print "Client: %s with provider %s" % (r.name, r.provider.name)
        else:
            r = random.choice(group)
        self.sendMessage(r, mixpath, msgF, msgB)

        interval = sf.sampleFromExponential(self.EXP_PARAMS_PAYLOAD)
        reactor.callLater(interval, self.randomMessaging, group)

    def createTestingSet(self):
        self.testHeartbeats = set()
        self.testDrops = set()
        self.testPayload = set()
        # friendsGroup = random.sample(self.usersPubs, 5)
        friendsGroup = self.usersPubs

        for i in range(100):
            mixpath = self.takePathSequence(self.mixnet, self.PATH_LENGTH)
            timestamp = time.time()
            self.testHeartbeats.add(self.createHeartbeat(mixpath, timestamp))
        for i in range(100):
            mixpath = self.takePathSequence(self.mixnet, self.PATH_LENGTH)
            self.testDrops.add(self.createDropMessage(mixpath))
        for i in range(100):
            mixpath = self.takePathSequence(self.mixnet, self.PATH_LENGTH)
            if self.TESTUSER:
                r = friendsGroup[0]
                print "Client: %s with provider %s" % (r.name, r.provider.name)
            else:
                # r = random.choice(self.usersPubs)
                r = random.choice(friendsGroup)
            msgF = "TESTMESSAGE" + sf.generateRandomNoise(NOISE_LENGTH)
            msgB = "TESTMESSAGE" + sf.generateRandomNoise(NOISE_LENGTH)
            packet, addr = self.makePacket(r, mixpath, self.setup,  msgF, msgB, False, typeFlag = 'P')
            self.testPayload.add((packet, addr))

    def setExpParamsDelay(self, newParameter):
        self.EXP_PARAMS_DELAY = (newParameter, None)

    def setExpParamsLoops(self, newParameter):
        self.EXP_PARAMS_LOOPS = (newParameter, None)

    def setExpParamsCover(self, newParameter):
        self.EXP_PARAMS_COVER = (newParameter, None)

    def setExpParamsPayload(self, newParameter):
        self.EXP_PARAMS_PAYLOAD = (newParameter, None)

    def saveInDatabase(self, database):
        """ Function saves clients public information in a database.

                Args:
                database (str) - dir and name of the database.
        """
        try:
            db = sqlite3.connect(database)
            c = db.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS Users (id INTEGER PRIMARY KEY, name text, port integer, host text, pubk blob, provider blob)''')
            insertQuery = "INSERT INTO Users VALUES(?, ?, ?, ?, ?, ?)"
            c.execute(insertQuery, [None, self.name, self.port, self.host,
                      sqlite3.Binary(petlib.pack.encode(self.pubk)),
                      sqlite3.Binary(petlib.pack.encode(self.provider))]
                     )
            db.commit()
            db.close()
        except Exception, e:
            print "ERROR: ", str(e)

    def takeSingleUserFromDB(self, database, idt):
        """ Function takes information about a selected single client from a database.

                Args:
                database (str) - dir and name of the database,
                idt (int) - identifier of the client.
        """
        try:
            db = sqlite3.connect(database)
            c = db.cursor()
            u = dc.selectByIdx(db, "Users", idt)
            if u[1] != self.name:
                p = petlib.pack.decode(u[5])
                receiver = format3.User(str(u[1]), u[2], u[3], petlib.pack.decode(u[4]),
                                        format3.Mix(p[0], p[1], p[2], p[3]))
                return receiver
            return None
        except Exception, e:
            print "ERROR: ", str(e)

    def takeAllUsersFromDB(self, database):
        """ Function takes information about all clients from the database.

                Args:
                database (str) - dir and name of the database.
        """
        usersList = []
        try:
            db = sqlite3.connect(database)
            c = db.cursor()
            c.execute("SELECT * FROM %s" % "Users")
            users = c.fetchall()
            for u in users:
                p = self.takeProvidersData("example.db", u[5])
                if not self.name == u[1]:
                    usersList.append(format3.User(str(u[1]), u[2], u[3], petlib.pack.decode(u[4]), p))
            db.close()
            return usersList
        except Exception, e:
            print "ERROR: ", str(e)

    def takeProvidersData(self, database, providerId):
        """ Function takes public information about a selected provider
            if providerId specified or about all registered providers
            from the database. 

                Args:
                database (str) - dir and name of the database,
                providerId (int) - identifier of a provider whoes information
                                    we want to pull.
        """
        providers = []
        try:
            db = sqlite3.connect(database)
            c = db.cursor()
            
            c.execute("SELECT * FROM %s WHERE name='%s'" % ("Providers", unicode(providerId)))
            fetchData = c.fetchall()
            pData = fetchData.pop()
            return format3.Mix(str(pData[1]), pData[2], str(pData[3]), petlib.pack.decode(pData[4]))

        except Exception, e:
            print "ERROR: ", str(e)
        finally:
            db.close()

    def takeMixnodesData(self, database):
        """ Function takes public information about all registered mixnodes
            from the database.

                Args:
                database (str) - dir and name of the database.
        """
        try:
            db = sqlite3.connect(database)
            c = db.cursor()
            c.execute("SELECT * FROM %s" % "Mixnodes")
            mixdata = c.fetchall()
            for m in mixdata:
                self.mixnet.append(format3.Mix(m[1], m[2], m[3], petlib.pack.decode(m[4])))
        except Exception, e:
            print "ERROR: ", str(e)

    def readInUsersPubs(self, databaseName):
        self.usersPubs = self.takeAllUsersFromDB(databaseName)

    def readInData(self, databaseName):
        self.readInUsersPubs(databaseName)
        self.takeMixnodesData(databaseName)
        self.turnOnMessagePulling()
        if self.TESTMODE or self.TESTUSER:
            self.createTestingSet()
        self.turnOnMessaging(self.mixnet)

    def measureSentMessages(self):
        lc = task.LoopingCall(self.takeMeasurments)
        lc.start(MEASURE_TIME, False)

    def takeMeasurments(self):
        self.sendMeasurments.append(self.numMessagesSent)
        self.numMessagesSent = 0

    def save_measurments(self):
        lc = task.LoopingCall(self.save_to_file)
        lc.start(SAVE_MEASURMENTS_TIME, False)

    def save_to_file(self):
        with open('messagesSent.csv', 'ab') as outfile:
            csvW = csv.writer(outfile, delimiter='\n')
            csvW.writerow(self.sendMeasurments)
        self.sendMeasurments = []

