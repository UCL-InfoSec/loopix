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
import datetime
import uuid
import time


@pytest.fixture
def testParticipants():
    setup = format3.setup()
    sender = Client(setup, "Alice", 7999, "127.0.0.1")

    transport = proto_helpers.FakeDatagramTransport()
    sender.transport = transport

    provider_s = Provider("ClientProvider", 8000, "127.0.0.1", setup)
    provider_s.transport = proto_helpers.FakeDatagramTransport()
    provider_s.clientList[sender.name] = (sender.host, sender.port)

    provider_r = Provider("ReceiverProvider", 9000, "134.0.0.1", setup)
    provider_r.transport = proto_helpers.FakeDatagramTransport()

    sender.provider = format3.Mix(provider_s.name, provider_s.port, provider_s.host, provider_s.pubk)
    
    mix1 = MixNode("M8001", 8001, "127.0.0.1", setup)
    mix1.transport = proto_helpers.FakeDatagramTransport()

    mix2 = MixNode("M8002", 8002, "127.0.0.1", setup)
    mix2.transport = proto_helpers.FakeDatagramTransport()

    receiver = Client(setup, 'B', 9999, "127.0.0.1")
    provider_r.clientList[receiver.name] = (receiver.host, receiver.port)

    receiver.transport = proto_helpers.FakeDatagramTransport()
    receiver.provider = format3.Mix(provider_r.name, provider_r.port, provider_r.host, provider_r.pubk)

    sender.PATH_LENGTH = 2
    receiver.PATH_LENGTH = 2

    return setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver

def testStartClient(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    sender.startProtocol()

def testInitClient(testParticipants):
    setup = format3.setup()
    provider_s = Provider("ClientProvider", 8000, "127.0.0.1", setup)
    sender = Client(setup, "Alice", 7999, "127.0.0.1")
    sender.provider = format3.Mix(provider_s.name, provider_s.port, provider_s.host, provider_s.pubk)

    assert sender.name == "Alice"
    assert sender.setup == setup
    assert sender.port == 7999
    assert sender.host == "127.0.0.1"
    assert sender.provider.name == provider_s.name
    assert sender.provider.port == provider_s.port
    assert sender.provider.host == provider_s.host
    assert sender.provider.pubk == provider_s.pubk

# def test_announce(testParticipants):
#     setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
#     sender.announce()
#     assert sender.transport.written[0] == ("UINF" + petlib.pack.encode([sender.name, sender.port, sender.host, sender.pubk, sender.provider]), (sender.boardHost, sender.boardPort))


# def test_pullMixnetInfo(testParticipants):
#     setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
#     sender.pullMixnetInformation(provider_s.port, provider_s.host)
#     assert sender.transport.written[0] == ("INFO", (provider_s.host, provider_s.port))


# def test_pullUsersInfo(testParticipants):
#     setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
#     sender.pullUserInformation(provider_s.port, provider_s.host)
#     assert sender.transport.written[0] == ("UREQ", (provider_s.host, provider_s.port))


def test_pullMessages(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    sender.pullMessages()
    assert sender.transport.written[1] == ("PULL_MSG"+sender.name, (provider_s.host, provider_s.port))


def test_checkBuffer(testParticipants):
    setup, sender, transport, provider, (mix1, mix2), receiver = testParticipants
    sender.usersPubs.append(format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider))

    sender.checkBuffer([format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk), 
        format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk)])
    assert len(sender.transport.written) == 1, "During checking buffer one of the "\
    "following messages should be send: drop message or real message"


def test_makePacket(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants

    sender.receiver = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)
    sender.usersPubs.append(format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider))

    sender.mixnet.append(format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk))
    sender.mixnet.append(format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk))

    packet, addr = sender.makePacket(sender.receiver, sender.mixnet, sender.setup, "DESTMSG", "BOUNCE")

    assert addr == (sender.provider.host, sender.provider.port)

    dest1, m1, i1, delay1 = provider_s.mix_operate(setup, petlib.pack.decode(packet)[1])
    dest2, m2, i2, delay2 = mix1.mix_operate(setup, m1)
    dest3, m3, i3, delay3 = mix2.mix_operate(setup, m2)
    dest4, m4, i4, delay4 = provider_r.mix_operate(setup, m3)
    assert receiver.readMessage(m4, (provider_r.host, provider_r.port)) == "DESTMSG"


def test_sendHeartBeat(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    sender.pathLength = 1
    sender.mixnet.append(format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk))
    sender.mixnet.append(format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk))

    timestamp = time.time()
    sender.sendHeartBeat(sender.mixnet, timestamp, [format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk), 
        format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk)])

    assert sender.transport.written[0][1] == (sender.provider.host, sender.provider.port)

    provider_s.do_PROCESS((sender.transport.written[0][0], sender.transport.written[0][1]))
    sendtime, packet = provider_s.Queue.pop()
    assert packet[1] == (mix2.host, mix2.port)

    mix2.do_PROCESS((packet[0], packet[1]))
    sendtime, packet = mix2.Queue.pop()
    assert packet[1] == (mix1.host, mix1.port)

    mix1.do_PROCESS((packet[0], packet[1]))
    sendtime, packet = mix1.Queue.pop()
    assert packet[1] == (provider_s.host, provider_s.port)

    provider_s.do_PROCESS((packet[0], packet[1]))
    assert len(provider_s.storage[sender.name]) == 1 

    provider_s.do_PROCESS(("PULL_MSG", (sender.host, sender.port)))
    cmsg, caddr = provider_s.transport.written[-1]
    assert caddr == (sender.host, sender.port)

