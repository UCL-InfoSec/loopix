import pytest
from loopix_client import LoopixClient
from loopix_mixnode import LoopixMixNode
from loopix_provider import LoopixProvider
from support_formats import Mix, Provider, User
from collections import namedtuple
import petlib.pack
from loopix.database_connect import DatabaseManager
import random
import sqlite3
import os
from core import group_layered_topology, take_mix_sequence, SphinxPacker
from sphinxmix.SphinxParams import SphinxParams

from twisted.test import proto_helpers
from twisted.internet import task, defer

import os.path
if os.path.isfile('test.db'):
    os.remove('test.db')

Env = namedtuple("Env",
             ["mixes", "pubs_mixes",
              "providers", "pubs_providers",
              "clients", "pubs_clients"])

dbManager = DatabaseManager('test.db')

@pytest.fixture
def loopix_mixes():
    sec_params = SphinxParams(header_len=1024)

    dbManager.create_mixnodes_table('Mixnodes')
    mixes = []
    pubs_mixes = []
    for i in range(3):
        mix = LoopixMixNode(sec_params, 'Mix%d'%(i+1), 9999-i, '1.2.3.%d'%i, i)
        mix.transport = proto_helpers.FakeDatagramTransport()
        mix.config_params = mix.config_params._replace(DATABASE_NAME = 'test.db')
        mixes.append(mix)
        dbManager.insert_row_into_table('Mixnodes',
                [None, mix.name, mix.port, mix.host,
                sqlite3.Binary(petlib.pack.encode(mix.pubk)), mix.group])
    pubs_mixes = [Mix(m.name, m.port, m.host, m.pubk, m.group) for m in mixes]
    return mixes, pubs_mixes

@pytest.fixture
def loopix_providers():
    sec_params = SphinxParams(header_len=1024)

    dbManager.create_providers_table('Providers')
    providers = []
    pubs_providers = []
    for i in range(3):
        p = LoopixProvider(sec_params, 'Provider%d'%(i+1), 9995-i, '1.2.%d.4'%i)
        p.transport = proto_helpers.FakeDatagramTransport()
        p.config_params = p.config_params._replace(DATABASE_NAME = 'test.db')
        providers.append(p)
        dbManager.insert_row_into_table('Providers',
            [None, p.name, p.port, p.host,
            sqlite3.Binary(petlib.pack.encode(p.pubk))])
    pubs_providers = [Provider(p.name, p.port, p.host, p.pubk) for p in providers]
    return providers, pubs_providers

@pytest.fixture
def loopix_clients(pubs_providers, pubs_mixes):

    sec_params = SphinxParams(header_len=1024)

    dbManager.create_users_table('Users')
    clients = []
    pubs_clients = []
    for i in range(3):
        provider = pubs_providers[i]
        c = LoopixClient(sec_params, 'Client%d'%(i+1), 9993 - i, '1.%d.3.4'%i, provider.name)
        c.register_mixes(pubs_mixes)
        c.transport = proto_helpers.FakeDatagramTransport()
        c.config_params = c.config_params._replace(DATABASE_NAME = 'test.db')
        c.provider = dbManager.select_provider_by_name(provider.name)
        clients.append(c)
        dbManager.insert_row_into_table('Users',
            [None, c.name, c.port, c.host,
            sqlite3.Binary(petlib.pack.encode(c.pubk)),
            c.provider.name])
    pubs_clients = [User(c.name, c.port, c.host, c.pubk, c.provider) for c in clients]
    return clients, pubs_clients

@pytest.fixture
def generate_env():
    mixes, pubs_mixes = loopix_mixes()
    providers, pubs_providers = loopix_providers()
    clients, pubs_clients = loopix_clients(pubs_providers, pubs_mixes)

    return Env(mixes, pubs_mixes,
               providers, pubs_providers,
               clients, pubs_clients)

env = generate_env()

def test_client_startProtocol():
    alice = env.clients[0]
    alice.startProtocol()
    pkt, addr = alice.transport.written[0]
    data = ['SUBSCRIBE', alice.name, alice.host, alice.port]
    assert pkt == petlib.pack.encode(data)
    assert alice.befriended_clients == env.pubs_clients
    assert alice.pubs_providers == env.pubs_providers
    assert alice.pubs_mixes == group_layered_topology(env.pubs_mixes)

    pkt, addr = alice.transport.written[1]
    assert pkt == petlib.pack.encode(['PULL', alice.name])

