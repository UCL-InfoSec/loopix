from sphinxmix.SphinxParams import SphinxParams
from sphinxmix.SphinxNode import sphinx_process
from sphinxmix.SphinxClient import receive_forward, PFdecode, Relay_flag, Dest_flag
from core import decrypt_sphinx_packet, make_sphinx_packet, generate_random_string

class MixCore(object):

    def __init__(self, params, name, port, host, privk, pubk):
        self.params, self.config = params
        self.name = name
        self.port = port
        self.host = host

        self.privk = privk
        self.pubk = pubk

    def create_loop_message(self, path):
        path = path + [self]
        loop_message = 'HT' + generate_random_string(self.config.NOISE_LENGTH)
        header, body = make_sphinx_packet(self.params, receiver=self, path=path, message=loop_message)
        return header, body

    def process_packet(self, packet):
        tag, routing, new_header, new_body = decrypt_sphinx_packet(packet, self.params, self.privk)
        routing_flag, meta_info = routing[0], routing[1:]
        if routing_flag == Relay_flag:
            next_addr, dropFlag, typeFlag, delay, next_name = meta_info[0]
            return "ROUT", [delay, new_header, new_body, next_addr, next_name]
        elif routing_flag == Dest_flag:
            dest, message = receive_forward(self.params, new_body)
            if dest == [self.host, self.port, self.name]:
                if message.startswith('HT'):
                    return "LOOP", message
            else:
                print "[%s] > Destination does not match" % self.name
                return "ERROR", []
