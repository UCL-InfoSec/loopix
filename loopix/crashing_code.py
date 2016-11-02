from client import Client
import format3
import os
from provider import Provider
import petlib.pack
from processQueue import ProcessQueue
from petlib.ec import EcPt, Bn, EcGroup
from petlib.cipher import Cipher
import msgpack
import hmac
from hashlib import sha512, sha1
import time
import pytest

from twisted.internet import reactor, task, defer, threads 

def readMessage(client, message, (host, port)):
	print "Reading message"
	""" Function allows to decyrpt and read a received message.

				Args:
				message (list) - received packet,
				host (str) - host of a provider,
				port (int) - port of a provider.
	"""
	elem = message[0]
	forward = message[1]
	backward = message[2]
	element = EcPt.from_binary(elem, client.G)

	if elem in client.sentElements:
		print "[%s] > Decrypted bounce:" % client.name
		return forward
	else:
		aes = Cipher("AES-128-CTR")
		k1 = format3.KDF((client.privk * element).export())
		b = Bn.from_binary(k1.b) % client.o
		new_element = b * element
		expected_mac = forward[:20]
		ciphertext_metadata, ciphertext_body = msgpack.unpackb(forward[20:])
		mac1 = hmac.new(k1.kmac, ciphertext_metadata, digestmod=sha1).digest()

		if not (expected_mac == mac1):
			raise Exception("> CLIENT %s : WRONG MAC ON PACKET" % client.name)

		enc_metadata = aes.dec(k1.kenc, k1.iv)
		enc_body = aes.dec(k1.kenc, k1.iv)
		pt = enc_body.update(ciphertext_body)
		pt += enc_body.finalize()
		header = enc_metadata.update(ciphertext_metadata)
		header += enc_metadata.finalize()
		header = petlib.pack.decode(header)

		if pt.startswith('HT'):
			print "[%s] > Decrypted heartbeat. " % client.name
			for i in client.heartbeatsSent:
				if i[0] == pt[2:]:
					client.numHeartbeatsReceived += 1
					latency = float(time.time()) - float(i[1])
					client.hearbeatLatency.append(latency)
			return pt
		else:
			print "[%s] > Decrypted message. " % client.name
			return pt

	reactor.callFromThread(client.processQueue.get().addCallback, readMessage)

def test_if_working():
	print "Just testing"
	processQueue = ProcessQueue()
	setup = format3.setup()
	client = Client(setup, "Test", 9999, "127.0.0.1", "Provider")
	provider = Provider("Provider", 8000, "127.0.0.1", setup)
	client.provider = provider

	dest = os.urandom(1000)
	back = os.urandom(1000)

	packet, addr = client.makePacket(client, [], setup, dest, back, False, None)

	dest, msg, idt, delay = provider.mix_operate(setup, petlib.pack.decode(packet)[1])
	dest2, msg2, idt2, delay2 = provider.mix_operate(setup, msg)

	processQueue.put((client, msg2, addr))

	c, msg, addr = processQueue.queue[0]
	readMessage(c, msg, addr)


if __name__ == "__main__":

	processQueue = ProcessQueue()
	setup = format3.setup()
	client = Client(setup, "Test", 9999, "127.0.0.1", "Provider")
	provider = Provider("Provider", 8000, "127.0.0.1", setup)
	client.provider = provider


	def add_to_queue():
		reactor.callLater(0.1, add_to_queue)

		dest = os.urandom(1000)
		back = os.urandom(1000)

		print "---Adding to queue----"
		try:
			packet, addr = client.makePacket(client, [], setup, dest, back, False, None)
		
			dest, msg, idt, delay = provider.mix_operate(setup, petlib.pack.decode(packet)[1])
			dest2, msg2, idt2, delay2 = provider.mix_operate(setup, msg)
			processQueue.put((client, msg2, addr))
			print len(processQueue.queue)
		except Exception, e:
			print "ERROR: ", str(e)

	add_to_queue()
	def process_queue(x):
		client, msg, addr = x
		readMessage(client, msg, addr)
		reactor.callFromThread(processQueue.get().addCallback, process_queue)

	processQueue.get().addCallback(process_queue)
	reactor.run()