def test_client_send_loop_message():
    alice = env.clients[0]
    alice.send_loop_message()
    packet, addr = alice.transport.written[-1]

    alice_provider = [p for p in env.providers if p.name == alice.provider.name]
    header, body = client_process_message(packet, env.mixes, alice_provider.pop())
    encoded_packet = petlib.pack.encode((header, body))
    flag, packet = alice.read_packet(encoded_packet)
    assert flag == "NEW"
    assert packet[:2] == "HT"

def client_process_message(packet, mixes, provider):
    header, body = petlib.pack.decode(packet)
    path = [provider] + mixes + [provider]
    for e in path:
        flag, new_packet = e.crypto_node.process_packet((header, body))
        if flag == "ROUT":
            delay, header, body, next_addr, next_name = new_packet
    return header, body

def test_client_make_loop_stream():
    alice = env.clients[0]
    alice.transport.written = []
    alice.reactor = task.Clock()
    alice.make_loop_stream()
    assert len(alice.transport.written) == 1
    alice.reactor.advance(100)
    assert len(alice.transport.written) == 2
    calls = alice.reactor.getDelayedCalls()
    for c in calls:
        assert c.func == alice.make_loop_stream

def test_client_create_drop_message():
    alice = env.clients[0]
    alice.transport.written = []
    friend = env.pubs_clients[1]
    alice.register_friends([friend])
    alice.send_drop_message()
    packet, addr = alice.transport.written[-1]
    alice_provider = [p for p in env.providers if p.name == alice.provider.name].pop()
    friend_provider = [p for p in env.providers if p.name == friend.provider.name].pop()
    assert client_process_drop_message(packet, env.mixes, [alice_provider, friend_provider])

def client_process_drop_message(packet, mixes, providers):
    sender_provider, receiver_provider = providers
    path = [sender_provider] + mixes + [receiver_provider]
    header, body = petlib.pack.decode(packet)
    for i, e in enumerate(path):
        flag, new_packet = e.crypto_node.process_packet((header, body))
        if flag == "ROUT":
            delay, header, body, next_addr, next_name = new_packet
        if flag == "DROP" and not i == len(path)-1:
            return False
    return True

def test_client_make_drop_stream():
    alice = env.clients[0]
    alice.transport.written = []
    alice.reactor = task.Clock()
    alice.make_drop_stream()
    assert len(alice.transport.written) == 1
    alice.reactor.advance(100)
    assert len(alice.transport.written) == 2

    calls = alice.reactor.getDelayedCalls()
    for c in calls:
        assert c.func == alice.make_drop_stream

def test_client_subscribe():
    alice = env.clients[0]
    alice.transport.written = []
    alice.subscribe_to_provider()
    packet, addr =  alice.transport.written[-1]
    assert petlib.pack.decode(packet) == ['SUBSCRIBE'] + [alice.name, alice.host, alice.port]
    assert addr == (alice.provider.host, alice.provider.port)

def test_client_get_and_addCallback():
    alice = env.clients[0]
    alice.process_queue.put(('TestPacket', ('1.2.3.4', 1111)))
    alice.get_and_addCallback(alice.handle_packet)
    assert any(isinstance(x, defer.Deferred) for x in alice.process_queue.consumers)

def test_client_send():
    alice = env.clients[0]
    alice.send('Hello world')
    packet, addr = alice.transport.written[-1]
    assert petlib.pack.decode(packet) == 'Hello world'
    assert addr == (alice.provider.host, alice.provider.port)

def test_client_schedule_next_call():
    alice = env.clients[2]
    alice.reactor = task.Clock()
    def tmp_method():
        alice.send('Test')

    alice.schedule_next_call(3, tmp_method)
    alice.reactor.advance(150)
    packet, addr = alice.transport.written[-1]
    assert petlib.pack.decode(packet) == 'Test'
    assert addr == (alice.provider.host, alice.provider.port)

def test_client_make_real_stream():
    alice = env.clients[0]
    alice.transport.written = []
    alice.reactor = task.Clock()

    alice.make_real_stream()
    assert len(alice.transport.written) == 1
    alice.reactor.advance(100)
    assert len(alice.transport.written) == 2

    calls = alice.reactor.getDelayedCalls()
    for c in calls:
        assert c.func == alice.make_real_stream

    # Check whether a real message is sent if buffer non-empty
    receiver = env.pubs_clients[1]
    path = [alice.provider] + env.pubs_mixes + [receiver.provider]
    test_packet = 'ABCDefgHIJKlmnOPRstUWxyz'
    alice.output_buffer.put(test_packet)
    alice.make_real_stream()
    packet, addr = alice.transport.written[-1]
    assert petlib.pack.decode(packet) == 'ABCDefgHIJKlmnOPRstUWxyz'
    assert addr == (alice.provider.host, alice.provider.port)

