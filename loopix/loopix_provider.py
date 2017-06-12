from loopix_mixnode import LoopixMixNode
from provider_core import ProviderCore
from processQueue import ProcessQueue
from core import generate_random_string
import random
import petlib.pack
from json_reader import JSONReader

class LoopixProvider(LoopixMixNode):
    jsonReader = JSONReader('config.json')
    config = jsonReader.get_provider_config_params()
    storage_inbox = {}
    clients = {}

    def __init__(self, sec_params, name, port, host, privk=None, pubk=None):
        LoopixMixNode.__init__(self, sec_params, name, port, host, privk, pubk)

        self.privk = privk or sec_params.group.G.order().random()
        self.pubk = pubk or (self.privk * sec_params.group.G.generator())
        self.crypto_node = ProviderCore((sec_params, self.config), self.name, self.port, self.host, self.privk, self.pubk)

    def subscribe_client(self, client):
        self.clients[client.name] = client

    def read_packet(self, packet):
        try:
            if packet.startswith('PING'):
                self.subscribe_client(packet.split('PING', 1)[1])
            else:
                decoded_packet = petlib.pack.decode(packet)
                flag, decrypted_packet = self.crypto_node.process_packet(decoded_packet)
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
        except Exception, e:
            print "ERROR: ", str(e)

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
        if len(popped_messages) < self.config.MAX_RETRIEVE:
            dummy_messages = self.generate_dummy_messages(self.config.MAX_RETRIEVE - len(popped_messages))
        return popped_messages + dummy_messages

    def get_clients_messages(self, client_id):
        if client_id in self.storage_inbox.keys():
            messages = self.storage_inbox[client_id]
            popped, rest = messages[:self.config.MAX_RETRIEVE], messages[self.config.MAX_RETRIEVE:]
            self.storage_inbox[client_id] = rest
            return popped
        return []

    def generate_dummy_messages(self, num):
        dummy_messages = [generate_random_string(self.config.NOISE_LENGTH) for _ in range(num)]
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
