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

setup = format3.setup()

def sampleData(setup):
	mix1 = MixNode("M1", 8001, "127.0.0.1", setup)
	mix2 = MixNode("M2", 8002, "127.0.0.1", setup)
	receiver = MixNode('B', 9999, setup)
	return (mix1, mix2, receiver)

@pytest.fixture	
def testProvider():
	provider = Provider("Provider", 8000, "127.0.0.1", setup)
	provider.transport = proto_helpers.FakeDatagramTransport()
	return provider

@pytest.fixture
def testSender(testProvider):
	provider = testProvider
	provider_pub = format3.Mix(provider.name, provider.port, provider.host, provider.pubk)
	sender = Client(setup, "Client", 7000, "127.0.0.1")
	sender.provider = provider_pub
	sender.transport = proto_helpers.FakeDatagramTransport()
	return sender

@pytest.fixture
def testMixes():
	mix1 = MixNode("M1", 1234, "127.0.0.1", setup)
	mix1.transport = proto_helpers.FakeDatagramTransport()
	mix2 = MixNode("M2", 1369, "127.0.0.1", setup)
	mix2.transport = proto_helpers.FakeDatagramTransport()
	return (mix1, mix2)

@pytest.fixture
def testReceiver(testProvider):
	provider = testProvider
	provider_pub = format3.Mix(provider.name, provider.port, provider.host, provider.pubk)
	receiver = Client(setup, "Receiver", 7001, "127.0.0.1")
	receiver.provider = provider_pub
	receiver.transport = proto_helpers.FakeDatagramTransport()
	return receiver
	
@pytest.fixture	
def testParticipantsPubs(testSender, testMixes, testReceiver, testProvider):
	sender, (mix1, mix2), receiver, provider = testSender, testMixes, testReceiver, testProvider

	sender_pub = format3.User(sender.name, sender.port, sender.host, sender.pubk, sender.provider)
	receiver_pub = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)
	mix1_pub = format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk)
	mix2_pub = format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk)
	provider_pub = format3.Mix(provider.name, provider.port, provider.host, provider.pubk)

	return sender_pub, receiver_pub, mix1_pub, mix2_pub, provider_pub

@pytest.fixture
def testMessage(testSender, testParticipantsPubs):
	sender = testSender

	_, receiver, mix1, mix2, provider = testParticipantsPubs
	message, (host, port) = sender.makePacket(receiver, [mix1, mix2], sender.setup, "DEST_MSG", "BOUNCE_MSG")
	
	return message

# def testAnnouce(testMixes):
# 	mix, _ = testMixes
# 	mix.announce()
# 	announceMsg, addr = mix.transport.written[0]
# 	assert addr == ("127.0.0.1", 9998)
# 	assert announceMsg[:4] == "MINF"
# 	plainMsg = petlib.pack.decode(announceMsg[4:])
# 	assert plainMsg[0] ==  mix.name and plainMsg[1] == mix.port and plainMsg[2] == mix.host and plainMsg[3].pt_eq(mix.pubk)

# def testSendRequest(testMixes):
# 	mix, _ = testMixes
# 	mix.sendRequest("REQUEST")
# 	msg, addr = mix.transport.written[0]
# 	assert msg == "REQUEST"
# 	assert addr == ("127.0.0.1", 9998)

def testDo_INFO(testMixes):
	mix, mix2 = testMixes
	mix.do_INFO('', ("127.0.0.1", 1234))
	msg, addr = mix.transport.written[0]
	assert addr == ("127.0.0.1", 1234)
	assert msg == "RINF" + petlib.pack.encode([mix.name, mix.port, mix.host, mix.pubk])

def testDo_ROUT(testProvider, testMixes, testMessage):
	provider = testProvider
	(mix1, mix2) = testMixes
	message = testMessage
	
	provider.do_ROUT(petlib.pack.decode(message)[1], ("127.0.0.1", 7000))
	time, queuePacket = provider.Queue.pop()
	decodedPacket = petlib.pack.decode(queuePacket[0][4:])

	expectedMsg = mix1.mix_operate(setup, decodedPacket[1])
	mix1.seenMacs = []
	mix1.seenElements = []

	mix1.do_ROUT(decodedPacket[1], (provider.host, provider.port))
	time, queuePacket = mix1.Queue.pop()
	decodedPacket = petlib.pack.decode(queuePacket[0][4:])
	assert expectedMsg[1] == decodedPacket[1]

