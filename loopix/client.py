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

from sphinxmix.SphinxClient import pki_entry, Nenc, create_forward_message, rand_subset, PFdecode, Relay_flag, Dest_flag, Surb_flag, receive_forward
from sphinxmix.SphinxParams import SphinxParams
from sphinxmix.SphinxNode import sphinx_process


with open('config.json') as infile:
    _PARAMS = json.load(infile)

TIME_PULL = float(_PARAMS["parametersClients"]["TIME_PULL"])
NOISE_LENGTH = float(_PARAMS["parametersClients"]["NOISE_LENGTH"])
MEASURE_TIME = float(_PARAMS["parametersClients"]["MEASURE_TIME"])
SAVE_MEASURMENTS_TIME = float(_PARAMS["parametersClients"]["SAVE_MEASURMENTS_TIME"])

class Client(DatagramProtocol):
    def __init__(self, setup, name, port, host,
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

        self.params = SphinxParams(header_len=1024)

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

        self.buffer = []


        # A set of PARAMETERS read in from the configuration file
        self.PATH_LENGTH = int(_PARAMS["parametersClients"]["PATH_LENGTH"])

        self.EXP_PARAMS_PAYLOAD = (float(_PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"]), None)
        if _PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"] != "None":
            self.EXP_PARAMS_LOOPS = (float(_PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"]), None)
        else:
            self.EXP_PARAMS_LOOPS = None

        if _PARAMS["parametersClients"]["EXP_PARAMS_COVER"] != "None":
            self.EXP_PARAMS_COVER = (float(_PARAMS["parametersClients"]["EXP_PARAMS_COVER"]), None)
        else:
            self.EXP_PARAMS_COVER = None

        self.EXP_PARAMS_DELAY = (float(_PARAMS["parametersClients"]["EXP_PARAMS_DELAY"]), None)

        # TEST MODE - Each message in this mode is labeled with its type
        self.TESTMODE = True if _PARAMS["parametersClients"]["TESTMODE"] == "True" else False
        # TARGET USER - This is set only for simulations; means that this users is sending to 
        # one selected recipient
        self.TARGETUSER = True if _PARAMS["parametersClients"]["TARGETUSER"] == "True" else False


        if _PARAMS["parametersClients"]["TURN_ON_SENDING"] == "False":
            self.TURN_ON_SENDING = False
        else:
            self.TURN_ON_SENDING = True

        self.DATABASE = "example.db"

        #self.receivedQueue = DeferredQueue()
        self.processQueue = ProcessQueue()

        self.numMessagesSent = 0
        self.sendMeasurments = []
        
        self.resolvedAdrs = {}

    def startProtocol(self):
        print "[%s] > Start Protocol" % self.name
        print "TARGET USER MODE: ", self.TARGETUSER

        if self.PATH_LENGTH < 3:
            print "[%s] > WARNING: Path length should be at least 3." % self.name

        self.provider = self.takeProvidersData(self.DATABASE, self.providerId)
        print "Provider: ", self.provider

        self.sendPing()

        self.readInData(self.DATABASE)

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

        if self.EXP_PARAMS_LOOPS:
            interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
            if self.TESTMODE:
                reactor.callLater(interval, self.generateFakeLoopTraffic)
            else:
                reactor.callLater(interval, self.generateLoopTraffic, mixList)
        else:
            print "[%s] > Loop cover traffic turned off." % self.name

    def turnOnCoverMsg(self, mixList):
        """ Function turns on a loop generating a drop cover traffic.

            Args:
                mixList (list): a list of active mixnodes in the network.
        """

        if self.EXP_PARAMS_COVER:
            interval = sf.sampleFromExponential(self.EXP_PARAMS_COVER)
            if self.TESTMODE:
                reactor.callLater(interval, self.generateFakeCoverTraffic)
            else:
                reactor.callLater(interval, self.generateCoverTraffic, mixList)
        else:
            print "[%s] > Drop cover traffic turned off." % self.name

    def checkBuffer(self, mixList):
        """ Function sends message from buffer or drop messages.

                Args:
                mixList (list): a list of active mixnodes in the network.
        """

        try:
            if len(self.buffer) > 0 and self.TURN_ON_SENDING:
                message, addr = self.buffer.pop(0)
                self.send(message, addr)
                print "[%s] > Message from the buffer sent." % self.name
            else:
                if self.TARGETUSER:
                    packet = random.choice(tuple(self.testDrops))
                    addr = (self.provider.host, self.provider.port)
                    self.send("ROUT" + packet, addr)
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
            packet = random.choice(tuple(self.testHeartbeats))
            addr = (self.provider.host, self.provider.port)
            self.send("ROUT" + packet, addr)
            interval = sf.sampleFromExponential(self.EXP_PARAMS_LOOPS)
            reactor.callLater(interval, self.generateFakeLoopTraffic)
        except Exception, e:
            print "ERROR generateFakeLoopTraffic: ", str(e)

    def generateFakeCoverTraffic(self):
        try:
            packet = random.choice(tuple(self.testDrops))
            addr = (self.provider.host, self.provider.port)
            self.send("ROUT" + packet, addr)
            interval = sf.sampleFromExponential(self.EXP_PARAMS_COVER)
            reactor.callLater(interval, self.generateFakeCoverTraffic)
        except Exception, e:
            print "ERROR", str(e)

    def generateFakePayload(self):
        try:
            if self.TURN_ON_SENDING:
                packet = random.choice(tuple(self.testPayload))
                addr = (self.provider.host, self.provider.port)
                self.send("ROUT" + packet, addr)
            else:
                packet = random.choice(tuple(self.testDrops))
                addr = (self.provider.host, self.provider.port)
                self.send("ROUT" + packet, addr)
            interval = sf.sampleFromExponential(self.EXP_PARAMS_PAYLOAD)
            reactor.callLater(interval, self.generateFakePayload)
        except Exception, e:
            print "ERROR generateFakePayload: ", str(e)


    def datagramReceived(self, data, (host, port)):
        #self.receivedQueue.put((data, (host, port)))
        # print "[%s] > datagram Received" % self.name
        try:
            self.processQueue.put((data, (host, port)))
        except Exception, e:
            print "[%s] > ERROR datagramReceived: %s " % (self.name, str(e))

    def do_PROCESS(self, (data, (host, port))): 
        self.processMessage(data, (host, port))
        #self.receivedQueue.get().addCallback(self.do_PROCESS)
        
        try:
            reactor.callFromThread(self.get_and_addCallback, self.do_PROCESS)
        except Exception, e:
            print "[%s] > ERROR do_PROCESS: %s" % (self.name, str(e))

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
            message = petlib.pack.decode(data)
            msg = self.readMessage(message, (host, port))
            if msg.startswith("HT"):
                print "[%s] > Heartbeat looped back" % self.name
            else:
                if msg.startswith("TESTMESSAGE"):
                    print "[%s] > This is a test message received" % self.name
                elif msg.startswith("FAKEMESSAGE"):
                    print "[%s] > This is a fake message received" % self.name
                else:
                    print "[%s] > New message unpacked." % (self.name)
        except Exception, e:
            print "[%s] > ERROR: Message reading error: %s" % (self.name, str(e))
            print data

    # ================================SPHINX PACKET FORMAT==================================
    def makeSphinxPacket(self, receiver, mixes, message = '', dropFlag=False, typeFlag=None):
        path = [self.provider] + mixes + [receiver.provider] + [receiver]
        keys_nodes = [n.pubk for n in path]

        nodes_routing = []
        for i in range(len(path)):
            if float(self.EXP_PARAMS_DELAY[0]) == 0.0:
                delay = 0.0
            else:
                delay = sf.sampleFromExponential(self.EXP_PARAMS_DELAY)
            nodes_routing.append(Nenc([(path[i].host, path[i].port), dropFlag, typeFlag, delay, path[i].name]))

        # Destination of the message
        dest = (receiver.host, receiver.port, receiver.name)
        header, body = create_forward_message(self.params, nodes_routing, keys_nodes, dest, message)
        return (header, body)

    def sendMessage(self, receiver, mixpath, msgF):
        """ Function allows to buffer a message (packed into Sphinx format) which we want to send.

            Args:
            receiver - public information of a receiver,
            mixpath (list) - path of mixnodes which should be traversed by the message,
            msgF (str) - message which we want to send,
            msgB (str) - message which is included in a bounce.
        """
        try:
            timestamp = '%.5f' % time.time()
            if self.TESTMODE:
                (header, body) = self.makeSphinxPacket(receiver, mixpath, msgF + timestamp, dropFlag=False, typeFlag = 'P')
            else:
                (header, body) = self.makeSphinxPacket(receiver, mixpath, msgF + timestamp, dropFlag=False)
            self.buffer.append(("ROUT" + petlib.pack.encode((header, body)), (self.provider.host, self.provider.port)))
        except Exception, e:
            print "[%s] > ERROR: Message could not be buffered for send: %s" % (self.name, str(e))


    def createHeartbeat(self, mixes, timestamp):
        """ Function creates a heartbeat - a noise message for which the sender and the receiver are the same entity.

                Args:
                mixes (list): list of mixnodes which the message should go through,
                timestamp (?): a timestamp at which the message was created.
        """
        try:
            heartMsg = sf.generateRandomNoise(NOISE_LENGTH)
            if self.TESTMODE:
                (header, body) = self.makeSphinxPacket(self, mixes, 'HT' + heartMsg + str(timestamp), dropFlag=False, typeFlag = 'H')
            else:
                (header, body) = self.makeSphinxPacket(self, mixes, 'HT' + heartMsg + str(timestamp), dropFlag=False)
            return (header, body)
        except Exception, e:
            print "[%s] > ERROR createHeartbeat: %s" % (self.name, str(e))
            return None

    def sendHeartbeat(self, mixnet, timestamp, predefinedPath=None):
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
                mixpath = predefinedPath if predefinedPath else self.takePathSequence(mixnet, self.PATH_LENGTH)
                heartbeatData = self.createHeartbeat(mixes, timestamp)
                if heartbeatData:
                    header, body = heartbeatData
                    print "[%s] > Sending heartbeat" % self.name
                    self.send("ROUT" + petlib.pack.encode((header, body)), (self.provider.host, self.provider.port))
                else:
                    raise Exception("[%s] > Heartbeat could not be send." % self.name)
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
            if self.TESTMODE:
                header, body = self.makeSphinxPacket(randomReceiver, mixes, randomMessage, dropFlag=True, typeFlag = 'D')
            else:
                header, body = self.makeSphinxPacket(randomReceiver, mixes, randomMessage, dropFlag=True)
            return (header, body)
        except Exception, e:
            print "[%s] > Create drop message ERROR: %s" % (self.name, str(e))
            return None

    def sendDropMessage(self, mixnet, predefinedPath = None):
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
                dropHeader, dropBody= dropData
                print "[%s] > Sending drop message" % self.name
                self.send("ROUT" + petlib.pack.encode((dropHeader, dropBody)), (self.provider.host, self.provider.port))
            else:
                raise Exception("[%s] > Drop message could not be send." % self.name)
        except ValueError, e:
            print "[%s] > Send drop message ERROR: %s" % (self.name, str(e))
        except Exception, e:
            print "[%s] > Send drop message ERROR: %s" % (self.name, str(e))

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

    def readMessage(self, message, (host, port)):
        """ Function allows to decyrpt and read a received message.

                Args:
                message (list) - received packet,
                host (str) - host of a provider,
                port (int) - port of a provider.
        """
        try:
            (header, body) = message

            peeledData = sphinx_process(self.params, self.privk, header, body)
            (tag, info, (header, body)) = peeledData
            rounting = PFdecode(self.params, info)
            if rounting[0] == Dest_flag:
                dest, message = receive_forward(self.params, body)
                if dest[-1] == self.name:
                    return message
                else:
                    raise Exception("Destination did not match")
                    return None
        except Exception, e:
            print "[%s] > ERROR: During message reading: %s" % (self.name, str(e))

    def takePathSequence(self, mixnet, length):
        """ Function takes a random path sequence build of active mixnodes. If the
        default length of the path is bigger that the number of available mixnodes,
        then all mixnodes are used as path.

                Args:
                mixnet (list) - list of active mixnodes,
                length (int) - length of the path which we want to build.
        """
        ENTRY_NODE = 0
        MIDDLE_NODE = 1
        EXIT_NODE = 2
        GROUPS = [ENTRY_NODE, MIDDLE_NODE, EXIT_NODE]

        randomPath = []
        try:
            if length > len(GROUPS):
                print '[%s] > There are not enough sets to build Stratified path' % self.name
                if len(mixnet) > length:
                    randomPath = random.sample(mixnet, length)
                else:
                    randomPath = mixnet
                    numpy.random.shuffle(randomPath)
            else:
                entries = [x for x in mixnet if x.group == ENTRY_NODE]
                middles = [x for x in mixnet if x.group == MIDDLE_NODE]
                exits = [x for x in mixnet if x.group == EXIT_NODE]

                entryMix = random.choice(entries)
                middleMix = random.choice(middles)
                exitMix = random.choice(exits)

                randomPath = [entryMix, middleMix, exitMix]
            return randomPath
        except Exception, e:
            print "[%s] > ERROR: During path generation: %s" % (self.name, str(e))

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

        print "[%s] > Generating fake 'real messages' which are put into buffer" % self.name
        self.EXP_PARAMS_FAKEGEN = (float(_PARAMS["parametersClients"]["FAKE_MESSAGING"]), None)
        self.TARGETRECIPIENT = _PARAMS["parametersClients"]["TARGETRECIPIENT"]
        recipient = self.takeUser(self.TARGETRECIPIENT)

        lc = task.LoopingCall(self.randomMessaging, recipient)
        lc.start(self.EXP_PARAMS_FAKEGEN[0], True)
        # interval = sf.sampleFromExponential(self.EXP_PARAMS_FAKEGEN)
        # reactor.callLater(interval, self.randomMessaging, recipient)

    def randomMessaging(self, r):
        """ Function simulated the generation of 'real' messages sent to a particular person
        """

        mixpath = self.takePathSequence(self.mixnet, self.PATH_LENGTH)
        message = "FAKEMESSAGE" + sf.generateRandomNoise(NOISE_LENGTH)
        print "[%s] > Sending to one target recipient %s" % (self.name, r.name)
        if not r:
            raise Exception('[%s] > Could not find the given user' % self.name)
        
        (header, body) = self.makeSphinxPacket(r, mixpath, message, dropFlag=False, typeFlag = 'P')            
        self.buffer.append((("ROUT" + petlib.pack.encode((header, body))), (self.provider.host, self.provider.port)))

        # interval = sf.sampleFromExponential(self.EXP_PARAMS_FAKEGEN)
        # reactor.callLater(interval, self.randomMessaging, r)

    def createTestingSet(self):

        print "Creating Testing Set"
        self.testHeartbeats = set()
        self.testDrops = set()
        self.testPayload = set()
        try:
            friendsGroup = random.sample(self.usersPubs, 10)
        except Exception, e:
            friendsGroup = self.usersPubs

        for i in range(100):
            mixpath = self.takePathSequence(self.mixnet, self.PATH_LENGTH)
            timestamp = time.time()
            heartbeatData = self.createHeartbeat(mixpath, timestamp)
            if heartbeatData:
                self.testHeartbeats.add(petlib.pack.encode(heartbeatData))
        for i in range(100):
            mixpath = self.takePathSequence(self.mixnet, self.PATH_LENGTH)
            dropData = self.createDropMessage(mixpath)
            if dropData:
                self.testDrops.add(petlib.pack.encode(dropData))
        if not self.TARGETUSER:
            print "[%s] > Creating a testing set of messages in the buffer"
            for i in range(100):
                mixpath = self.takePathSequence(self.mixnet, self.PATH_LENGTH)
                r = random.choice(friendsGroup)
                msgF = "TESTMESSAGE" + self.name + sf.generateRandomNoise(NOISE_LENGTH)
            
                header, body = self.makeSphinxPacket(r, mixpath, msgF, dropFlag = False, typeFlag = 'P')
                self.testPayload.add(petlib.pack.encode((header, body)))

    def setExpParamsDelay(self, newParameter):

        self.EXP_PARAMS_DELAY = (newParameter, None)

    def setExpParamsLoops(self, newParameter):

        self.EXP_PARAMS_LOOPS = (newParameter, None)

    def setExpParamsCover(self, newParameter):

        self.EXP_PARAMS_COVER = (newParameter, None)

    def setExpParamsPayload(self, newParameter):

        self.EXP_PARAMS_PAYLOAD = (newParameter, None)

    def takeUser(self, name):

        user = None
        for i in self.usersPubs:
            if i.name == name:
                user = i
        return user

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
            print "ERROR Save in Database: ", str(e)

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
                                        format3.Provider(p[0], p[1], p[2], p[3]))
                return receiver
            return None
        except Exception, e:
            print "ERROR takeSingleUserFromDB: ", str(e)

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
                p = self.takeProvidersData(self.DATABASE, u[5])
                if not self.name == u[1]:
                    usersList.append(format3.User(str(u[1]), u[2], u[3], petlib.pack.decode(u[4]), p))
            db.close()
            return usersList
        except Exception, e:
            print "ERROR takeAllUsersFromDB: ", str(e)

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
            return format3.Provider(str(pData[1]), pData[2], str(pData[3]), petlib.pack.decode(pData[4]))

        except Exception, e:
            print "ERROR takeProvidersData: ", str(e)
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
                self.mixnet.append(format3.Mix(m[1], m[2], m[3], petlib.pack.decode(m[4]), m[5]))
        except Exception, e:
            print "ERROR takeMixnodesData: ", str(e)


    def readInUsersPubs(self, databaseName):

        self.usersPubs = self.takeAllUsersFromDB(databaseName)

    def readInData(self, databaseName):

        self.readInUsersPubs(databaseName)
        self.takeMixnodesData(databaseName)
        self.turnOnMessagePulling()

        if self.TESTMODE:
            self.createTestingSet()
        if self.TARGETUSER:
            self.turnOnFakeMessaging()
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


