import os
import random
import itertools
import petlib.pack
from loopix_mixnode import LoopixMixNode
from provider_core import ProviderCore
from core import generate_random_string
from json_reader import JSONReader

class LoopixProvider(LoopixMixNode):
    jsonReader = JSONReader(os.path.join(os.path.dirname(__file__), 'config.json'))
    config_params = jsonReader.get_provider_config_params()
    storage_inbox = {}
    clients = {}

    def __init__(self, sec_params, name, port, host, privk=None, pubk=None):
        LoopixMixNode.__init__(self, sec_params, name, port, host, privk, pubk)

        self.privk = privk or sec_params.group.G.order().random()
        self.pubk = pubk or (self.privk * sec_params.group.G.generator())
        self.crypto_node = ProviderCore((sec_params, self.config_params), self.name,
                                        self.port, self.host, self.privk, self.pubk)

    def subscribe_client(self, client_data):
        subscribe_key, subscribe_host, subscribe_port = client_data
        self.clients[subscribe_key] = (subscribe_host, subscribe_port)
        print "[%s] > Subscribed client" % self.name

    def read_packet(self, packet):
        try:
            decoded_packet = petlib.pack.decode(packet)
            if decoded_packet[0] == 'SUBSCRIBE':
                self.subscribe_client(decoded_packet[1:])
            elif decoded_packet[0] == 'PULL':
                pulled_messages = self.pull_messages(client_id=decoded_packet[1])
                map(lambda (packet, addr): self.send(packet, addr),
                    zip(pulled_messages, itertools.repeat(self.clients[decoded_packet[1]])))
            else:
                flag, decrypted_packet = self.crypto_node.process_packet(decoded_packet)
                if flag == "ROUT":
                    delay, new_header, new_body, next_addr, next_name = decrypted_packet
                    if self.is_assigned_client(next_name):
                        self.put_into_storage(next_name, (new_header, new_body))
                    else:
                        self.reactor.callFromThread(self.send_or_delay,
                                                    delay,
                                                    (new_header, new_body),
                                                    next_addr)
                elif flag == "LOOP":
                    print "[%s] > Received loop message" % self.name
                elif flag == "DROP":
                    print "[%s] > Received drop message" % self.name
        except Exception, exp:
            print "ERROR: ", str(exp)

    def is_assigned_client(self, client_id):
        return any(c == client_id for c in self.clients)

    def put_into_storage(self, client_id, packet):
        try:
            self.storage_inbox[client_id].append(packet)
        except KeyError, _:
            self.storage_inbox[client_id] = [packet]

    def pull_messages(self, client_id):
        dummy_messages = []
        popped_messages = self.get_clients_messages(client_id)
        if len(popped_messages) < self.config_params.MAX_RETRIEVE:
            dummy_messages = self.generate_dummy_messages(
                self.config_params.MAX_RETRIEVE - len(popped_messages))
        return popped_messages + dummy_messages

    def get_clients_messages(self, client_id):
        if client_id in self.storage_inbox.keys():
            messages = self.storage_inbox[client_id]
            popped, rest = messages[:self.config_params.MAX_RETRIEVE], messages[self.config_params.MAX_RETRIEVE:]
            self.storage_inbox[client_id] = rest
            return popped
        return []

    def generate_dummy_messages(self, num):
        dummy_messages = [('DUMMY', generate_random_string(self.config_params.NOISE_LENGTH),
                    generate_random_string(self.config_params.NOISE_LENGTH)) for _ in range(num)]
        return dummy_messages

    def generate_random_path(self):
        return self.construct_full_path()

    def construct_full_path(self):
        sequence = []
        num_all_layers = len(self.pubs_mixes)
        for i in range(num_all_layers):
            mix = random.choice(self.pubs_mixes[i])
            sequence.append(mix)
        return sequence
