import sys
import os
from zope.interface import implements
from email.Header import Header

from twisted.mail import smtp, maildir
from twisted.internet import defer, reactor
from twisted.python import log
from twisted.application import service, internet

from sphinxmix.SphinxParams import SphinxParams
from loopix_client import LoopixClient


class LoopixMessageDelivery(object):
    implements(smtp.IMessageDelivery)
    #An implementor of smtp.IMessageDelivery, which describes how to process a message

    def __init__(self, protocol, baseDir, loopix_client):
        self.protocol = protocol
        self.baseDir = baseDir
        self.loopix_client = loopix_client
        self.name = self.loopix_client.name

    def receivedHeader(self, helo, origin, recipients):
        clientHostname, clientIP = helo
        myHostname = self.protocol.transport.getHost().host
        headerValue = "FROM: HOSTNAME: %s, IP: %s, SENDER: %s, BY %s with ESMTP ; %s" % (
                        clientHostname, clientIP, origin, myHostname, smtp.rfc822date())
        return Header(headerValue).encode()

    def _getAddressDir(self, address):
        return os.path.join(self.baseDir, "%s" % address)

    def validateTo(self, user):
        if user.dest.domain == "localhost":
            return lambda: MaildirMessage(self._getAddressDir(str(user.dest)), self.loopix_client)
        else:
            log.msg("Received email for invalid recipient %s" % user)
            raise smtp.SMTPBadRcpt(user)

    def validateFrom(self, helo, origin):
        return origin

class MaildirMessage(object):
    implements(smtp.IMessage)
    # Interface definition for messages that can be sent via SMTP.
    # An implementor of smtp.IMessage, which describes what to do with a received message

    def __init__(self, userDir, client):
        if not os.path.exists(userDir):
            os.mkdir(userDir)
        inboxDir = os.path.join(userDir, 'Inbox')
        self.lines = []

        self.client = client

    def lineReceived(self, line):
        self.lines.append(line)

    def eomReceived(self):
        print "New SMTP message received"
        self.lines.append('') # Add a trailing newline.
        messageData = '\n'.join(self.lines)
        self.client.put_into_buffer(messageData)
        return defer.succeed(None)

    def connectionLost():
        print "Connection lost unexpectedly!"
        del(self.lines)

class LoopixSMTPFactory(smtp.SMTPFactory):

    def __init__(self, baseDir, loopix_client):
        self.baseDir = baseDir
        self.loopix_client = loopix_client

    def buildProtocol(self, addr):
        proto = smtp.ESMTP()
        proto.delivery = LoopixMessageDelivery(proto, self.baseDir, self.loopix_client)
        return proto

# log.startLogging(sys.stdout)
# sec_params = SphinxParams(header_len=1024)
# clientParams = ['Client', 9999, '127.0.0.1', 'TestProvider']
# params = (sec_params, clientParams)
# proto = LoopixSMTPFactory("./tmp/mail", params)
# reactor.listenTCP(2500, proto)
# reactor.run()
