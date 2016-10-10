import pytest
from twisted.test import proto_helpers
from mixnode import MixNode
from bulletinBoard import BulletinBoard
import format3
import petlib.pack
from client import Client
from provider import Provider
import base64
import codecs

@pytest.fixture
def testBoard():
	board = BulletinBoard(9998, "127.0.0.1")
	transport = proto_helpers.FakeDatagramTransport()
	board.transport = transport
	setup = format3.setup()
	return setup, board

def testSendMixnetData(testBoard):
	setup, board = testBoard
	mix = MixNode("A", 8000, "127.0.0.1", setup)
	board.addMixnode([mix.name, mix.port, mix.host, mix.pubk])
	board.sendMixnetData("127.0.0.1", 8000)
	msg, addr = board.transport.written[0]
	assert addr == ("127.0.0.1", 8000)
	assert msg == "RINF" + petlib.pack.encode(board.mixnetwork)

def testSendUsersData(testBoard):
	setup, board = testBoard
	client = Client(setup, "test@mail.com", 7000, "127.0.0.1")
	provider = Provider("ClientProvider", 8000, "127.0.0.1", format3.setup())
	client.provider = format3.Mix(provider.name, provider.port, provider.host, provider.pubk)
	board.usersPubs.append(format3.User(client.name, client.port, client.host, client.pubk, client.provider))
	board.sendUsersData("127.0.0.1", 8000)
	msg, addr = board.transport.written[0]
	assert addr == ("127.0.0.1", 8000)
	assert msg.startswith('UPUB')

def testAddMixnode(testBoard):
	setup, board = testBoard
	mix = MixNode("A@mail.com", 8000, "127.0.0.1", setup)
	board.addMixnode([mix.name, mix.port, mix.host, mix.pubk])
	assert format3.Mix(mix.name, mix.port, mix.host, mix.pubk) in board.mixnetwork

def testAddUser(testBoard):
	setup, board = testBoard
	user = Client(setup, "TestClient", 8000, "127.0.0.1")
	provider = Provider("ProviderTest", 8001, "127.0.0.1", setup)
	userProvider = format3.Mix(provider.name, provider.port, provider.host, provider.pubk)
	board.addUser([user.name, user.port, user.host, user.pubk, userProvider])
	assert format3.User(user.name, user.port, user.host, user.pubk, userProvider) in board.usersPubs

def testAddProvider(testBoard):
	setup, board = testBoard
	provider = Provider("ProviderTest", 8001, "127.0.0.1", setup)
	board.addProvider([provider.name, provider.port, provider.host, provider.pubk])
	assert format3.Mix(provider.name, provider.port, provider.host, provider.pubk) in board.providers