def test_client_construct_full_path():
    client = env.clients[0]
    receiver = env.pubs_clients[1]
    path = client.construct_full_path(receiver)
    assert len(path) == 6
    assert path[0] == client.provider
    assert path[1].group == 0
    assert path[2].group == 1
    assert path[3].group == 2
    assert path[4] == receiver.provider
    assert path[5] == receiver

def test_client_get_network_info():
    alice = env.clients[0]
    alice.DATABASE_NAME = 'test.db'
    alice.get_network_info()

    assert alice.pubs_mixes == group_layered_topology(env.pubs_mixes)
    assert alice.pubs_providers == env.pubs_providers
    assert alice.befriended_clients == env.pubs_clients

def test_client_retrieve_messages():
    alice = env.clients[1]
    alice.reactor = task.Clock()
    alice.transport.written = []
    alice.retrieve_messages()

    message, addr = alice.transport.written.pop()
    assert petlib.pack.decode(message) == ['PULL', alice.name]
    assert addr == (alice.provider.host, alice.provider.port)

def test_client_datagramReceived():
    alice = env.clients[1]
    test_packet = '123456789'
    alice.datagramReceived(test_packet, ('1.2.3.4', 1111))
    insert_time, stored_packet = alice.process_queue.queue.pop()
    assert test_packet == stored_packet

def test_client_handle_packet():
    alice = env.clients[1]
    provider = [p for p in env.providers if p.name == alice.provider.name].pop()

    alice.send_loop_message()
    packet, addr = alice.transport.written[-1]
    provider.handle_packet(packet)
    alice.transport.written = []

#===============================================================================

def test_mix_get_network_info():
    mix = env.mixes[0]
    mix.DATABASE_NAME = 'test.db'
    mix.get_network_info()

    other_mixes = [m for m in env.pubs_mixes if mix.name != m.name]
    assert mix.pubs_mixes == group_layered_topology(other_mixes)
    assert mix.pubs_providers == env.pubs_providers

    provider = env.providers[0]
    provider.DATABASE_NAME = 'test.db'
    provider.get_network_info()

    assert provider.pubs_mixes == group_layered_topology(env.pubs_mixes)
    other_providers = [p for p in env.pubs_providers if provider.name != p.name]
    assert provider.pubs_providers == other_providers

def test_mix_register_mixes():
    [mix.register_mixes(env.pubs_mixes) for mix in env.mixes]
    mix = env.mixes[0]
    assert mix.pubs_mixes == group_layered_topology(env.pubs_mixes)

def test_mix_register_providers():
    [mix.register_providers(env.pubs_providers) for mix in env.mixes]
    mix = env.mixes[0]
    assert mix.pubs_providers == env.pubs_providers

def test_mix_make_loop_stream():
    mix = env.mixes[0]
    mix.transport.written = []
    mix.reactor = task.Clock()

    mix.make_loop_stream()
    assert len(mix.transport.written) == 1

    mix.reactor.advance(100)
    assert len(mix.transport.written) == 2

    calls = mix.reactor.getDelayedCalls()
    for c in calls:
        assert c.func == mix.make_loop_stream

def test_mix_send_loop_message():
    mix = env.mixes[0]
    mix.transport.written = []
    path = [m for m in env.pubs_mixes if m.name != mix.name]
    packet = mix.crypto_node.create_loop_message(path)

    process_route = [m for m in env.mixes if m.name != mix.name]
    header, body = packet
    for e in process_route:
        flag, new_packet = e.crypto_node.process_packet((header, body))
        if flag == 'ROUT':
            delay, header, body, next_addr, next_name = new_packet
    flag, packet = mix.crypto_node.process_packet((header, body))
    assert flag == 'LOOP'
    assert packet[:2] == 'HT'

def test_mix_schedule_next_call():
    mix = env.mixes[1]
    mix.reactor = task.Clock()
    mix.transport.written = []
    def tmp_method():
        mix.send('Test', ('1.1.1.1', 1111))

    mix.schedule_next_call(3, tmp_method)
    mix.reactor.advance(100)
    packet, addr = mix.transport.written[-1]

    assert petlib.pack.decode(packet) == 'Test'
    assert addr == ('1.1.1.1', 1111)

