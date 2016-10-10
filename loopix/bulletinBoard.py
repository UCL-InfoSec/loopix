from twisted.internet.protocol import DatagramProtocol
import petlib.pack
from petlib.ec import EcGroup, EcPt
from twisted.internet import protocol, reactor, defer
import format3


class BulletinBoard(DatagramProtocol):
    """Bulletin Board is responsible for gathering all
    public informations from the mixes and clients and allows
    all participants of the protocol to pull these information.
    """

    def __init__(self, port, host):
        """The BulletinBoard constructor.

                Keyword arguments:
                port -- port on which bulletin board is listening for connection
                host -- bulletin board host
        """
        self.port = port
        self.host = host
        self.mixnetwork = []
        self.usersPubs = []
        self.providers = []
        self.USERS_DATA_FILE = 'clientsPubs.txt'

    def startProtocol(self):
        """ Function starts the Bulletin Board protocol """

        print "> BulletinBoard started."

    def stopProtocol(self):
        """ Function stops the Bulletin Board protocol """

        print "BulletinBoard stoped."

    def datagramReceived(self, data, (host, port)):
        """ The Bulleting Board can receive:
                - notification from the mixnode, which is annoucing its availability in the network,
                - request from the providers to transfer the information about mixnetwork,
                - request for the publica information about the users using the system,
                - pull request from the mixnodes to send current network status (what mixnodes are active).

                Args:
                data (str): data received by the Bulletin Board,
                host (str): host of the client/server which sent the message,
                port (int): port of the client/server which sent the message.
        """

        if data[:4] == "INFO":
            print "> BulletinBoard received request for mixes information from %s, %d " % (host, port)
            print "> Sending Mixnet Info."
            self.sendMixnetData(host, port)
        if data[:4] == "UREQ":
            self.sendUsersData(host, port)
        if data[:4] == "MINF":
            print "> BulletinBoard received public information from mixnode %s, %d" % (host, port)
            dataMix = petlib.pack.decode(data[4:])
            self.addMixnode(dataMix)
        if data[:4] == "UINF":
            dataUser = petlib.pack.decode(data[4:])
            self.addUser(dataUser)
        if data[:4] == "PINF":
            dataprovider = petlib.pack.decode(data[4:])
            self.addProvider(dataProvider)
        if data[:4] == "PULL":
            print "> Request for public mixnode information from mix %s, %d" % (host, port)
            self.sendMixnetData(host, port)

    def sendMixnetData(self, host, port):
        """ This function packs the current list of active mixnodes in the network into a packet
                and forwards to a specified port/host

                Args:
                host (str): host of the client/server where the data is send,
                port (int): port of the client/server where the data is send.
        """

        mixnetInfo = petlib.pack.encode(self.mixnetwork)
        self.transport.write("RINF" + mixnetInfo, (host, port))

    def sendUsersData(self, host, port):
        """ This function packs the current list of users in the network into a packet
                and forwards to a specified port/host

                Args:
                host (str): host of the client/server where the data is send,
                port (int): port of the client/server where the data is send.
        """
        for user in self.usersPubs:
            encoded = petlib.pack.encode([user])
            try:
                self.transport.write("UPUB" + encoded, (host, port))
            except Exception, e:
                print "akuku", str(e)


    def addMixnode(self, dataMix):
        """ This function adds a new mixnode information the the public
        bulletin board list of all active mixnodes in the network.

                Args:
                dataMix (list): list mixnode public information.
        """
        tmpMix = format3.Mix(dataMix[0], dataMix[1], dataMix[2], dataMix[3])
        if tmpMix not in self.mixnetwork:
            self.mixnetwork.append(tmpMix)

    def addUser(self, dataUser):
        """ This function adds a new users public information to the board, to allow other users to look up for
        contact information.

            Args:
            dataUser (list) : list of public user information.
        """

        tmpUser = format3.User(dataUser[0], dataUser[1], dataUser[2], dataUser[3], dataUser[4])
        if tmpUser not in self.usersPubs:
            self.usersPubs.append(tmpUser)

    def addProvider(self, dataProvider):
        """ Function adds a new providers information to the board list, to allow other participants of the systems 
            to ask about providers information.

            Args:
            dataProvider (list) : list of provider public information.

        """
        tmpProvider = format3.Mix(dataProvider[0], dataProvider[1], dataProvider[2], dataProvider[3])
        if tmpProvider not in self.providers:
            self.providers.append(tmpProvider)
