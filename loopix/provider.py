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

class Provider(MixNode):

    def __init__(self, name, port, host, setup, privk=None, pubk=None):
        """ A class representing a provider. """
        MixNode.__init__(self, name, port, host, setup, privk, pubk)

        self.clientList = {}
        self.usersPubs = []
        self.storage = {}
        self.replyBlocks = {}
        self.MAX_RETRIEVE = 500

        self.bSent = 0
        self.bReceived = 0
        self.bProcessed = 0
        self.gbSent = 0
        self.gbProcessed = 0
        self.otherProc = 0

        self.nMsgSent = 0
        self.testReceived = 0
        self.measurments = []
        self.testQueueSize = 0

        self.processQueue = ProcessQueue()

    def startProtocol(self):
        reactor.suggestThreadPoolSize(30)

        print "[%s] > Start protocol." % self.name
        
        reactor.callLater(10.0, self.turnOnProcessing)

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
        try:
            self.processQueue.put((data, (host, port)))
            self.bReceived += 1
        except Exception, e:
            print "[%s] > ERROR: %s " % (self.name, str(e))

    def do_PROCESS(self, obj):
        self.processMessage(obj)
        self.bProcessed += 1

        try:
            reactor.callFromThread(self.get_and_addCallback, self.do_PROCESS)
        except Exception, e:
            print "[%s] > ERROR: %s" % (self.name, str(e))

    def get_and_addCallback(self, f):
        self.processQueue.get().addCallback(f)

    def processMessage(self, (data, (host, port))):

        if data[:8] == "PULL_MSG":
            self.do_PULL(data[8:], (host, port))
            self.otherProc += 1
        elif data[:4] == "ROUT":
            try:
                idt, msgData = petlib.pack.decode(data[4:])
                #self.sendMessage("ACKN"+idt, (host, port))
                self.do_ROUT(msgData, (host, port))
                self.gbProcessed += 1
            except Exception, e:
                print "[%s] > ERROR: " % self.name, str(e)
        elif data[:4] == "ACKN":
            #if data in self.expectedACK:
            #    self.expectedACK.remove(data)
            self.otherProc += 1
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
        if name in self.storage:
            if self.storage[name]:
                for _ in range(self.MAX_RETRIEVE):
                    if self.storage[name]:
                        message = self.storage[name].pop()
                        self.sendMessage("PMSG" + message, (ip_host, port))
            else:
                self.sendMessage("NOMSG", (ip_host, port))
        else:
            self.sendMessage("NOASG", (ip_host, port))

    def do_ROUT(self, data, (host, port), tag=None):
        """ Function operates on the received route packet. First, the function decrypts one layer on the packet. Next, if 
        it is a forward message adds it to the queue. If it is a message destinated to one of the providers clients, the message 
        is saved in the storage, where it awaits for the client to fetch it.

                Args:
                data (str): traversing packet string,
                host (str): host of the sender of the packet
                port (int): port of the sender of the packet
        """

        try:
            peeledData = self.mix_operate(self.setup, data)
        except Exception, e:
            print "[%s] > ERROR during packet processing." % self.name
        else:
            if peeledData:
                (xtoPort, xtoHost, xtoName), msg_forw, idt, delay = peeledData
                if xtoName in self.clientList:
                    self.saveInStorage(xtoName, msg_forw)
                else:
                    try:
                        # if delay > 0:
                        #     reactor.callLater(delay, self.sendMessage, "ROUT" + petlib.pack.encode((idt ,msg_forw)), (xtoHost, xtoPort))
                        # else:
                        #     self.sendMessage("ROUT" + petlib.pack.encode((idt ,msg_forw)), (xtoHost, xtoPort))
                        reactor.callFromThread(self.send_or_delay, delay, petlib.pack.encode((idt, msg_forw)), (xtoHost, xtoPort))
                        # self.expectedACK.add("ACKN"+idt)
                    except Exception, e:
                        print "ERROR during ROUT: ", str(e)

    def saveInStorage(self, key, value):
        """ Function saves a message in the local storage, where it awaits till the client will fetch it.

                Args:
                key (int): clients key,
                value (str): message (encrypted) stored for the client.
        """
        if key in self.storage:
            self.storage[key].append(petlib.pack.encode((value, time.time())))
        else:
            self.storage[key] = [petlib.pack.encode((value, time.time()))]

    def subscribeClient(self, name, host, port):
        if name not in self.clientList:
            self.clientList[name] = (host, port)
        #else:
        #    self.clientList[name] = (host, port)

    def sendInfoMixnet(self, host, port):
        """ Function forwards the public information about the mixnodes and users in the system to the requesting address.

                Args:
                host (str): requesting host
                port (port): requesting port
        """
        if not self.mixList:
            self.transport.write("EMPT", (host, port))
        else:
            self.transport.write("RINF" + petlib.pack.encode(self.mixList), (host, port))

    def sendInfoUsers(self, host, port):
        if not self.usersPubs:
            self.transport.write("EMPT", (host, port))
        else:
            self.transport.write("UINF" + petlib.pack.encode(self.usersPubs), (host, port))

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
        lc.start(120, False)

    def saveMeasurments(self):
        lc = task.LoopingCall(self.save_to_file)
        lc.start(360, False)

    def takeMeasurments(self):
        self.measurments.append([self.bProcessed, self.gbProcessed, self.bReceived, self.pProcessed, self.otherProc])
        self.bProcessed = 0
        self.gbProcessed = 0
        self.bReceived = 0
        self.pProcessed = 0
        self.otherProc = 0

    def save_to_file(self):
        try:
            with open("performanceProvider.csv", "ab") as outfile:
                csvW = csv.writer(outfile, delimiter=',')
                csvW.writerows(self.measurments)
            self.measurments = []
        except Exception, e:
            print "ERROR saving to file: ", str(e)