def test_mix_send_or_delay():
    mix = env.mixes[0]
    mix.reactor = task.Clock()
    mix.transport.written = []
    mix.send_or_delay(0, 'Hello world', ('1.1.1.2', 1112))
    mix.reactor.advance(1)
    packet, addr = mix.transport.written.pop()
    assert petlib.pack.decode(packet) == 'Hello world'
    assert addr == ('1.1.1.2', 1112)

    mix.send_or_delay(10, 'Hello world', ('1.1.1.2', 1112))
    mix.reactor.advance(11)
    packet, addr = mix.transport.written.pop()
    assert petlib.pack.decode(packet) == 'Hello world'
    assert addr == ('1.1.1.2', 1112)

def test_mix_send():
    mix = env.mixes[0]
    mix.transport.written = []
    mix.send('Hello world', ('1.1.1.2', 1112))

def test_mix_construct_full_path():
    mix = env.mixes[0]
    path = mix.generate_random_path()
    assert path[0] == env.pubs_mixes[1]
    assert path[1] == env.pubs_mixes[2]
    assert path[2] in env.pubs_providers

    mix = env.mixes[1]
    path = mix.construct_full_path()
    assert path[0] == env.pubs_mixes[2]
    assert path[1] in env.pubs_providers
    assert path[2] == env.pubs_mixes[0]

    mix = env.mixes[2]
    path = mix.construct_full_path()
    assert path[0] in env.pubs_providers
    assert path[1] == env.pubs_mixes[0]
    assert path[2] == env.pubs_mixes[1]

def test_mix_datagramReceived():
    mix = env.mixes[0]
    test_packet = '123456789'
    mix.datagramReceived(test_packet, ('1.2.3.4', 1111))
    insert_time, stored_packet = mix.process_queue.queue.pop()
    assert test_packet == stored_packet

def test_mix_get_and_addCallback():
    mix = env.mixes[0]
    mix.process_queue.put(('TestPacket', ('1.2.3.4', 1111)))
    mix.get_and_addCallback(mix.handle_packet)
    assert any(isinstance(x, defer.Deferred) for x in mix.process_queue.consumers)

#===============================================================================

def test_provider_subscribe_client():
    provider = env.providers[0]
    client = env.pubs_clients[0]
    provider.subscribe_client([client.name, client.host, client.port])
    assert provider.clients == {client.name : (client.host, client.port)}

def test_provider_is_assigned_client():
    provider = env.providers[0]

    subs_client = env.clients[0]
    provider.subscribe_client([subs_client.name, subs_client.host, subs_client.port])
    assert provider.is_assigned_client(subs_client.name)

    non_subs_client = env.clients[1]
    assert not provider.is_assigned_client(non_subs_client.name)

def test_provider_put_into_storage():
    provider = env.providers[0]
    subs_client = env.clients[0]

    provider.put_into_storage(subs_client.name, 'Hello world')
    assert 'Hello world' in provider.storage_inbox[subs_client.name]

def test_provider_pull_messages():
    provider = env.providers[0]
    subs_client = env.clients[0]

    for i in range(100):
        provider.put_into_storage(subs_client.name, 'Hello world x%d' % i)
    stored_messages = provider.storage_inbox[subs_client.name]
    pulled_messages = provider.pull_messages(subs_client.name)
    assert pulled_messages == stored_messages[:50]

    provider.storage_inbox = {}
    for i in range(10):
        provider.put_into_storage(subs_client.name, 'Hello world x%d' % i)
    stored_messages = provider.storage_inbox[subs_client.name]
    pulled_messages = provider.pull_messages(subs_client.name)

    assert len(pulled_messages) == provider.config_params.MAX_RETRIEVE
    assert set(stored_messages) < set(pulled_messages)

def test_client_provider_retrieve():
    import itertools

    provider = env.providers[0]
    provider.transport.written = []
    subs_client = env.clients[0]

    for i in range(100):
        provider.put_into_storage(subs_client.name, 'Hello world x%d' % i)

    subs_client.retrieve_messages()
    pkt, addr = subs_client.transport.written[-1]
    assert pkt == petlib.pack.encode(['PULL', subs_client.name])
    assert addr == (provider.host, provider.port)

    provider.read_packet(pkt)
    test_msg = [petlib.pack.encode('Hello world x%d' % i) for i in range(50)]
    test_packets = zip(test_msg, itertools.repeat((subs_client.host, subs_client.port)))
    assert provider.transport.written == test_packets
    packet, addr = provider.transport.written[0]

    provider.storage_inbox[subs_client.name] = []
    provider.transport.written = []
    provider.read_packet(petlib.pack.encode(['PULL',subs_client.name]))
    packets = [i[0] for i in provider.transport.written]
    assert all(petlib.pack.decode(i)[0] == 'DUMMY' for i in packets)
    for p in packets:
        assert subs_client.read_packet(p) == None


