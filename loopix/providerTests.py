# ------------------------TESTS-----------------------------
import pytest
from twisted.test import proto_helpers
from provider import Provider
import format3
from mixnode import MixNode
from bulletinBoard import BulletinBoard
import petlib.pack
from client import Client
import base64
import os


@pytest.fixture
def testProvider():
	setup = format3.setup()
	provider = Provider("ClientProvider", 8000, "127.0.0.1", setup)
	transport = proto_helpers.FakeDatagramTransport()
	provider.transport = transport
	return setup, provider

@pytest.fixture

def testParticipants(testProvider):
	setup, provider = testProvider
	client = Client(setup, "client@mail.com", 7000, "172.0.0.1")
	client.provider = format3.Mix(provider.name, provider.port, provider.host, provider.pubk)

	provider_r = Provider("ClientProvider", 7999, "134.0.0.1", setup)
	receiver = Client(setup, "receiver@mail.com", 7001, "173.0.0.1")
	receiver.provider = format3.Mix(provider_r.name, provider_r.port, provider_r.host, provider_r.pubk)
	provider_r.clientList[receiver.name] = (receiver.host, receiver.port)

	mix = MixNode("M8001", 8001, "100.0.0.1", setup)
	mixPub = format3.Mix(mix.name, mix.port, mix.host, mix.pubk)

	return client, receiver, provider_r, mix

@pytest.fixture
def testMessage(testProvider, testParticipants):
	setup, provider = testProvider
	client, receiver, provider_r, mix = testParticipants
	
	receiverPub = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)
	mixPub = format3.Mix(mix.name, mix.port, mix.host, mix.pubk)

	packet, destinationAddr = client.makePacket(receiverPub, [mixPub], setup, "Test", "TestBounce")

	return packet

def testProviderStart(testProvider):
	board = BulletinBoard(9998, "127.0.0.1")
	board.transport = proto_helpers.FakeDatagramTransport()

	setup, provider = testProvider

	provider.startProtocol()
	assert "INFO", ("127.0.0.1", 9998) == provider.transport.written[0]

def test_do_PULL(testProvider):
	setup, provider = testProvider
	TN_1, TH_1, TP_1 = ('N1', "127.0.0.1", 7000)
	TN_2, TH_2, TP_2 = ('N2', "134.0.0.1", 7001)
	TN_3, TH_3, TP_3 = ('N3', "169.1.1.1", 7002)
	
	provider.storage[TN_2] = []
	provider.storage[TN_3] = []

	provider.do_PULL(TN_1, (TH_1, TP_1))
	assert provider.transport.written[0] == ("NOASG", (TH_1, TP_1))

	provider.do_PULL(TN_2, (TH_2, TP_2))
	assert provider.transport.written[1] == ("NOMSG", (TH_2, TP_2))
	
	provider.transport = proto_helpers.FakeDatagramTransport()
	for i in range(provider.MAX_RETRIEVE+5):
		provider.storage[TN_3].append(petlib.pack.encode("TestMessage%d"%i))
	
	old_len = len(provider.storage[TN_3])	 
	provider.do_PULL(TN_3, (TH_3, TP_3))
	
	for i, msg in enumerate(provider.transport.written):
		assert msg, (TH_3, TP_3) == "PMSG" + petlib.pack.encode("TestMessage%d"%i)
	assert len(provider.storage[TN_3]) == old_len-provider.MAX_RETRIEVE

def testProviderRINFRequest(testProvider):
	setup, provider = testProvider
	testMix = MixNode("M8001", 8001, "127.0.0.1", setup)
	mixInfo = format3.Mix(testMix.name, testMix.port, testMix.host, testMix.pubk)
	provider.do_PROCESS(("RINF"+petlib.pack.encode([mixInfo]), ("127.0.0.1", 9000)))
	assert format3.Mix(testMix.name, testMix.port, testMix.host, testMix.pubk) in provider.mixList

