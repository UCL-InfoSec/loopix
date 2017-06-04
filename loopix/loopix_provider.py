from loopix_mixnode import LoopixMixNode
from provider_core import ProviderCore
from sphinxmix.SphinxParams import SphinxParams
from processQueue import ProcessQueue
from core import get_group_characteristics, generate_random_string
import random
import petlib.pack

class LoopixProvider(LoopixMixNode):
    MAX_RETRIEVE = 50

    def __init__(self, name, port, host, privk=None, pubk=None):
        LoopixMixNode.__init__(self, name, port, host, privk, pubk)

        params = SphinxParams(header_len=1024)
        order, generator = get_group_characteristics(params)
        self.privk = privk or order.random()
        self.pubk = pubk or (self.privk * generator)
        self.core = ProviderCore(params, self.name, self.port, self.host, self.privk, self.pubk)

        self.storage_inbox = {}
        self.clients = {}

    def subscribe_client(self, client):
        self.clients[client.name] = client

    def read_packet(self, packet):
        decoded_packet = petlib.pack.decode(packet)
        flag, decrypted_packet = self.core.process_packet(decoded_packet)
        if flag == "ROUT":
            delay, new_header, new_body, next_addr, next_name = decrypted_packet
            if self.is_assigned_client(next_name):
                self.put_into_storage(next_name, petlib.pack.encode(new_header, new_body))
            else:
                self.reactor.callFromThread(self.send_or_delay, delay, (new_header, new_body), next_addr)
        elif flag == "LOOP":
            print "[%s] > Received loop message" % self.name
        elif flag == "DROP":
            print "[%s] > Received drop message" % self.name

    def is_assigned_client(self, client_id):
        return any(c == client_id for c in self.clients)

    def put_into_storage(self, client_id, packet):
        try:
            self.storage_inbox[client_id].append(packet)
        except Exception, e:
            self.storage_inbox[client_id] = [packet]

    def pull_messages(self, client_id):
        dummy_messages = []
        client_addr = (self.clients[client_id].host, self.clients[client_id].port)
        popped_messages = self.get_clients_messages(client_id)
        if len(popped_messages) < self.MAX_RETRIEVE:
            dummy_messages = self.generate_dummy_messages(self.MAX_RETRIEVE - len(popped_messages))
        return popped_messages + dummy_messages

    def get_clients_messages(self, client_id):
        if client_id in self.storage_inbox.keys():
            messages = self.storage_inbox[client_id]
            popped, rest = messages[:self.MAX_RETRIEVE], messages[self.MAX_RETRIEVE:]
            self.storage_inbox[client_id] = rest
            return popped
        return []

    def generate_dummy_messages(self, num):
        dummy_messages = [generate_random_string(100) for _ in range(num)]
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
