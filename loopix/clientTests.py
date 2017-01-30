# ------------------------TESTS-----------------------------
import pytest
from twisted.test import proto_helpers
import format3
from client import Client
from supportFunctions import generateRandomNoise
from provider import Provider
from mixnode import MixNode
import petlib.pack
from petlib.cipher import Cipher
from os import urandom
import os
import datetime
import uuid
import time
import sqlite3
import databaseConnect as dc

@pytest.fixture
def testParticipants():

    setup = format3.setup()
    sender = Client(setup, "Alice", 7999, "127.0.0.1")
    sender.PATH_LENGTH = 3

    transport = proto_helpers.FakeDatagramTransport()
    sender.transport = transport

    provider_s = Provider("SenderProvider", 8000, "127.0.0.1", setup)
    provider_s.transport = proto_helpers.FakeDatagramTransport()
    provider_s.clientList[sender.name] = (sender.host, sender.port)

    receiver = Client(setup, 'Bob', 9999, "127.0.0.1")
    receiver.PATH_LENGTH = 3
    receiver.transport = proto_helpers.FakeDatagramTransport()

    provider_r = Provider("ReceiverProvider", 9000, "134.0.0.1", setup)
    provider_r.transport = proto_helpers.FakeDatagramTransport()
    provider_r.clientList[receiver.name] = (receiver.host, receiver.port)
    
    mix1 = MixNode("M8001", 8001, "127.0.0.1", setup)
    mix1.transport = proto_helpers.FakeDatagramTransport()

    mix2 = MixNode("M8002", 8002, "127.0.0.1", setup)
    mix2.transport = proto_helpers.FakeDatagramTransport()

    mix3 = MixNode("M8003", 8003, "127.0.0.1", setup)
    mix3.transport = proto_helpers.FakeDatagramTransport()

    sender.PATH_LENGTH = 3
    receiver.PATH_LENGTH = 3

    sender.providerId = provider_s.name
    receiver.providerId = provider_r.name

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
    c.execute(insertClient, [None, sender.name, sender.port, sender.host, sqlite3.Binary(petlib.pack.encode(sender.pubk)), provider_s.name]) 
    c.execute(insertClient, [None, receiver.name, receiver.port, receiver.host, sqlite3.Binary(petlib.pack.encode(receiver.pubk)), provider_r.name]) 
    
    db.commit()

    insertMixnode = "INSERT INTO Mixnodes VALUES(?, ?, ?, ?, ?, ?)"
    c.execute(insertMixnode, [None, mix1.name, mix1.port, mix1.host, 
        sqlite3.Binary(petlib.pack.encode(mix1.pubk)), 0])
    c.execute(insertMixnode, [None, mix2.name, mix2.port, mix2.host, 
        sqlite3.Binary(petlib.pack.encode(mix2.pubk)), 1])
    c.execute(insertMixnode, [None, mix3.name, mix3.port, mix3.host, 
        sqlite3.Binary(petlib.pack.encode(mix3.pubk)), 2])
    
    db.commit()
    insertProvider = "INSERT INTO Providers VALUES(?, ?, ?, ?, ?)"
    c.execute(insertProvider, [None, provider_s.name, provider_s.port, provider_s.host,
        sqlite3.Binary(petlib.pack.encode(provider_s.pubk))])
    c.execute(insertProvider, [None, provider_r.name, provider_r.port, provider_r.host,
        sqlite3.Binary(petlib.pack.encode(provider_r.pubk))])

    db.commit()

    sender.DATABASE = "test.db"
    sender.TESTMODE = False
    receiver.DATABASE = "test.db"
    receiver.TESTMODE = False

    return setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver

