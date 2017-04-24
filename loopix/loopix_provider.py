from loopix_mixnode import LoopixMixNode
from provider_core import ProviderCore
from sphinxmix.SphinxParams import SphinxParams
from processQueue import ProcessQueue

class LoopixProvider(LoopixMixNode):
    def __init__(self, name, port, host, privk=None, pubk=None):
        LoopixMixNode.__init__(self, name, port, host, privk, pubk)

        params = SphinxParams(header_len=1024)
        gr_order = params.group.G.order()
        gr_generator = params.group.G.generator()

        self.privk = privk or gr_order.random()
        self.pubk = pubk or (self.privk * gr_generator)
        self.core = ProviderCore(params, self.name, self.port, self.host, self.privk, self.pubk)

        self.storage_inbox = {}

    def assign_clients(self, clients):
        self.clients = clients

    def datagramReceived(self, data, (host, port)):
        self.process_queue.put((data, (host, port)))

    def packet_received(self, packet):
        flag, packet = self.core.process_packet(packet)
        if flag == "ROUT":
            new_header, new_body, next_addr, next_name = packet
            if self.is_assigned_client(next_name):
                self.put_into_storage(next_name, (new_header, new_body))
        return flag, packet

    def is_assigned_client(self, name):
        for c in self.clients:
            if c.name == name:
                return True
        return False

    def put_into_storage(self, next_name, packet):
        try:
            self.storage_inbox[next_name].append(packet)
        except Exception, e:
            self.storage_inbox[next_name] = [packet]

    def pull_messages(self, client_name, client_addr):
        popped_messages = self.get_clients_messages(client_name)
        if len(popped_messages) < MAX_RETRIEVE:
            dummy_messages = self.generate_dummy_messages(MAX_RETRIEVE - len(popped_messages))
        for m in popped_messages + dummy_messages:
            self.send(m, client_addr)

    def get_clients_messages(client_name):
        if client_name in self.inboxes.keys():
            messages = self.inboxes[client_name]
            popped, rest = messages[:MAX_RETRIEVE], messages[MAX_RETRIEVE:]
            storage[name] = rest
            return popped
        return []

    def generate_dummy_messages(self, num):
        return []