def test_provider_generate_dummy_messages():
    provider = env.providers[0]
    dummies = provider.generate_dummy_messages(20)
    assert len(dummies) == 20

def test_provider_construct_path():
    provider = env.providers[0]
    path = provider.generate_random_path()
    assert path[0] == env.pubs_mixes[0]
    assert path[1] == env.pubs_mixes[1]
    assert path[2] == env.pubs_mixes[2]

def test_provider_datagramReceived():
    provider = env.providers[0]
    test_packet = '123456789'
    provider.datagramReceived(test_packet, ('1.2.3.4', 1111))
    insert_time, stored_packet = provider.process_queue.queue.pop()
    assert test_packet == stored_packet

def test_provider_get_clients_messages():
    provider = env.providers[0]
    subs_client = env.clients[0]

    provider.storage_inbox = {}

    assert provider.get_clients_messages(subs_client.name) == []

    test_set = []
    for i in range(120):
        test_set.append('Hello world x%d' % i)

    [provider.put_into_storage(subs_client.name, x) for x in test_set]
    msgs = provider.get_clients_messages(subs_client.name)
    assert len(msgs) == provider.config_params.MAX_RETRIEVE
    assert len(provider.storage_inbox[subs_client.name]) == 120 - provider.config_params.MAX_RETRIEVE
    assert msgs == test_set[:provider.config_params.MAX_RETRIEVE]
    assert provider.storage_inbox[subs_client.name] == test_set[provider.config_params.MAX_RETRIEVE:]

    provider.storage_inbox[subs_client.name] = []
    [provider.put_into_storage(subs_client.name, x) for x in test_set[:10]]
    msgs = provider.get_clients_messages(subs_client.name)
    assert len(msgs) == 10
    assert len(provider.storage_inbox[subs_client.name]) == 0
    assert msgs == test_set[:10]
    assert provider.storage_inbox[subs_client.name] == []

def test_client_provider_sending():
    sender, recipient = random.sample(env.clients, 2)
    sender.transport.written = []
    provider_s = [p for p in env.providers if p.name == sender.provider.name].pop()
    provider_r = [p for p in env.providers if p.name == recipient.provider.name].pop()

    sender.send_message('Hello world', recipient)
    packet, addr = sender.transport.written[-1]

    provider_s.datagramReceived(packet, (sender.host, sender.port))
    time, pop_packet = provider_s.process_queue.queue.pop()
    provider_s.read_packet(pop_packet)

def test_provider_mix_sending():
    provider = random.choice(env.providers)
    provider.register_mixes(env.pubs_mixes)
    mixes = env.mixes

    provider.send_loop_message()
    packet, addr = provider.transport.written[-1]
    assert addr == (mixes[0].host, mixes[0].port)
    mixes[0].datagramReceived(packet, addr)
    time, pop_packet = mixes[0].process_queue.queue.pop()
    mixes[0].read_packet(pop_packet)

def test_provider_ping_received():
    alice = env.clients[1]
    provider = [p for p in env.providers if p.name == alice.provider.name].pop()

    alice.subscribe_to_provider()
    pkt, addr = alice.transport.written[-1]

    assert petlib.pack.decode(pkt) == ['SUBSCRIBE'] + [alice.name, alice.host, alice.port]
    assert addr == (provider.host, provider.port)

    provider.read_packet(pkt)

def test_mix_mix_sending():
    mix = env.mixes[0]
    mix.register_mixes(env.pubs_mixes)
    mix.register_providers(env.pubs_providers)
    mix2, mix3 = env.mixes[1], env.mixes[2]

    mix.send_loop_message()
    packet, addr = mix.transport.written[-1]
    assert addr == (mix2.host, mix2.port)
    mix2.datagramReceived(packet, addr)
    time, pop_packet = mix2.process_queue.queue.pop()
    mix2.read_packet(pop_packet)

def test_generate_random_delay():
    sec_params = SphinxParams(header_len=1024)
    client = env.clients[0]
    packer = SphinxPacker((sec_params, client.config_params))
    delay = packer.generate_random_delay(0.0)
    assert delay == 0.0

def test_take_mix_sequence():
    assert take_mix_sequence(0,5) == [1,2,3,4]
    assert take_mix_sequence(1,5) == [2,3,4,0]
    assert take_mix_sequence(2,5) == [3,4,0,1]
    assert take_mix_sequence(3,5) == [4,0,1,2]
    assert take_mix_sequence(4,5) == [0,1,2,3]