def testStartClient(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants

    sender.startProtocol()


def testInitClient(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.startProtocol()

    assert sender.name == "Alice"
    assert sender.setup == setup
    assert sender.port == 7999
    assert sender.host == "127.0.0.1"
    assert sender.provider.name == provider_s.name
    assert sender.provider.port == provider_s.port
    assert sender.provider.host == provider_s.host
    assert sender.provider.pubk == provider_s.pubk


def test_pullMessages(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.startProtocol()
    sender.pullMessages()
    # the first element in transport.written is the one from send ping in startprotocol
    assert sender.transport.written[1] == ("PING"+sender.name, (provider_s.host, provider_s.port))
    assert sender.transport.written[2] == ("PULL_MSG"+sender.name, (provider_s.host, provider_s.port))


def test_checkBuffer(testParticipants):
    setup, sender, transport, provider, (mix1, mix2, mix3), receiver = testParticipants
    sender.startProtocol()
    sender.STRATIFIED = False
    receiver.startProtocol()
    sender.usersPubs.append(format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider))

    old_queue = len(sender.transport.written)
    sender.checkBuffer(sender.mixnet)
    assert len(sender.transport.written) == old_queue + 1, "During checking buffer one of the "\
    # "following messages should be send: drop message or real message"

def test_sphinxPacket(testParticipants):
    from sphinxmix.SphinxParams import SphinxParams
    from sphinxmix.SphinxClient import pki_entry, Nenc, create_forward_message, rand_subset, PFdecode, Relay_flag, Dest_flag, Surb_flag, receive_forward
    from sphinxmix.SphinxNode import sphinx_process
    params = SphinxParams(header_len=1024)

    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.STRATIFIED = True
    sender.startProtocol()
    receiver.startProtocol()

    sender.receiver = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)
    #sender.usersPubs.append(format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider))

    # mixpath = rand_subset(sender.mixnet, 8)
    mixpath = sender.takePathSequence(sender.mixnet, 3)

    print mixpath
    message = sender.makeSphinxPacket(sender.receiver, mixpath, "Hello World")

    ret_val = provider_s.process_sphinx_packet(message)
    (tag, info, (header, body)) = ret_val

    ret_val2 = mix1.process_sphinx_packet((header, body))
    (tag2, info2, (header2, body2)) = ret_val2

    ret_val3 = mix2.process_sphinx_packet((header2, body2))
    (tag3, info3, (header3, body3)) = ret_val3

    ret_val4 = mix3.process_sphinx_packet((header3, body3))
    (tag4, info4, (header4, body4)) = ret_val4  

    ret_val5 = provider_r.process_sphinx_packet((header4, body4))
    (tag5, info5, (header5, body5)) = ret_val5      

    message = receiver.readMessage((header5, body5), (provider_r.host, provider_r.port))
    assert message == "Hello World"

def test_createSphinxHeartbeat(testParticipants):
    from sphinxmix.SphinxClient import PFdecode, receive_forward, Dest_flag

    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.STRATIFIED = False
    sender.startProtocol()
    receiver.startProtocol()

    mixpath = sender.takePathSequence(sender.mixnet, 3)

    timestamp = timestamp = '%.5f' % time.time()
    header, body = sender.createHeartbeat(mixpath, timestamp)

    ret_val = provider_s.process_sphinx_packet((header, body))
    (tag1, info1, (header1, body1)) = ret_val

    ret_val1 = mix1.process_sphinx_packet((header1,body1))
    (tag2, info2, (header2, body2)) = ret_val1

    ret_val2 = mix2.process_sphinx_packet((header2, body2))
    (tag3, info3, (header3, body3)) = ret_val2

    ret_val3 = mix3.process_sphinx_packet((header3, body3))
    (tag4, info4, (header4, body4)) = ret_val3

    ret_val4 = provider_s.process_sphinx_packet((header4, body4))
    (tag5, info5, (header5, body5)) = ret_val4

    message = sender.readMessage((header5, body5), (provider_s.host, provider_s.port))
    assert message.startswith('HT')


def test_createSphinxDropMessage(testParticipants):
    from sphinxmix.SphinxClient import PFdecode, receive_forward, Dest_flag, Relay_flag
    
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.STRATIFIED = False
    sender.startProtocol()
    receiver.startProtocol()
    
    mixpath = sender.takePathSequence(sender.mixnet, 3)

    timestamp = timestamp = '%.5f' % time.time()
    header, body = sender.createDropMessage(mixpath)

    ret_val = provider_s.process_sphinx_packet((header, body))
    (tag1, info1, (header1, body1)) = ret_val

    ret_val1 = mix1.process_sphinx_packet((header1,body1))
    (tag2, info2, (header2, body2)) = ret_val1

    ret_val2 = mix2.process_sphinx_packet((header2, body2))
    (tag3, info3, (header3, body3)) = ret_val2

    ret_val3 = mix3.process_sphinx_packet((header3, body3))
    (tag4, info4, (header4, body4)) = ret_val3

    #ret_val3 = provider_r.process_sphinx_packet((header3, body3))
    ret_val3 = provider_r.do_ROUT((header4, body4), (mix2.host, mix2.port))
    #(tag4, info4, (header4, body4)) = ret_val3    

    routing = PFdecode(provider_r.params, info4)
    assert routing[0] == Relay_flag
    next_addr, dropFlag, typeFlag, delay, next_name = routing[1]
    assert dropFlag == True


def test_readMessage(testParticipants):
    from sphinxmix.SphinxClient import pki_entry, Nenc, create_forward_message, rand_subset, PFdecode, Relay_flag, Dest_flag, Surb_flag, receive_forward

    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.STRATIFIED = False
    sender.startProtocol()
    receiver.startProtocol()

    mixpath = sender.takePathSequence(sender.mixnet, 3)
    sender.receiver = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)
    sender.sendMessage(sender.receiver, mixpath, "Hello world")

    assert len(sender.buffer) == 1
    data, addr = sender.buffer.pop() 

    header, body = petlib.pack.decode(data[4:])
    ret_val = provider_s.process_sphinx_packet((header, body))
    (tag1, info1, (header1, body1)) = ret_val

    ret_val1 = mix1.process_sphinx_packet((header1,body1))
    (tag2, info2, (header2, body2)) = ret_val1

    ret_val2 = mix2.process_sphinx_packet((header2, body2))
    (tag3, info3, (header3, body3)) = ret_val2

    ret_val3 = mix3.process_sphinx_packet((header3, body3))
    (tag4, info4, (header4, body4)) = ret_val3    

    ret_val4 = provider_r.process_sphinx_packet((header4, body4))
    (tag5, info5, (header5, body5)) = ret_val4

    message = receiver.readMessage((header5, body5), (provider_r.host, provider_r.port))
    assert message.startswith("Hello world")


