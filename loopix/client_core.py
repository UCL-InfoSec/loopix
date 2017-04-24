import random
import supportFunctions as sf
from sphinxmix.SphinxClient import pki_entry, Nenc, create_forward_message, Relay_flag, Dest_flag, Surb_flag, receive_forward
from core import decrypt_sphinx_packet, make_sphinx_packet

class ClientCore(object):
    NOISE_LENGTH = 500
    EXP_PARAMS_DELAY = (3, None)

    def __init__(self, params, name, port, host, privk=None, pubk = None):
        self.params = params
        self.name = name
        self.port = port
        self.host = host
        self.privk = privk
        self.pubk = pubk

    def create_loop_message(self, path):
        loop_message = 'HT' + sf.generateRandomNoise(self.NOISE_LENGTH)
        header, body = make_sphinx_packet(self, path, loop_message)
        return (header, body)

    def create_drop_message(self, random_reciever, path):
        drop_message = sf.generateRandomNoise(self.NOISE_LENGTH)
        header, body = make_sphinx_packet(self, path, drop_message,drop_flag=True)
        return (header, body)

    def create_real_message(self, message, receiver, path):
        header, body = make_sphinx_packet(receiver, path, message)
        return header, body

    def process_packet(self, packet):
        tag, routing, new_header, new_body = decrypt_sphinx_packet(packet, self.params, self.privk)
        routing_flag, meta_info = routing[0], routing[1:]
        if routing_flag == Dest_flag:
            dest, message = receive_forward(self.params, new_body)
            if dest == [self.host, self.port, self.name]:
                return "NEW", message
            else:
                return "ERROR", []
