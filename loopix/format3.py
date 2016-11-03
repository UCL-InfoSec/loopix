# format 3
from os import urandom
from collections import namedtuple
from binascii import hexlify
from copy import copy
import math

from hashlib import sha512, sha1
import hmac

import msgpack

from petlib.ec import EcGroup
from petlib.ec import EcPt
from petlib.bn import Bn
from petlib.cipher import Cipher
import base64
import petlib.pack
import binascii

import time

Keys = namedtuple('Keys', ['b', 'iv', 'kmac', 'kenc'])
Mix = namedtuple('Mix', ['name', 'port', 'host', 'pubk'])
User = namedtuple('User', ['name', 'port', 'host', 'pubk', 'provider'])


def sampleData(setup):
    mix1 = MixNode("M1", '8001', setup)
    mix2 = MixNode("M2", '8002', setup)

    receiver = MixNode('B', '9999', setup)
    return (mix1, mix2, receiver)


def KDF(element, idx="A"):
    ''' The key derivation function for b, iv, and keys '''
    keys = sha512(element + idx).digest()
    return Keys(keys[:16], keys[16:32], keys[32:48], keys[48:64])


def setup():
    ''' Setup the parameters of the mix crypto-system '''
    G = EcGroup()
    o = G.order()
    g = G.generator()
    o_bytes = int(math.ceil(math.log(float(int(o))) / math.log(256)))
    return G, o, g, o_bytes


def printPath(path):
	for node in path:
		printMixInfo(node)

def computeSharedSecrets(sender, path, setup):
	G, o, g, o_bytes = setup
	Bs = [] # list of blinding factors
	pubs = [] # list of public values shared between Alice and mix nodes
	shared_secrets = [] # list of shared secret keys between Alice and each mixnode

	rand_nonce = G.order().random()
	init_pub = rand_nonce * sender.pubk
	pubs = [init_pub] # pubs = [sedner.pub]
	prod_bs = Bn(1)
	
	for i, node in enumerate(path):
		xysec = (sender.privk * rand_nonce * prod_bs) * node.pubk
		shared_secrets.append(xysec)

		# blinding factors
		k = KDF(xysec.export())
		b = Bn.from_binary(k.b) % o
		Bs.append(b)
		prod_bs = (b * prod_bs) % o
		pubs.append(prod_bs * init_pub)

	return Bs, pubs, shared_secrets

def deriveKeys(all_factors, shared_secrets):
	all_keys = []
	for bs, Ksec in zip(all_factors, shared_secrets):
		
		kforw = KDF(Ksec.export())
		kback = KDF((bs * Ksec).export())

		all_keys.append((kforw, kback))

	return all_keys