def test_send(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.send("Hello world", ("127.0.0.1", 8000))
    assert sender.transport.written[0] == ("Hello world", ("127.0.0.1", 8000))


def test_setExpParamsDelay(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.setExpParamsDelay(10.0)
    assert sender.EXP_PARAMS_DELAY == (10.0, None)


def test_setExpParamsLoops(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.setExpParamsLoops(20.0)
    assert sender.EXP_PARAMS_LOOPS == (20.0, None)


def test_setExpParamsCover(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.setExpParamsCover(30.0)
    assert sender.EXP_PARAMS_COVER == (30.0, None)


def test_setExpParamsPayload(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.setExpParamsPayload(40.0)
    assert sender.EXP_PARAMS_PAYLOAD == (40.0, None)


def test_encryptData(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    plaintext = "TESTMESSAGE"
    cipher = sender.encryptData(plaintext)

    aes = Cipher.aes_128_gcm()
    expectedCipher, tag = aes.quick_gcm_enc(sender.kenc, sender.iv, plaintext)
    assert tag + expectedCipher == cipher


def test_decryptData(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    plaintext = "TESTMESSAGE"
    aes = Cipher.aes_128_gcm()
    cipher, tag = aes.quick_gcm_enc(sender.kenc, sender.iv, plaintext)
    decrypt = sender.decryptData(tag + cipher)
    assert plaintext == decrypt


def test_takePathSequence(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants

    mix3 = MixNode("M8003", 8003, "127.0.0.1", setup)
    mix3.transport = proto_helpers.FakeDatagramTransport()
    
    sender.STRATIFIED = True
    sender.mixnet = [format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk, 0), \
        format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 1), \
        format3.Mix(mix3.name, mix3.port, mix3.host, mix3.pubk, 2)]
    

    path = sender.takePathSequence(sender.mixnet, 3)
    assert path[0] == format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk, 0) and \
        path[1] == format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 1) and \
        path[2] == format3.Mix(mix3.name, mix3.port, mix3.host, mix3.pubk, 2)


def test_takeMixnodesDataSTMode(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.startProtocol()
    assert sender.mixnet == [format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk, 0), \
        format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk, 1), \
        format3.Mix(mix3.name, mix3.port, mix3.host, mix3.pubk, 2)]


def test_selectRandomReceiver(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    G, o, g, o_bytes = setup
    
    assert sender.selectRandomReceiver() == None

    sender.usersPubs.append(format3.User("TestUSer", 1234, "127.0.0.1", g, format3.Provider(provider_r.name, provider_r.port, provider_r.host, provider_r.pubk)))
    assert sender.selectRandomReceiver() == format3.User("TestUSer", 1234, "127.0.0.1", g, format3.Provider(provider_r.name, provider_r.port, provider_r.host, provider_r.pubk))
   

def test_generateRandomNoise():
    assert len(generateRandomNoise(10)) == 10


def test_sampleFromExponential():
    from supportFunctions import sampleFromExponential
    assert type(sampleFromExponential((10.0, None))) == float


def test_sendSphinxMessage(testParticipants):
    
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2, mix3), receiver = testParticipants
    sender.startProtocol()
    receiver.startProtocol()


    mixpath = sender.takePathSequence(sender.mixnet, 3)
    sender.receiver = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)

    sender.sendMessage(sender.receiver, mixpath, "Hello world")
    
    assert len(sender.buffer) == 1
    data, addr = sender.buffer.pop() 
    assert addr == (sender.provider.host, sender.provider.port)
    assert data[:4] == "ROUT"
