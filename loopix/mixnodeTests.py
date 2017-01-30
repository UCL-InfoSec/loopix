# ------------------------TESTS-----------------------------
import pytest
from twisted.test import proto_helpers
import format3
import hmac
from hashlib import sha1
import base64
from mixnode import MixNode
import petlib.pack
from os import urandom
from petlib.cipher import Cipher
import calendar
import time
from client import Client
from provider import Provider
import datetime
import supportFunctions as sf 
import os
import sqlite3
import databaseConnect as dc

setup = format3.setup()

def sampleData(setup):
	mix1 = MixNode("M1", 8001, "127.0.0.1", setup)
	mix2 = MixNode("M2", 8002, "127.0.0.1", setup)
	receiver = MixNode('B', 9999, setup)
	return (mix1, mix2, receiver)

@pytest.fixture	
def testProvider():
	provider = Provider("Provider", 8000, "127.0.0.1", setup)
	provider.PATH_LENGTH = 3
	provider.transport = proto_helpers.FakeDatagramTransport()
	return provider

@pytest.fixture
def testSender(testProvider):
	provider = testProvider
	provider_pub = format3.Provider(provider.name, provider.port, provider.host, provider.pubk)
	sender = Client(setup, "Client", 7000, "127.0.0.1")
	sender.PATH_LENGTH = 3
	sender.provider = provider_pub
	sender.transport = proto_helpers.FakeDatagramTransport()
	return sender

@pytest.fixture
def testMixes():
	mix1 = MixNode("M1", 1234, "127.0.0.1", setup)
	mix1.transport = proto_helpers.FakeDatagramTransport()
	mix1.PATH_LENGTH = 3
	mix2 = MixNode("M2", 1369, "127.0.0.1", setup)
	mix2.transport = proto_helpers.FakeDatagramTransport()
	mix2.PATH_LENGTH = 3
	return (mix1, mix2)

@pytest.fixture
def testReceiver(testProvider):
	provider = testProvider
	provider_pub = format3.Provider(provider.name, provider.port, provider.host, provider.pubk)
	receiver = Client(setup, "Receiver", 7001, "127.0.0.1")
	receiver.PATH_LENGTH = 3
	receiver.provider = provider_pub
	receiver.transport = proto_helpers.FakeDatagramTransport()
	return receiver
	
# @pytest.fixture	
# def testParticipantsPubs(testSender, testMixes, testReceiver, testProvider):
# 	sender, (mix1, mix2), receiver, provider = testSender, testMixes, testReceiver, testProvider

# 	sender_pub = format3.User(sender.name, sender.port, sender.host, sender.pubk, sender.provider)
# 	receiver_pub = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)
# 	mix1_pub = format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk)
# 	mix2_pub = format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk)
# 	provider_pub = format3.Mix(provider.name, provider.port, provider.host, provider.pubk)

# 	return sender_pub, receiver_pub, mix1_pub, mix2_pub, provider_pub

@pytest.fixture
def testMessage(testSender, testReceiver, testMixes):
	sender = testSender

	receiver = testReceiver
	mix1, mix2 = testMixes

	sender.receiver = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)
	sender.mixnet = [format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk, 0), 
	format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 1)]

	mixpath = sender.mixnet
	message = sender.makeSphinxPacket(sender.receiver, mixpath, "Hello World")
	return message

@pytest.fixture
def testMixset():
	mix3 = MixNode("M3", 1233, "127.0.0.1", setup)
	mix3.transport = proto_helpers.FakeDatagramTransport()
	mix4 = MixNode("M4", 1363, "127.0.0.1", setup)
	mix4.transport = proto_helpers.FakeDatagramTransport()
	mix5 = MixNode("M5", 1233, "127.0.0.1", setup)
	mix5.transport = proto_helpers.FakeDatagramTransport()
	mix6 = MixNode("M6", 1266, "127.0.0.1", setup)
	mix6.transport = proto_helpers.FakeDatagramTransport()

	return (mix3, mix4, mix5, mix6)


