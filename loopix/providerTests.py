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
	client.provider = format3.Provider(provider.name, provider.port, provider.host, provider.pubk)

	provider_r = Provider("ClientProvider", 7999, "134.0.0.1", setup)
	receiver = Client(setup, "receiver@mail.com", 7001, "173.0.0.1")
	receiver.provider = format3.Provider(provider_r.name, provider_r.port, provider_r.host, provider_r.pubk)
	provider_r.clientList[receiver.name] = (receiver.host, receiver.port)

	mix = MixNode("M8001", 8001, "100.0.0.1", setup)
	mixPub = format3.Mix(mix.name, mix.port, mix.host, mix.pubk, 0)

	return client, receiver, provider_r, mix

@pytest.fixture
def testMessage(testProvider, testParticipants):
	setup, provider = testProvider
	client, receiver, provider_r, mix = testParticipants
	
	receiverPub = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)
	mixPub = format3.Mix(mix.name, mix.port, mix.host, mix.pubk, 0)

	(header, body) = client.makeSphinxPacket(receiverPub, [mixPub], setup, "Test", "TestBounce")

	return (header, body)


def testProviderStart(testProvider):
	board = BulletinBoard(9998, "127.0.0.1")
	board.transport = proto_helpers.FakeDatagramTransport()

	setup, provider = testProvider

	provider.startProtocol()
	assert "INFO", ("127.0.0.1", 9998) == provider.transport.written[0]


def testSaveInStorage(testProvider):
 	setup, provider = testProvider
 	testKey, testValue = 7000, "ABC"
 	provider.saveInStorage(testKey, testValue)
 	assert testKey in provider.storage.keys()
 	assert testValue, _ == petlib.pack.decode(provider.storage[testKey].pop())


def testDropMessage(testProvider, testParticipants):
	setup, provider = testProvider
	client, receiver, provider_r, mix = testParticipants
	receiverPub = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)
	client.usersPubs.append(receiverPub)

	mixPub = format3.Mix(mix.name, mix.port, mix.host, mix.pubk, 0)
	header, body = client.createDropMessage([mixPub])

	ret_val = provider.process_sphinx_packet((header, body))
	(tag1, info1, (header1, body1)) = ret_val
	addr, dropFlag, typeFlag, delay, name = petlib.pack.decode(info1)[1]
	assert dropFlag == False

	ret_val1 = mix.process_sphinx_packet((header1, body1))
	(tag2, info2, (header2, body2)) = ret_val1
	addr, dropFlag, typeFlag, delay, name = petlib.pack.decode(info2)[1]
	assert dropFlag == False

	provider_r.do_ROUT((header2, body2), (mix.port, mix.host))
	


