from mix_core import MixCore
from sphinxmix.SphinxNode import sphinx_process
from sphinxmix.SphinxClient import receive_forward, PFdecode, Relay_flag, Dest_flag
from core import decrypt_sphinx_packet, make_sphinx_packet

class ProviderCore(MixCore):
    def __init__(self, params, name, port, host, privk, pubk):
        MixCore.__init__(self, params, name, port, host, privk, pubk)

        self.params = params
        self.name = name
        self.port = port
        self.host = host
        self.privk = privk
        self.pubk = pubk

    def process_packet(self, packet):
        tag, routing, new_header, new_body = decrypt_sphinx_packet(packet, self.params, self.privk)
        routing_flag, meta_info = routing[0], routing[1:]
        if routing_flag == Relay_flag:
            next_addr, drop_flag, type_flag, delay, next_name = meta_info[0]
            if drop_flag:
                return "DROP", []
            else:
                return "ROUT", [delay, new_header, new_body, next_addr, next_name]
        elif routing_flag == Dest_flag:
            print "Dest, Hello"
            dest, message = receive_forward(self.params, body)
            if dest == [self.host, self.port, self.name]:
                if message.startswith('HT'):
                    return "LOOP", [message]
            else:
                return "ERROR", []