def test_DB(testSender, testMixes, testReceiver, testProvider, testMixset):
	sender, (mix1, mix2), receiver, provider = testSender, testMixes, testReceiver, testProvider

	mix3, mix4, mix5, mix6 = testMixset

	if os.path.isfile("test.db"):
		os.remove("test.db")
    
	databaseName = "test.db"
	db = sqlite3.connect(databaseName)
	print "Database created and opened succesfully"

	c = db.cursor()
	dc.createUsersTable(db, "Users")
	dc.createProvidersTable(db, "Providers")
	dc.createMixnodesTable(db, "Mixnodes")

	insertClient = "INSERT INTO Users VALUES(?, ?, ?, ?, ?, ?)"
	c.execute(insertClient, [None, sender.name, sender.port, sender.host, sqlite3.Binary(petlib.pack.encode(sender.pubk)), provider.name]) 
	c.execute(insertClient, [None, receiver.name, receiver.port, receiver.host, sqlite3.Binary(petlib.pack.encode(receiver.pubk)), provider.name]) 
    
	db.commit()

	insertMixnode = "INSERT INTO Mixnodes VALUES(?, ?, ?, ?, ?, ?)"
	c.execute(insertMixnode, [None, mix1.name, mix1.port, mix1.host, 
        sqlite3.Binary(petlib.pack.encode(mix1.pubk)), 0])
	c.execute(insertMixnode, [None, mix3.name, mix3.port, mix3.host, 
        sqlite3.Binary(petlib.pack.encode(mix3.pubk)), 0])

	c.execute(insertMixnode, [None, mix2.name, mix2.port, mix2.host, 
        sqlite3.Binary(petlib.pack.encode(mix2.pubk)), 1])
	c.execute(insertMixnode, [None, mix4.name, mix4.port, mix4.host, 
        sqlite3.Binary(petlib.pack.encode(mix4.pubk)), 1])
    
	c.execute(insertMixnode, [None, mix5.name, mix5.port, mix5.host, 
        sqlite3.Binary(petlib.pack.encode(mix5.pubk)), 2])
	c.execute(insertMixnode, [None, mix6.name, mix6.port, mix6.host, 
        sqlite3.Binary(petlib.pack.encode(mix6.pubk)), 2])
    
	db.commit()
	insertProvider = "INSERT INTO Providers VALUES(?, ?, ?, ?, ?)"
	c.execute(insertProvider, [None, provider.name, provider.port, provider.host,
        sqlite3.Binary(petlib.pack.encode(provider.pubk))])

	db.commit()


def test_processMessage(testProvider, testMixes, testMessage):
	from sphinxmix.SphinxNode import sphinx_process

	provider = testProvider
	(mix1, mix2) = testMixes
	(header, body) = testMessage
	
	expected = sphinx_process(provider.params, provider.privk, header, body)

	ret_val = provider.process_sphinx_packet(testMessage)

	assert expected == ret_val

def test_createSphinxHeartbeat(testMixes):
	from sphinxmix.SphinxClient import Nenc, PFdecode, Dest_flag, receive_forward

	mix1, mix2 = testMixes
	mix3 = MixNode("M3", 8003, "127.0.0.1", setup)
	provider = Provider("P1", 8000, "127.0.0.1", setup)
	mix3.transport = proto_helpers.FakeDatagramTransport()
	provider.transport = proto_helpers.FakeDatagramTransport()

	(header, body) = mix1.createSphinxHeartbeat([format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 0), 
		format3.Mix(mix3.name, mix3.port, mix3.host, mix3.pubk, 1), 
		format3.Provider(provider.name, provider.port, provider.host, provider.pubk)], time.time())

	ret_val = mix2.process_sphinx_packet((header, body))
	(tag1, info1, (header1, body1)) = ret_val

	ret_val1 = mix3.process_sphinx_packet((header1, body1))
	(tag2, info2, (header2, body2)) = ret_val1

	ret_val2 = provider.process_sphinx_packet((header2, body2))
	(tag3, info3, (header3, body3)) = ret_val2

	ret_val3 = mix1.process_sphinx_packet((header3, body3))
	(tag4, info4, (header4, body4)) = ret_val3

	rounting = PFdecode(mix1.params, info4)
	if rounting[0] == Dest_flag:
		dest, message = receive_forward(mix1.params, body4)
	assert dest == [mix1.host, mix1.port, mix1.name]
	assert message.startswith('HT')


def testAES_ENC_DEC(testMixes):
	mix, _ = testMixes

	key = urandom(16)
	iv = urandom(16)
	plaintext = "TEST"

	aes = Cipher("AES-128-CTR")
	enc = aes.enc(key, iv)
	cipher = enc.update(plaintext)
	cipher += enc.finalize()
	
	assert cipher == mix.aes_enc_dec(key, iv, plaintext)


