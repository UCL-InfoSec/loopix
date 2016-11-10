import base64
import databaseConnect as dc
from collections import namedtuple
import format3
from hashlib import sha512, sha1
import hmac
import math
from mixnode import MixNode
import msgpack
import numpy
import os
from petlib.cipher import Cipher
from petlib.ec import EcPt, Bn, EcGroup
import petlib.pack
from provider import Provider
import random
import resource
import time
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, protocol, task, defer, threads
from twisted.internet.defer import DeferredQueue, DeferredLock
from types import *
import sqlite3
import string
import supportFunctions as sf
import sys
import uuid
import io
from twisted.logger import jsonFileLogObserver, Logger
import csv
from twisted.internet.interfaces import IPullProducer
from zope.interface import implementer
from processQueue import ProcessQueue
from sets import Set

import copy

# import fcntl

# def make_blocking(fd):
#     flags = fcntl.fcntl(fd, fcntl.F_GETFL)
#     if flags & os.O_NONBLOCK:
#         fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)


TIME_PULL = 10
NOISE_LENGTH = 500

#log = Logger(observer=jsonFileLogObserver(io.open("log.json", "a")))


class Client(DatagramProtocol):
    def __init__(self, setup, name, port, host, testMode=False,
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

        self.d = defer.Deferred()

        # Information about active mixnodes and other users in the network
        self.mixnet = []
        self.usersPubs = []

        self.sentElements = set()
        self.heartbeatsSent = set()
        self.buffer = []

        self.aes = Cipher.aes_128_gcm()

        self.PATH_LENGTH = 3
        self.EXP_PARAMS_PAYLOAD = (10, None)
        self.EXP_PARAMS_LOOPS = (10, None)
        self.EXP_PARAMS_COVER = (10, None)
        self.EXP_PARAMS_DELAY = (0.005, None)
        self.TESTMODE = testMode

        self.boardHost = "127.0.0.1"
        self.boardPort = 9998

        self.numHeartbeatsSent = 0
        self.numHeartbeatsReceived = 0
        self.numMessagesSent = 0
        self.tagedHeartbeat = {}

        self.tagForTesting = False

        self.receivedQueue = DeferredQueue()

        #self.processQueue = ProcessQueue()

    def startProtocol(self):
        print "[%s] > Start Protocol" % self.name

        self.provider = self.takeProvidersData("example.db", self.providerId)
        print "Provider: ", self.provider

        self.sendPing()
        reactor.callLater(100.0, self.readInData, "example.db")
        reactor.callLater(100.0, self.turnOnProcessing)

        #if self.TESTMODE:
        self.measureSentMessages()
        reactor.callLater(180.0, self.updateParams)


    def turnOnProcessing(self):
        self.receivedQueue.get().addCallback(self.do_PROCESS)
        #self.processQueue.get().addCallback(self.do_PROCESS)

    def sendPing(self):

        def send_to_ip(IPAddr):
            self.transport.write("PING"+self.name, (IPAddr, self.provider.port))

        reactor.resolve(self.provider.host).addCallback(send_to_ip)

    def stopProtocol(self):
        print "[%s] > Stop Protocol" % self.name


    def updateParams(self):
        old_payload = self.EXP_PARAMS_PAYLOAD[0]
        old_loops = self.EXP_PARAMS_LOOPS[0]
        old_drop = self.EXP_PARAMS_COVER[0]

        self.EXP_PARAMS_PAYLOAD = (float(old_payload/2.0), None)
        self.EXP_PARAMS_LOOPS = (float(old_loops/2.0), None)
        self.EXP_PARAMS_COVER = (float(old_drop/2.0), None)

        if old_payload <= 0.5:
            pass
        else:
            reactor.callLater(300, self.updateParams)

    # def announce(self):
    #     resp = "UINF" + petlib.pack.encode([self.name, self.port,
    #                                         self.host, self.pubk,
    #                                         self.provider])
    #     self.transport.write(resp, (self.boardHost, self.boardPort))
    #     print "[%s] > announced."
    #     log.info("[%s] > announced to the board." % self.name)

    # def pullMixnetInformation(self, providerPort, providerHost):
    #     """ Asking for the mixnodes information """
    #     self.transport.write("INFO", (providerHost, providerPort))
    #     log.info("[%s] > pulled mixnet information." % self.name)

    # def pullUserInformation(self, providerPort, providerHost):
    #     """ Asking for other users public information """
    #     self.transport.write("UREQ", (providerHost, providerPort))
    #     log.info("[%s] > pulled users information." % self.name)

    def pullMessages(self):
        """ Sends a request to pull messages from the provider."""

        def send_to_ip(IPAddrs):
            self.transport.write("PING"+self.name, (IPAddrs, self.provider.port))
            self.transport.write("PULL_MSG"+self.name, (IPAddrs, self.provider.port))
            self.numMessagesSent += 2
            # print "[%s] > Pulled messages from provider %s" % (self.name, str(IPAddrs))

        reactor.resolve(self.provider.host).addCallback(send_to_ip)

    def turnOnMessagePulling(self):
        """ Function turns on a loop which pulls messages from the provider every timestamp."""

        lc = task.LoopingCall(self.pullMessages)
        lc.start(TIME_PULL)

    def turnOnMessaging(self, mixList):
        """ Function turns on sending cover traffic and real message buffer checking.

            Args:
                mixList (list): a list of active mixnodes in the network.
        """
        self.turnOnBufferChecking(mixList)
        self.turnOnCoverLoops(mixList)
        self.turnOnCoverMsg(mixList)
        if self.TESTMODE:
            self.turnOnFakeMessaging()
        self.sendTagedMessage()

    def turnOnBufferChecking(self, mixList):
        """ Function turns on a loop checking the buffer with messages.

            Args:
                mixList (list): a list of active mixnodes in the network.

        """

        interval = sf.sampleFromExponential(self.EXP_PARAMS_PAYLOAD)
        reactor.callLater(interval, self.checkBuffer, mixList)

    def turnOnCoverLoops(self, mixList):
        """ Function turns on a loop generating a loop cover traffic.

            Args:
                mixList (list): a list of active mixnodes in the network.
        """

        interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
        reactor.callLater(interval, self.generateLoopTraffic, mixList)

    def turnOnCoverMsg(self, mixList):
        """ Function turns on a loop generating a drop cover traffic.

            Args:
                mixList (list): a list of active mixnodes in the network.
        """

        interval = sf.sampleFromExponential(self.EXP_PARAMS_COVER)
        reactor.callLater(interval, self.generateCoverTraffic, mixList)

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

    def datagramReceived(self, data, (host, port)):
        self.receivedQueue.put((data, (host, port)))
        # print "[%s] > Received new packet" % self.name
        # try:
        #     self.processQueue.put((data, (host, port)))
        # except Exception, e:
        #     print "[%s] > ERROR: %s " % (self.name, str(e))

    def do_PROCESS(self, (data, (host, port))): 
        self.processMessage(data, (host, port))
        self.receivedQueue.get().addCallback(self.do_PROCESS)
        
        # try:
        #     reactor.callFromThread(self.get_and_addCallback, self.do_PROCESS)
        # except Exception, e:
        #     print "[%s] > ERROR: %s" % (self.name, str(e))

    def get_and_addCallback(self, f):
        self.processQueue.get().addCallback(f)

    def processMessage(self, data, (host, port)):
        # data, (host, port) = obj        

        # if data[:4] == "EMPT":
        #     print "[%s] > Received information: It seems that mixnet does not have any nodes." % self.name
        # if data[:4] == "RINF":
        #     print "[%s] > Received information: about the active mixnodes from %s,  %d." % (self.name, host, port)
        #     dataList = petlib.pack.decode(data[4:])
        #     for element in dataList:
        #         self.mixnet.append(format3.Mix(element[0], element[1], element[2], element[3]))
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
            if msg:
                if msg.startswith("HTTAG"):
                    self.measureLatency(msg, timestamp)
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
        # delay = [current_time + sf.sampleFromExponential(self.EXP_PARAMS_DELAY) for _ in range(len(path)+1)]
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
            # print "[%s] > Buffered message to client %s" % (self.name, receiver.name)
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

        reactor.resolve(host).addCallback(send_to_ip)
        self.numMessagesSent += 1

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
            print "[%s] > Decrypted bounce:" % self.name
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
                #for i in self.heartbeatsSent:
                    #if i[0] == pt[2:]:
                        # self.numHeartbeatsReceived += 1
                        # self.heartbeatsSent.remove(i)
                return pt
            else:
                print "[%s] > Decrypted message. " % self.name
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
        #friendsGroup = random.sample(self.usersPubs, 3)
        friendsGroup = self.usersPubs
        # print "Friends group: ", friendsGroup
        reactor.callLater(0.01, self.randomMessaging, friendsGroup)

    def randomMessaging(self, group):

        r = random.choice(group)
        # #r = random.choice(self.usersPubs)
        mixpath = self.takePathSequence(self.mixnet, self.PATH_LENGTH)
        msgF = "TESTMESSAGE" + sf.generateRandomNoise(NOISE_LENGTH)
        msgB = "TESTMESSAGE" + sf.generateRandomNoise(NOISE_LENGTH)
        self.sendMessage(r, mixpath, msgF, msgB)

        reactor.callLater(0.01, self.randomMessaging, group)

    def sendTagedMessage(self):
        try:
            mixes = self.takePathSequence(self.mixnet, self.PATH_LENGTH)
            tag = "TAG" + str(uuid.uuid4())
            tagedMessage = tag + sf.generateRandomNoise(NOISE_LENGTH)
            #packet, addr = self.makePacket(self, mixes, self.setup, 'HT'+tagedMessage, 'HB'+tagedMessage, False, typeFlag='P')
            #self.send("ROUT" + packet, addr)
            #self.sendMessage(self, mixes, 'HT'+tagedMessage, 'HB'+tagedMessage)
            message, addr = self.makePacket(self, mixes, self.setup,  'HT'+tagedMessage, 'HB'+tagedMessage, False, typeFlag = 'P')
            packet = "ROUT" + message
            self.send(packet, addr)
            self.tagedHeartbeat[tagedMessage] = time.time()
            # print "[%s] > TAGED MESSAGE SENT." % self.name
        except Exception, e:
            print "[%s] > ERROR: %s" % (self.name, str(e))

    def measureLatency(self, msg, providerTimestamp):
        # print ">TAG MESSAGE RECEIVED: This is a taged message, to measure latency"
        if msg[2] in self.tagedHeartbeat.keys():
            latency = (float(providerTimestamp) - float(i[0]))
            del self.tagedHeartbeat[msg[2]]
            with open('latency.csv', 'ab') as outfile:
                csvW = csv.writer(outfile, delimiter=',')
                data = [[latency]]
                csvW.writerows(data)
            self.sendTagedMessage()
        # for i in self.tagedHeartbeat:
        #     if i[1] == msg[2:]:
        #         latency = (float(providerTimestamp) - float(i[0]))
        #         self.tagedHeartbeat.remove(i)
        #         with open('latency.csv', 'ab') as outfile:
        #             csvW = csv.writer(outfile, delimiter=',')
        #             data = [[latency]]
        #             csvW.writerows(data)
        #         self.sendTagedMessage()

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
            #if providerId:
            
            c.execute("SELECT * FROM %s WHERE name='%s'" % ("Providers", unicode(providerId)))
            fetchData = c.fetchall()
            pData = fetchData.pop()
            return format3.Mix(str(pData[1]), pData[2], str(pData[3]), petlib.pack.decode(pData[4]))
            
            #else:
            #    c.execute("SELECT * FROM %s ORDER BY RANDOM() LIMIT 1" % ("Providers"))
            #    providersData = c.fetchall()
            #    providersList = []
            #    for p in providersData:
            #        providersList.append(format3.Mix(p[1], p[2], p[3], petlib.pack.decode(p[4]))) 
            #    return random.choice(providersList)
            # self.transport.write("PING"+self.name, (self.provider.host, self.provider.port))
            #print "Provider taken."
        
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
        self.turnOnMessaging(self.mixnet)

    def measureSentMessages(self):
        lc = task.LoopingCall(self.sentMessages)
        lc.start(600)

    def sentMessages(self):
        numSent = self.numMessagesSent
        self.numMessagesSent = 0
        with open('messagesSent.csv', 'ab') as outfile:
            csvW = csv.writer(outfile, delimiter=',')
            data = [[numSent, self.EXP_PARAMS_PAYLOAD[0]]]
            csvW.writerows(data)