def create_mixpacket_format(sender, receiver, mixes, setup, dest_message='', return_message='', delay=[], dropMsgFlag=0, typeFlag=None):
	''' Function builds a message package '''
	G, o, g, o_bytes = setup

	round_trip = mixes + [receiver] + list(reversed(mixes))

	# Take sender data
	_, saddr, spub, s = sender.name, sender.port, sender.pubk, sender.privk

	# Compute blinding factors, public elements and shared keys
	Bs, pubs, shared_secrets = computeSharedSecrets(sender, round_trip, setup)

	# Precompute the correction factors
	correction_factors = []

	for i in range(len(mixes)):

	 	total_b = Bn(1)
	 	for j in range(i, 2 * len(mixes) - i):
	 		total_b = (total_b * Bs[j]) % o

	 	correction_factors.append(total_b)

	all_factors = copy(correction_factors)
	all_factors += [Bn(1)]
	all_factors += [bf.mod_inverse(o) for bf in reversed(correction_factors)]

	# Derive all keys
	all_keys = deriveKeys(all_factors, shared_secrets)

	data = [sender] + round_trip + [sender]

	addressing = []
	for i in range(len(round_trip)):
		tmp = ((data[1+i-1].port, data[1+i-1].host, data[1+i-1].name), (data[1+i+1].port, data[1+i+1].host, data[1+i+1].name))
	 	addressing.append(tmp)

	# All data
	all_data = zip(round_trip, all_factors, pubs, addressing, all_keys)
	forward_stages = []
	backward_stages = []

	dropFlag = '0'

	delay_i = 0
	# Build the backward path
	msgback = return_message
	for j in range(len(mixes) + 1):
		mix, bs, yelem, (mixfrom, mixto), (kforw, kback) = all_data[j]
		the_bs = bs.mod_inverse(o)
		delay_i = (delay[j] if delay else 0)

		metadata = petlib.pack.encode(["1", dropFlag, typeFlag, delay_i, mixto, mixfrom])
		ciphertext_metadata = aes_enc_dec(kback.kenc, kback.iv, metadata)
		ciphertext_msgback = aes_enc_dec(kback.kenc, kback.iv, msgback)
		ciphertext = msgpack.packb([ciphertext_metadata, ciphertext_msgback]) 
		mac = hmac.new(kback.kmac, ciphertext_metadata, digestmod=sha1).digest()
		msgback = mac + ciphertext
		backward_stages.append(msgback)

	# Build the forward path
	msgforw = dest_message
	for i in range(len(mixes) + 1):
		j = len(mixes) - i
		if j == len(mixes)-1 and dropMsgFlag==1:
			dropFlag = '1'
		mix, bs, yelem, (mixfrom, mixto), (kforw, kback) = all_data[j]
		delay_i = (delay[j] if delay else 0)

		metadata = petlib.pack.encode(["0", dropFlag, typeFlag, delay_i, mixfrom, mixto, bs])
		ciphertext_metadata = aes_enc_dec(kforw.kenc, kforw.iv, metadata)
		ciphertext_msgforw = aes_enc_dec(kforw.kenc, kforw.iv, msgforw)
		ciphertext = msgpack.packb([ciphertext_metadata, ciphertext_msgforw])
		mac = hmac.new(kforw.kmac, ciphertext_metadata, digestmod=sha1).digest()
		msgforw = mac + ciphertext
		forward_stages.append(msgforw)
		dropFlag = '0'

	# Message: first 20 bytes is for MAC, next 60 bytes is for header and the rest is for message
	stages = zip(list(reversed(forward_stages)), backward_stages)

	# # checking
	# plaintext2 = msgforw
	# if __debug__:
	#  	for j in range(len(mixes) + 1):
	#  		msg_f, msg_b = stages.pop(0)
	#  		mix, bs, yelem, (xfrom, xto), (k1, k2) = all_data[j]

	#  		ciphertext_metadata, ciphertext_body = msgpack.unpackb(msg_f[20:])
	#  		plain_metadata, plain_body = msgpack.unpackb(plaintext2[20:])

	#  		mac1 = hmac.new(k1.kmac, ciphertext_metadata, digestmod=sha1).digest()
	#  		mac12 = hmac.new(k1.kmac, plaintext2[20:], digestmod=sha1).digest()

	#  		assert plaintext2[:20] == mac1, "Wrong mac in the forward header"

	#  		plaintext = aes_enc_dec(k1.kenc, k1.iv, ciphertext_body)

	#  		plaintext2 = aes_enc_dec(k1.kenc, k1.iv, ciphertext_body)
	#  	assert plaintext == dest_message, "Decryption went wrong in the background header"

	# # Debug for backward header
	# stages = zip(forward_stages, list(reversed(backward_stages)))
	# plaintext2 = msgback
	# if __debug__:
	# 	for j in range(len(mixes) + 1):
	# 		idx = len(mixes) - j
	# 		msg_f, msg_b = stages.pop(0)
	# 		mix, bs, yelem, (xfrom, xto), (k1, k2) = all_data[idx]
	# 		ciphertext_metadata, ciphertext_body = msgpack.unpackb(msg_b[20:])
	# 		plain_metadata, plain_body = msgpack.unpackb(plaintext2[20:])

	# 		mac2 = hmac.new(k2.kmac, ciphertext_metadata, digestmod=sha1).digest()

	# 		assert plaintext2[:20] == mac2, "Wrong mac in the backward header"

	#  		plaintext = aes_enc_dec(k2.kenc, k2.iv, ciphertext_body)

	#  		mac2b = hmac.new(k2.kmac, plain_metadata, digestmod=sha1).digest()
	#  		assert mac2b == mac2, "Wrong mac in the backward header"

	#  		plaintext2 = aes_enc_dec(k2.kenc, k2.iv, ciphertext_body)
	#  	assert plaintext == return_message, "Decryption went wrong in the background header"

	# # End __debug__

	final_element = pubs[0].export()
	save_element = pubs[-1].export()
	msgback = return_message
	return [save_element, final_element, msgforw, msgback]

# NOT IN USE
# def mix_operate(setup, mix, message, generate_return_message=False):
# 	""" THIS FUNCTION IS NOT CURRENTLY IN USE"""
# 	G, o, g, o_bytes = setup
# 	elem = message[0]
# 	forward = message[1]
# 	backward = message[2]
# 	element = EcPt.from_binary(elem, G)

# 	# Derive first key
#  	k1 = KDF((mix.privk * element).export())

#  	# Derive the blinding factor
#  	b = Bn.from_binary(k1.b) % o
#  	new_element = b * element

#  	# Check the forward MAC
#  	expected_mac = forward[:20]
#  	ciphertext_metadata, ciphertext_body = msgpack.unpackb(forward[20:])
# 	mac1 = hmac.new(k1.kmac, ciphertext_metadata, digestmod=sha1).digest()
# 	if not (expected_mac == mac1):
#  		raise Exception("WRONG MAC")

#  	# Decrypt the forward message
#  	enc_metadata = aes.dec(k1.kenc, k1.iv)
# 	enc_body = aes.dec(k1.kenc, k1.iv)
# 	pt = enc_body.update(ciphertext_body)
# 	pt += enc_body.finalize()
# 	header = enc_metadata.update(ciphertext_metadata)
# 	header += enc_metadata.finalize()