def test_takeMixnodesDataStratiefied(testSender, testMixes, testReceiver, testProvider, testMixset):
	mix1, mix2 = testMixes
	mix3, mix4, mix5, mix6 = testMixset
	test_DB(testSender, testMixes, testReceiver, testProvider, testMixset)

	mix1.STRATIFIED = True

	assert mix1.stratified_group == None
	mix1.readInData('test.db')
	assert mix1.stratified_group == 0

	assert mix1.mixList == [format3.Mix(mix3.name, mix3.port, mix3.host, mix3.pubk, 0), \
		format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 1), \
		format3.Mix(mix4.name, mix4.port, mix4.host, mix4.pubk, 1), \
		format3.Mix(mix5.name, mix5.port, mix5.host, mix5.pubk, 2), \
		format3.Mix(mix6.name, mix6.port, mix6.host, mix6.pubk, 2)]


def test_takeRandomPathSTMode(testMixes, testMixset, testProvider):
	mix1, mix2 = testMixes
	mix3, mix4, mix5, mix6 = testMixset
	provider = testProvider
	mix1.STRATIFIED = True

	mix1.mixList = [format3.Mix(mix3.name, mix3.port, mix3.host, mix3.pubk, 0), \
					format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 1), \
					format3.Mix(mix5.name, mix5.port, mix5.host, mix5.pubk, 2)]

	mix1.stratified_group = 0
	mix1.prvList.append(format3.Provider(provider.name, provider.port, provider.host, provider.pubk)) 
	path = mix1.takePathSequence(mix1.mixList, 3)
	assert path == [format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 1), \
		format3.Mix(mix5.name, mix5.port, mix5.host, mix5.pubk, 2), \
		format3.Provider(provider.name, provider.port, provider.host, provider.pubk)]


	mix1.stratified_group = 1
	mix1.prvList.append(format3.Provider(provider.name, provider.port, provider.host, provider.pubk)) 
	path = mix1.takePathSequence(mix1.mixList, 3)
	assert path == [format3.Mix(mix5.name, mix5.port, mix5.host, mix5.pubk, 2), \
		format3.Provider(provider.name, provider.port, provider.host, provider.pubk), \
		format3.Mix(mix3.name, mix3.port, mix3.host, mix3.pubk, 0)]

	mix1.stratified_group = 2
	mix1.prvList.append(format3.Provider(provider.name, provider.port, provider.host, provider.pubk)) 
	path = mix1.takePathSequence(mix1.mixList, 3)
	assert path == [format3.Provider(provider.name, provider.port, provider.host, provider.pubk), \
		format3.Mix(mix3.name, mix3.port, mix3.host, mix3.pubk, 0), \
		format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 1)]

	mix1.stratified_group = 0
	mix1.mixList = [format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 1), \
					format3.Mix(mix5.name, mix5.port, mix5.host, mix5.pubk, 2)]
	mix1.prvList.append(format3.Provider(provider.name, provider.port, provider.host, provider.pubk)) 
	path = mix1.takePathSequence(mix1.mixList, 3)
	assert path == [format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 1), \
		format3.Mix(mix5.name, mix5.port, mix5.host, mix5.pubk, 2), \
		format3.Provider(provider.name, provider.port, provider.host, provider.pubk)]


	mix1.stratified_group = 1
	mix1.mixList = [format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 0), \
					format3.Mix(mix5.name, mix5.port, mix5.host, mix5.pubk, 2)]
	mix1.prvList.append(format3.Provider(provider.name, provider.port, provider.host, provider.pubk)) 
	path = mix1.takePathSequence(mix1.mixList, 3) 
	assert path == [format3.Mix(mix5.name, mix5.port, mix5.host, mix5.pubk, 2), \
		format3.Provider(provider.name, provider.port, provider.host, provider.pubk), \
		format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 0)]

	mix1.stratified_group = 2
	mix1.mixList = [format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 0), \
					format3.Mix(mix5.name, mix5.port, mix5.host, mix5.pubk, 1)]
	mix1.prvList.append(format3.Provider(provider.name, provider.port, provider.host, provider.pubk)) 
	path = mix1.takePathSequence(mix1.mixList, 3)
	assert path == [format3.Provider(provider.name, provider.port, provider.host, provider.pubk), \
		format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 0), \
		format3.Mix(mix5.name, mix5.port, mix5.host, mix5.pubk, 1)]