def testDo_BOUNCE(testSender, testProvider, testMixes, testMessage):
 	mix1, mix2 = testMixes
 	message = testMessage
 	xto1, msg1, idt1, delay1 = testProvider.mix_operate(setup, petlib.pack.decode(message)[1])
 	mix1.do_ROUT(msg1, (testProvider.host, testProvider.port))
 	time, queuePacket = mix1.Queue.pop()
 	mix1.sendMessage(queuePacket[0], queuePacket[1])
 	mix1.expectedACK.append("ACKN"+queuePacket[2])
 	[mix1.Queue.pop() for element in mix1.Queue]
 	mix1.do_BOUNCE(mix1.bounceInformation[mix1.expectedACK.pop()])
 	bounce_packet = mix1.Queue.pop()[1]
 	assert bounce_packet[1] == (testProvider.host, testProvider.port)
 	idt, msg = petlib.pack.decode(bounce_packet[0][4:])
 	xto_bnc, msg_bnc, idt_bnc, delay_bnc = testProvider.mix_operate(setup, msg)
 	
 	assert xto_bnc == [testSender.port, testSender.host, testSender.name]
 	assert testSender.readMessage(msg_bnc, (testProvider.host, testProvider.port)) == "BOUNCE_MSG"


def testDo_RINF(testMixes):
	mix1, mix2 = testMixes
	mix1.do_RINF(petlib.pack.encode([format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk)]))
	assert format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk) in mix1.mixList


def testSendHeartbeat(testMixes):
	mix1, mix2 = testMixes
	mix3 = MixNode("M3", 8003, "127.0.0.1", setup)
	provider = Provider("P1", 8000, "127.0.0.1", setup)
	mix3.transport = proto_helpers.FakeDatagramTransport()
	provider.transport = proto_helpers.FakeDatagramTransport()

	mix1.prvList.append(provider)
	predefinedPath = [format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk),
	 format3.Mix(mix3.name, mix3.port, mix3.host, mix3.pubk), format3.Mix(provider.name, provider.port, provider.host, provider.pubk)]
	mix1.sendHeartbeat([format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk),
	 format3.Mix(mix3.name, mix3.port, mix3.host, mix3.pubk)], predefinedPath)
	assert len(mix1.transport.written) == 1

	msg, addr = mix1.transport.written[0]
	assert addr == (mix2.host, mix2.port)

	xto, packet, idt, delay = mix2.mix_operate(mix2.setup, petlib.pack.decode(msg[4:])[1])
	assert xto == [mix3.port, mix3.host, mix3.name]


	xto, packet, idt, delay = mix3.mix_operate(mix1.setup, packet)
	assert xto == [provider.port, provider.host, provider.name]

	xto, packet, idt, delay = provider.mix_operate(provider.setup, packet)
	assert xto == [mix1.port, mix1.host, mix1.name]

	mix1.mix_operate(mix1.setup, packet)	


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

def testmix_operate(testProvider, testMixes, testMessage, testReceiver):
 	mix1, mix2 = testMixes
 	message = testMessage
 	xtoP, msgP, idtP, delayP = testProvider.mix_operate(setup, petlib.pack.decode(message)[1])
 	xto1, msg1, idt1, delay1 = mix1.mix_operate(setup, msgP)
 	xto2, msg2, idt2, delay2 = mix2.mix_operate(setup, msg1)
 	xtoP, msgP, idtP, delayP = testProvider.mix_operate(setup, msg2)
 	assert testReceiver.readMessage(msgP, (testProvider.host, testProvider.port)) == "DEST_MSG"


def testCheckSeenMAC(testMixes):
	mix1, mix2 = testMixes
	fake_mac = '0x23'
	fake_mac_2 = '0x32'
	mix1.seenMacs.add(fake_mac)
	assert mix1.checkMac(fake_mac) == True and mix1.checkMac(fake_mac_2) == False


def testAddToQueue(testMixes):
	mix1, mix2 = testMixes
	delay = 20
	current_epoch = sf.epoch()
	mix1.addToQueue(("Message", (mix2.host, mix2.port)), current_epoch + delay)
	assert (current_epoch + delay, ("Message", (mix2.host, mix2.port))) in mix1.Queue

def testSendMessage(testMixes):
	mix1, mix2 = testMixes
	mix1.sendMessage("Message", (mix2.host, mix2.port))
	msg, addr = mix1.transport.written[0]
	assert addr ==  (mix2.host, mix2.port)
	assert msg == "Message"


