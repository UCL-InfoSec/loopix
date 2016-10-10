from twisted.internet import reactor
from bulletinBoard import BulletinBoard
from twisted.internet import stdio
from twisted.protocols import basic
import socket

class BoardEcho(basic.LineReceiver):
    from os import linesep as delimiter
    def __init__(self):
        self.board = BulletinBoard(9998, socket.gethostbyname(socket.gethostname()))
        reactor.listenUDP(9998, self.board)

    def connectionMade(self):
        self.transport.write('>>> ')

    def lineReceived(self, line):
        if line.upper() == "-E":
            reactor.stop()
        else:
            print "Command not found"
        self.transport.write('>>> ')

if __name__ == '__main__':
    stdio.StandardIO(BoardEcho())
    reactor.run()