def test_duplicateMessage(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    sender.receiver = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)
    sender.usersPubs.append(format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider))

    sender.mixnet.append(format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk))
    sender.mixnet.append(format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk))

    packet, addr = sender.makePacket(sender.receiver, sender.mixnet, sender.setup, "DESTMSG", "BOUNCE")
    packet_dupl = packet
    assert addr == (sender.provider.host, sender.provider.port)

    encoded = provider_s.mix_operate(setup, petlib.pack.decode(packet)[1])
    encoded_dupl = provider_s.mix_operate(setup, petlib.pack.decode(packet_dupl)[1])
    assert encoded_dupl == None


def test_dropMessage(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    sender.mixnet.append(format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk))
    sender.mixnet.append(format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk))
    sender.usersPubs.append(format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)) 

    packet, (host, port) =  sender.createDropMessage(sender.mixnet)
    dest, msg, idt, delay = provider_s.mix_operate(setup, petlib.pack.decode(packet)[1])
    dest2, msg2, idt2, delay2 = mix1.mix_operate(setup, msg)
    dest3, msg3, idt3, delay3 = mix2.mix_operate(setup, msg2)
    assert provider_r.mix_operate(setup, msg3) == None


def test_readMessage(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants

    sender.sendMessage(format3.User(receiver.name, receiver.port, 
        receiver.host, receiver.pubk, receiver.provider), [format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk)],
    "MSGFORW", "MSGBACK")
    msg, addr = sender.buffer.pop()
    #provider_s.do_PROCESS((msg, addr))
    u = petlib.pack.decode(msg[4:])
    xto1, msg1, idt1, delay1 = provider_s.mix_operate(provider_s.setup, u[1])
    
    # time, packet = provider_s.Queue.pop()
    xto2, msg2, idt2, delay2 = mix1.mix_operate(mix1.setup, msg1)
    # time2, packet2 = mix1.Queue.pop()
    xto3, msg3, idt3, delay3 = provider_r.mix_operate(provider_r.setup, msg2)
    # msg, latency = petlib.pack.decode(provider_r.storage[receiver.name].pop())
    assert receiver.readMessage(msg3, (provider_r.host, provider_r.port)).startswith("MSGFORW")


def test_send(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    sender.send("Hello world", ("127.0.0.1", 8000))
    assert sender.transport.written[0] == ("Hello world", ("127.0.0.1", 8000))


def test_setExpParamsDelay(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    sender.setExpParamsDelay(10.0)
    assert sender.EXP_PARAMS_DELAY == (10.0, None)


def test_setExpParamsLoops(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    sender.setExpParamsLoops(20.0)
    assert sender.EXP_PARAMS_LOOPS == (20.0, None)


def test_setExpParamsCover(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    sender.setExpParamsCover(30.0)
    assert sender.EXP_PARAMS_COVER == (30.0, None)


def test_setExpParamsPayload(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    sender.setExpParamsPayload(40.0)
    assert sender.EXP_PARAMS_PAYLOAD == (40.0, None)


def test_encryptData(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    plaintext = "TESTMESSAGE"
    cipher = sender.encryptData(plaintext)

    aes = Cipher.aes_128_gcm()
    expectedCipher, tag = aes.quick_gcm_enc(sender.kenc, sender.iv, plaintext)
    assert tag + expectedCipher == cipher


def test_decryptData(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    plaintext = "TESTMESSAGE"
    aes = Cipher.aes_128_gcm()
    cipher, tag = aes.quick_gcm_enc(sender.kenc, sender.iv, plaintext)
    decrypt = sender.decryptData(tag + cipher)
    assert plaintext == decrypt


def test_takePathSequence(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    sender.mixnet.append(format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk))
    sender.mixnet.append(format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk))

    path = sender.takePathSequence(sender.mixnet, 2)
    assert len(path) == 2
    assert (format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk) in path and format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk) in path)

    path2 = sender.takePathSequence(sender.mixnet, 1)
    assert len(path2) == 1
    assert (format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk) in path2 or format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk) in path2)


def test_selectRandomReceiver(testParticipants):
    setup, sender, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
    G, o, g, o_bytes = setup
    
    assert sender.selectRandomReceiver() == None

    sender.usersPubs.append(format3.User("TestUSer", 1234, "127.0.0.1", g, format3.Mix(provider_r.name, provider_r.port, provider_r.host, provider_r.pubk)))
    assert sender.selectRandomReceiver() == format3.User("TestUSer", 1234, "127.0.0.1", g, format3.Mix(provider_r.name, provider_r.port, provider_r.host, provider_r.pubk))
   

def test_generateRandomNoise():
    assert len(generateRandomNoise(10)) == 10


def test_sampleFromExponential():
    from supportFunctions import sampleFromExponential
    assert type(sampleFromExponential((10.0, None))) == float


# def test_checkMsg(testParticipants):
#     import os
#     import time
#     setup, client, transport, (provider_s, provider_r), (mix1, mix2), receiver = testParticipants
#     mixes = [format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk)]
#     randomNoise = os.urandom(1000)
#     heartMsg = "TAG" + randomNoise
#     readyToSentPacket, addr = client.makePacket(client, mixes, client.setup, 'HT'+heartMsg, 'HB'+heartMsg)
#     client.send("ROUT" + readyToSentPacket, addr)
#     testTime = time.time()
#     client.tagedHeartbeat.append((testTime, heartMsg))

#     packet, addr = client.transport.written[0]
#     idt, msg = petlib.pack.decode(packet[4:])
#     dest1, msg1, idt1, delay1 = provider_s.mix_operate(setup, msg)
#     dest2, msg2, idt2, delay2 = mix1.mix_operate(setup, msg1)
#     dest2, msg2, idt2, delay2 = provider_s.mix_operate(setup, msg2) 
#     plaintext = client.readMessage(msg2, (provider_s.host, provider_s.port))
#     client.checkMsg(plaintext, testTime)

