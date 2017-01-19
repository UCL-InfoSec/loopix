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

	sender.receiver = format3.User(receiver.name, receiver.port, receiver.host, receiver.pubk, receiver.provider)
	sender.mixnet = [format3.Mix(mix1.name, mix1.port, mix1.host, mix1.pubk), 
	format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk)]

	mixpath = sender.mixnet
	message = sender.makeSphinxPacket(sender.receiver, mixpath, "Hello World")
	return message


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

	(header, body) = mix1.createSphinxHeartbeat([format3.Mix(mix2.name, mix2.port, mix2.host, mix2.pubk), 
		format3.Mix(mix3.name, mix3.port, mix3.host, mix3.pubk), 
		format3.Mix(provider.name, provider.port, provider.host, provider.pubk)], time.time())

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

def test_sendTagedMessage(testMixes):
	pass

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
