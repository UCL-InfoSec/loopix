from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor, protocol, task, defer, threads
import petlib.pack
from petlib.ec import EcGroup, EcPt
from petlib.bn import Bn
from twisted.internet import reactor, defer
import format3
from mixnode import MixNode
import base64
import random
import threading
import codecs
import time
import databaseConnect as dc
import sys
import sqlite3
import io
import csv
from twisted.internet.defer import DeferredQueue
import supportFunctions as sf
from processQueue import ProcessQueue
import numpy
import json

with open('config.json') as infile:
    _PARAMS = json.load(infile)

TIME_ACK = float(_PARAMS["parametersMixnodes"]["TIME_ACK"])
MAX_DELAY_TIME = float(_PARAMS["parametersMixnodes"]["MAX_DELAY_TIME"])
NOISE_LENGTH = float(_PARAMS["parametersMixnodes"]["NOISE_LENGTH"])
MEASURE_TIME = float(_PARAMS["parametersMixnodes"]["MEASURE_TIME"])
SAVE_MEASURMENTS_TIME = float(_PARAMS["parametersMixnodes"]["SAVE_MEASURMENTS_TIME"])

from sphinxmix.SphinxParams import SphinxParams
from sphinxmix.SphinxNode import sphinx_process
from sphinxmix.SphinxClient import PFdecode, Relay_flag, Dest_flag, Surb_flag, receive_forward, Nenc, create_forward_message

