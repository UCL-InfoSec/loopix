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


from twisted.logger import jsonFileLogObserver, Logger
log = Logger(observer=jsonFileLogObserver(io.open("log.json", "a")))

class Provider(MixNode):

    def __init__(self, name, port, host, setup, privk=None, pubk=None):
        """ A class representing a provider. """
        MixNode.__init__(self, name, port, host, setup, privk, pubk)

        self.clientList = {}
        self.usersPubs = []
        self.storage = {}
        self.replyBlocks = {}
        self.MAX_RETRIEVE = 10000

        self.numMsgReceived = 0

    def startProtocol(self):
        print "[%s] > Start protocol." % self.name
        log.info("[%s] > Start protocol." % self.name)
        
        # self.transport.write("INFO", ("127.0.0.1", 9998))
        #print "[%s] > Request for network info sent." % self.name
        #log.info("[%s] > Request for network info sent." % self.name)

        self.run()
        self.d.addCallback(self.turnOnHeartbeats)
        self.d.addErrback(self.errbackHeartbeats)
        self.turnOnReliableUDP()
        self.readInData('example.db')
        self.measureMsgReceived()
        #self.saveInDB('example.db')

    def stopProtocol(self):
        print "[%s] > Stop protocol" % self.name
        log.info("[%s] > Stop protocol" % self.name)

    def datagramReceived(self, data, (host, port)):
        print "[%s] > received data from %s" % (self.name, host)
        log.info("[%s] > received data" % self.name)
        if data[:8] == "PULL_MSG":
            print "[%s] > Provider received pull messages request from (%s, %d)" % (self.name, host, port)
            log.info("[%s] > Provider received pull messages request from (%s, %d)" % (self.name, host, port))
            self.do_PULL(data[8:], (host, port))
        if data[:4] == "RINF":
            print "[%s] > Provider received mixnode metadata informations from bulletin board %s, %d" % (self.name, host, port)
            log.info("[%s] > Provider received mixnode metadata informations from bulletin board %s, %d" % (self.name, host, port))
            dataList = petlib.pack.decode(data[4:])
            for element in dataList:
                self.mixList.append(
                    format3.Mix(
                        element[0],
                        element[1],
                        element[2],
                        element[3]))
        if data[:4] == "UPUB":
            dataList = petlib.pack.decode(data[4:])
            for element in dataList:
                self.usersPubs.append(format3.User(element[0], element[1], element[2], element[3], element[4]))
            print "[%s] > Provider received public information of users registered in the system" % self.name
            log.info("[%s] > Provider received public information of users registered in the system" % self.name)
        if data[:4] == "INFO":
            self.sendInfoMixnet(host, port)
            print "[%s] > Provider received request for information from %s, %d " % (self.name, host, port)
            log.info("[%s] > Provider received request for information from %s, %d " % (self.name, host, port))
        if data[:4] == "ROUT":
            if (host, port) not in self.clientList:
                self.numMsgReceived += 1
            try:
                self.bReceived += sys.getsizeof(data[4:])
                idt, msgData = petlib.pack.decode(data[4:])
                self.sendMessage("ACKN"+idt, (host, port))
                self.do_ROUT(msgData, (host, port))
            except Exception, e:
                print "[%s] > ERROR: " % self.name, str(e)
                log.error("[%s] > Error during ROUT received: %s" % (self.name, str(e)))
        if data[:4] == "ACKN":
            if data in self.expectedACK:
                self.expectedACK.remove(data)
        if data[:4] == "PING":
            print "[%s] > provider received assign message from client (%s, %d)" % (self.name, host, port)
            log.info("[%s] > provider received assign message from client (%s, %d)" % (self.name, host, port))
            self.subscribeClient(data[4:], host, port)

    def do_PULL(self, name, (host, port)):
        """ Function which responds the pull message request from the client. First, the function checks if the requesting 
        client belogs to this provider, next takes all the messages destinated to this client and sends a fixed number of 
        messages to the client.

                Args:
                host (str): host of the requesting client,
                port (int): port of the requesting client.
        """
        def send_to_ip(IPAddrs):
            if name in self.storage.keys():
            #if host in self.storage.keys():
                if self.storage[name]:
                    for _ in range(self.MAX_RETRIEVE):
                        if self.storage[name]:
                            message = self.storage[name].pop(0)
                            self.transport.write("PMSG" + message, (IPAddrs, port))
                            print "[%s] > Message fetched for user (%s, %s, %d)." % (self.name, name, host, port)
                            log.info("[%s] > Message fetched for user (%s, %s, %d)." % (self.name, name, host, port))
                else:
                    self.transport.write("NOMSG", (IPAddrs, port))

            else:
                self.transport.write("NOASG", (IPAddrs, port))

        reactor.resolve(host).addCallback(send_to_ip)

    def do_ROUT(self, data, (host, port), tag=None):
        """ Function operates on the received route packet. First, the function decrypts one layer on the packet. Next, if 
        it is a forward message adds it to the queue. If it is a message destinated to one of the providers clients, the message 
        is saved in the storage, where it awaits for the client to fetch it.

                Args:
                data (str): traversing packet string,
                host (str): host of the sender of the packet
                port (int): port of the sender of the packet
        """
        print "[%s] > Received ROUT message from %s, %d " % (self.name, host, port)
        log.info("[%s] > Received ROUT message from %s, %d " % (self.name, host, port))
        try:
            peeledData = self.mix_operate(self.setup, data)
        except Exception, e:
            log.info("[%s] > error during packet processing." % self.name)
        else:
            if peeledData:
                (xtoPort, xtoHost, xtoName), msg_forw, idt, delay = peeledData
                def save_or_queue(IPAddrs):
                    if xtoName in self.clientList.keys():
                    #if (IPAddrs, int(xtoPort)) in self.clientList.values():
                        self.saveInStorage(xtoName, msg_forw)
                    else:
                        self.addToQueue(
                            ("ROUT" + petlib.pack.encode((idt ,msg_forw)), (IPAddrs, xtoPort), idt), delay)
                reactor.resolve(xtoHost).addCallback(save_or_queue)

    def saveInStorage(self, key, value):
        """ Function saves a message in the local storage, where it awaits till the client will fetch it.

                Args:
                key (int): clients key,
                value (str): message (encrypted) stored for the client.
        """
        if key not in self.storage.keys():
            self.storage[key] = [petlib.pack.encode((value, time.time()))]
        else:
            self.storage[key].append(petlib.pack.encode((value, time.time())))
        print "[%s] > Saved message for User %s in storage" % (self.name, key)
        log.info("[%s] > Saved message for User %s in storage" % (self.name, key))

    def subscribeClient(self, name, host, port):
        if name not in self.clientList.keys():
            self.clientList[name] = (host, port)
            print "[%s] > A new client subscribed to the provider. Current list: %s" % (self.name, str(self.clientList.keys()))
        else:
            self.clientList[name] = (host, port)
            print "[%s] > Client %s already subscribed to provider" % (self.name, name)
            

    def sendInfoMixnet(self, host, port):
        """ Function forwards the public information about the mixnodes and users in the system to the requesting address.

                Args:
                host (str): requesting host
                port (port): requesting port
        """
        if not self.mixList:
            self.transport.write("EMPT", (host, port))
        else:
            print "> Sending Mixnet Public Info."
            self.transport.write("RINF" + petlib.pack.encode(self.mixList), (host, port))

    def sendInfoUsers(self, host, port):
        print "Sending users info."
        if not self.usersPubs:
            self.transport.write("EMPT", (host, port))
        else:
            print "> Sending Users Public Info."
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
        log.info("[%s] > Provider public information saved in database." % self.name)


    def measureMsgReceived(self):
        lc = task.LoopingCall(self.saveNumbers)
        lc.start(60)

    def saveNumbers(self):
        print "----MEASURING MESSAGES RECEIVED--------"
        msgsR = self.numMsgReceived
        self.numMsgReceived = 0
        with open('messagesReceived.csv', 'ab') as outfile:
            csvW = csv.writer(outfile, delimiter=',')
            data = [[msgsR]]
            csvW.writerows(data)