#  	# Parse the forward message
#  	xcode = header[0]
#  	if not (xcode == "0" or xcode == "1"):
#  		raise Exception("Wrong routing code")

#  	sf_flag = header[1]
#  	if xcode == "0":
#  		xfrom, xto, the_bs, new_forw = header[3:7], header[7:11], header[11:], pt
#  		old_bs = Bn.from_binary(base64.b64decode(the_bs))
#  		if old_bs == Bn(1):
#  			new_element = element

#  		k2 = format3.KDF(((self.privk * old_bs) * element).export())
# 		enc_metadata = aes.dec(k2.kenc, k2.iv)
# 		enc_body = aes.dec(k2.kenc, k2.iv)
# 		metadata = format3.paddString("1" + '0' + delay + str(xto) + str(xfrom), 60)
# 		new_back_metadata = enc_metadata.update(metadata)
# 		new_back_metadata += enc_metadata.finalize()
# 		new_back_body = enc_body.update(backward)
# 		new_back_body += enc_body.finalize()
# 		new_back_body = msgpack.packb([new_back_metadata, new_back_body])

# 		mac_back = hmac.new(k2.kmac, new_back_metadata, digestmod=sha1).digest()

# 		new_back = mac_back + new_back_body

#  		if generate_return_message:
#  			ret_elem = old_bs * element
#  			ret_forw = new_back
#  			ret_back = "None"

#  			return [ret_elem.export(), ret_forw, ret_back]
#  	else:

#  		xfrom, xto, new_forw = header[3:7], header[7:11], pt

#  		if not (backward == "None"):
#  			raise Exception("Backwards header should be None")

#  		new_back = "None"

# 	new_element = new_element.export()
# 	return [new_element, new_forw, new_back]


def paddString(input, length):
	il = len(input)
	return input + '0'*(length-il)


def aes_enc_dec(key, iv, input):
		"""A helper function which implements the AES-128 encryption in counter mode CTR"""

		aes = Cipher("AES-128-CTR")
		enc = aes.enc(key, iv)
		output = enc.update(input)
		output += enc.finalize()
		return output


def printMixInfo(mix):
	print "Name: ", mix.name
	print "Addr: ", mix.port
	print "PubK: ", mix.pubk
	print "Priv: ", mix.privk

# ------------------------TESTS-----------------------------
import pytest


def test_paddString():
	assert paddString("A", 10) == "A000000000"


def test_aes_enc_dec():
	from os import urandom

	aes = Cipher("AES-128-CTR")
	key = urandom(16)
	iv = urandom(16)
	enc = aes.enc(key, iv)
	ipt = "Hello"

	ciphertext = enc.update(ipt)
	ciphertext += enc.finalize()

	dec = aes.enc(key, iv)
	plaintext = dec.update(ciphertext)
	plaintext += dec.finalize()

	assert ipt == plaintext


def test_createPacket():
	from mixnode import MixNode
	from client import Client

	G = EcGroup(713)
	o = G.order()
	g = G.generator()
	o_bytes = int(math.ceil(math.log(float(int(o))) / math.log(256)))

	s = (G, o, g, o_bytes)
	mix1 = MixNode("M1", 8000, "127.0.0.1", s)
	mix1.privk = Bn.from_binary(base64.b64decode("z7yGAen5eAgHBRB9nrafE6h9V0kW/VO2zC7cPQ=="))
	mix1.pubk = mix1.privk * g

	mix2 = MixNode("M2", 8001, "127.0.0.1", s)
	mix2.privk = Bn.from_binary(base64.b64decode("266YjC8rEyiEpqXCNXCz1qXTEnwAsqz/tCyzcA=="))
	mix2.pubk = mix2.privk * g

	sender = MixNode('A', 7999, "127.0.0.1", s)
	sender.privk = Bn.from_binary(base64.b64decode("/m8A5kOfWNhP4BMcUm7DF0/G0/TBs2YH8KAYzQ=="))
	sender.pubk = sender.privk * g

	#receiver = MixNode('B', 8003, "127.0.0.1", s)
	privk = Bn.from_binary(base64.b64decode("DCATXyhAkzSiKaTgCirNJqYh40ha6dcXPw3Pqw=="))
	receiver = Client(s, 'B', 9999, "127.0.0.1")
	receiver.privk = privk
	receiver.pubk = receiver.privk * g

	mix_path = [Mix(mix1.name, mix1.port, mix1.host, mix1.pubk), Mix(mix2.name, mix2.port, mix2.host, mix2.pubk)]

	packet = create_mixpacket_format(sender, receiver, mix_path, s, "Hello", "Hello back")
	element = packet[0]
	message = packet[1:]

	xto2, message2, idt2, delay2 = mix1.mix_operate(s, message)
	xto3, message3, idt3, delay3 = mix2.mix_operate(s, message2)
	pt = receiver.readMessage(message3, ("127.0.0.1",9000))
	assert pt == "Hello"