def testProviderUPUBRequest(testProvider):
	setup, provider = testProvider
	client = Client(setup, "test@mail.com", 7000, "127.0.0.1")
	client.provider = format3.Mix(provider.name, provider.port, provider.host, provider.pubk)
	reqrsp = "UPUB" + petlib.pack.encode([[client.name, client.port, client.host, client.pubk, client.provider]])
	provider.do_PROCESS((reqrsp, ("127.0.0.1", 9999)))
	assert format3.User(client.name, client.port, client.host, client.pubk, 
		[client.provider.name, client.provider.port,
		client.provider.host, client.provider.pubk]) in provider.usersPubs 

def test_do_ROUT(testProvider, testMessage, testParticipants):
	setup, provider = testProvider
	client, receiver, provider_r, mix = testParticipants
	packetMessage = testMessage

	# when the provider is passing message into the network
	idt, msgData = petlib.pack.decode(packetMessage)
	provider.do_ROUT(msgData, (client.host, client.port))

	assert provider.storage == {}

	timestamp, packetInfo = provider.Queue.pop(0)
	assert packetInfo[1] == (mix.host, mix.port) 

	# when the message is destinated for the receiver
	provider.sendMessage(packetInfo[0], packetInfo[1])
	msg, destination = provider.transport.written[0]
	next_dest, peeledMsg, _, _ = mix.mix_operate(setup,petlib.pack.decode(msg[4:])[1])
	
	destAddr, expectedMsg, idt, timestamp = provider_r.mix_operate(setup, peeledMsg)
	provider_r.seenMacs = []
	provider_r.seenElements = []
	
	provider_r.do_ROUT(peeledMsg, (mix.host, mix.port))
	storedMsg, _ = petlib.pack.decode(provider_r.storage[receiver.name].pop()) 
	
	assert storedMsg == expectedMsg

def testSaveInStorage(testProvider):
	setup, provider = testProvider
	testKey, testValue = 7000, "ABC"
	provider.saveInStorage(testKey, testValue)
	assert testKey in provider.storage.keys()
	assert testValue, _ == petlib.pack.decode(provider.storage[testKey].pop())
	
def testSendInfoMixnet(testProvider):
	setup, provider = testProvider
	provider.sendInfoMixnet(7000, "111.1.1.1")
	assert provider.transport.written[0] == ("EMPT", (7000, "111.1.1.1"))

	mix = MixNode("M8001", 8001, "100.0.0.1", setup)
	mixPub = format3.Mix(mix.name, mix.port, mix.host, mix.pubk)
	provider.mixList.append(mixPub)
	provider.sendInfoMixnet(7000, "111.1.1.1")

	assert provider.transport.written[1] == ("RINF"+petlib.pack.encode(provider.mixList), (7000, "111.1.1.1"))

def testSendInfoUsers(testProvider):
	setup, provider = testProvider
	provider.sendInfoUsers(7000, "111.1.1.1")
	assert provider.transport.written[0] == ("EMPT", (7000, "111.1.1.1"))

	client = Client(setup, "client@mail.com", 7000, "172.0.0.1")
	client.provider = format3.Mix(provider.name, provider.port, provider.host, provider.pubk)
	clientPubs = format3.User(client.name, client.port, client.host, client.pubk, client.provider)
	provider.usersPubs.append(clientPubs)

	provider.sendInfoUsers(7000, "111.1.1.1")
	assert provider.transport.written[1] == ("UINF" + petlib.pack.encode(provider.usersPubs), (7000, "111.1.1.1"))


def testProviderACKNBack(testProvider):
	setup, provider = testProvider
	_fakeACK = "ACKN67194593"
	_fakeACK_2 = "ACKN67194594"
	provider.expectedACK.append(_fakeACK)
	provider.expectedACK.append(_fakeACK_2)
	provider.do_PROCESS((_fakeACK, ("127.0.0.1", 9999)))
	assert _fakeACK not in provider.expectedACK
	assert _fakeACK_2 in provider.expectedACK