class Provider(MixNode):

    def __init__(self, name, port, host, setup, privk=None, pubk=None):
        """ A class representing a provider. """
        MixNode.__init__(self, name, port, host, setup, privk, pubk)

        self.processQueue = ProcessQueue()

        self.clientList = {}
        self.usersPubs = []
        self.storage = {}
        self.MAX_RETRIEVE = 500

        self.bProcessed = 0
        self.gbSent = 0
        self.otherProc = 0
        self.mReceived = 0

        self.measurments = []

    def startProtocol(self):
        reactor.suggestThreadPoolSize(50)

        print "[%s] > Start protocol." % self.name
        
        reactor.callLater(10.0, self.turnOnProcessing)

        if self.TAGED_HEARTBEATS == "True":
           self.d.addCallback(self.turnOnTagedHeartbeats)
        else:
           self.d.addCallback(self.turnOnHeartbeats)
        self.d.addErrback(self.errbackHeartbeats)

        #self.turnOnReliableUDP()
        self.readInData('example.db')

        self.turnOnMeasurments()
        self.saveMeasurments()

    def stopProtocol(self):
        print "[%s] > Stop protocol" % self.name

    def turnOnProcessing(self):
        self.processQueue.get().addCallback(self.do_PROCESS)

    def datagramReceived(self, data, (host, port)):
        self.mReceived += 1
        try:
            self.processQueue.put((data, (host, port)))
        except Exception, e:
            print "[%s] > ERROR Datagram Received: %s " % (self.name, str(e))

    def do_PROCESS(self, obj):
        self.processMessage(obj)
        self.bProcessed += 1

        try:
            reactor.callFromThread(self.get_and_addCallback, self.do_PROCESS)
        except Exception, e:
            print "[%s] > ERROR do_PROCESS: %s" % (self.name, str(e))

    def get_and_addCallback(self, f):
        self.processQueue.get().addCallback(f)

    def processMessage(self, (data, (host, port))):
        if data[:8] == "PULL_MSG":
            self.do_PULL(data[8:], (host, port))
            self.otherProc += 1
        elif data[:4] == "ROUT":
            try:
                header, body = petlib.pack.decode(data[4:])
                self.do_ROUT((header, body), (host, port))
            except Exception, e:
                print "[%s] > ERROR processMessage: %s" % (self.name, str(e))
                print repr(e)
        elif data[:4] == "ACKN":
            #if data in self.expectedACK:
            #    self.expectedACK.remove(data)
            # self.otherProc += 1
            pass
        elif data[:4] == "PING":
            self.subscribeClient(data[4:], host, port)
            self.otherProc += 1
        else:
            print "Processing Message - message not recognized"

    def do_PULL(self, name, (host, port)):
        """ Function which responds the pull message request from the client. First, the function checks if the requesting 
        client belogs to this provider, next takes all the messages destinated to this client and sends a fixed number of 
        messages to the client.

                Args:
                host (str): host of the requesting client,
                port (int): port of the requesting client.
        """
        try:
            self.flushStorage(name, (host, port))
        except Exception, e:
            print "ERROR during flushing: ", str(e)

    def flushStorage(self, name, (ip_host, port)):
        if name not in self.clientList:
           self.sendMessage("NOASG", (ip_host, port))
        else: 
            if name in self.storage:
                if self.storage[name]:
                    for _ in range(self.MAX_RETRIEVE):
                        if self.storage[name]:
                            message = self.storage[name].pop()
                            self.sendMessage("PMSG" + message, (ip_host, port))
                else:
                    self.sendMessage("NOMSG", (ip_host, port))
            else:
                self.sendMessage("NOMSG", (ip_host, port))

    def do_ROUT(self, data, (host, port)):
        """ Function operates on the received route packet. First, the function decrypts one layer on the packet. Next, if 
        it is a forward message adds it to the queue. If it is a message destinated to one of the providers clients, the message 
        is saved in the storage, where it awaits for the client to fetch it.

                Args:
                data (str): traversing packet string,
                host (str): host of the sender of the packet
                port (int): port of the sender of the packet
        """

        try:
            peeledData = self.process_sphinx_packet(data)
        except Exception, e:
            print "[%s] > ERROR during packet processing." % self.name
        else:
            if peeledData:
                (tag, info, (header, body)) = peeledData
                #routing_flag, meta_info = PFdecode(self.params, info)
                routing = PFdecode(self.params, info)
                if routing[0] == Relay_flag:
                    routing_flag, meta_info = routing
                    next_addr, dropFlag, typeFlag, delay, next_name = meta_info
                    if dropFlag:
                        print "[%s] > Drop message." % self.name
                    else:
                        if next_name in self.clientList:
                            self.saveInStorage(next_name, petlib.pack.encode((header, body)))
                            print "[%s] > Message saved in storage." % self.name   
                        else:
                            if typeFlag == 'P':
                                self.pProcessed += 1
                            try:
                                reactor.callFromThread(self.send_or_delay, delay, "ROUT" + petlib.pack.encode((header, body)), next_addr)
                                print "[%s] > Message forwarded." % self.name
                            except Exception, e:
                                print "ERROR during message processing", str(e)
                elif routing[0] == Dest_flag:
                    dest, message = receive_forward(self.params, body)
                    if dest[-1] == self.name:
                        if message.startswith('HT'):
                            # print "[%s] > Heartbeat looped back" % self.name
                            pass
                        if message.startswith('TAG'):
                            # print "[%s] > Tagged message received" % self.name
                            self.measureLatency(message)
                    else:
                        raise Exception("Destination did not match")

    def takePathSequence(self, mixnet, length):
        """ Function takes path sequence of a given length. If the length is 
            bigger than the number of registered mixnodes in the network, all
            mixnodes are used to build a path.
        """
        try:
            ENTRY_NODE = 0
            MIDDLE_NODE = 1
            EXIT_NODE = 2
            GROUPS = [ENTRY_NODE, MIDDLE_NODE, EXIT_NODE]

            randomPath = []
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
            print "[%s] > ERROR: During selecting path %s" % (self.name, str(e))


    def saveInStorage(self, key, value):
        """ Function saves a message in the local storage, where it awaits till the client will fetch it.

                Args:
                key (int): clients key,
                value (str): message (encrypted) stored for the client.
        """
        if key in self.storage:
            self.storage[key].append(value)
        else:
            self.storage[key] = [value]

    def subscribeClient(self, name, host, port):
        if name not in self.clientList:
            self.clientList[name] = (host, port)
        else:
            self.clientList[name] = (host, port)

    def saveInDB(self, databaseName):
        data = [self.name, self.port, self.host, self.pubk]
        db = sqlite3.connect(databaseName)
        c = db.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY, name text, port integer, host text, pubk blob)'''%"Providers")
        insertQuery = "INSERT INTO Providers VALUES(?, ?, ?, ?, ?)"
        c.execute(insertQuery, [None, self.name, str(self.port), self.host, sqlite3.Binary(petlib.pack.encode(self.pubk))])
        db.commit()
        db.close()
        print "[%s] > Provider public information saved in database." % self.name

    def turnOnMeasurments(self):
        lc = task.LoopingCall(self.takeMeasurments)
        lc.start(MEASURE_TIME, False)

    def saveMeasurments(self):
        lc = task.LoopingCall(self.save_to_file)
        lc.start(SAVE_MEASURMENTS_TIME, False)

    def takeMeasurments(self):
        self.measurments.append([self.bProcessed, self.pProcessed, self.otherProc, self.mReceived])
        self.bProcessed = 0
        self.pProcessed = 0
        self.otherProc = 0
        self.mReceived = 0

    def save_to_file(self):
        try:
            with open("performanceProvider.csv", "ab") as outfile:
                csvW = csv.writer(outfile, delimiter=',')
                csvW.writerows(self.measurments)
            self.measurments = []
        except Exception, e:
            print "ERROR saving to file: ", str(e)
