import random
from sphinxmix.SphinxClient import Relay_flag, Dest_flag, Surb_flag
from core import SphinxPacker, generate_random_string
from json_reader import JSONReader
from twisted.python import log
from twisted.python.logfile import DailyLogFile
# log.startLogging(DailyLogFile.fromFullPath("foo_log.log"))

class ClientCore(object):

    def __init__(self, params, name, port, host, privk=None, pubk = None):
        self.params, self.config = params
        self.packer = SphinxPacker(self.params, self.config)
        self.name = name
        self.port = port
        self.host = host
        self.privk = privk
        self.pubk = pubk

    def create_loop_message(self, path):
        loop_message = 'HT' + generate_random_string(self.config.NOISE_LENGTH)
        header, body = self.packer.make_sphinx_packet(self, path, loop_message)
        log.msg("[%s] > Packed loop message." % self.name)
        return (header, body)

    def create_drop_message(self, random_reciever, path):
        drop_message = generate_random_string(self.config.NOISE_LENGTH)
        header, body = self.packer.make_sphinx_packet(self, path, drop_message,drop_flag=True)
        log.msg("[%s] > Packed drop message." % self.name)
        return (header, body)

    def pack_real_message(self, message, receiver, path):
        header, body = self.packer.make_sphinx_packet(receiver, path, message)
        log.msg("[%s] > Packed real message." % self.name)
        return header, body

    def process_packet(self, packet):
        log.msg("[%s] > Processing packet." % self.name)
        tag, routing, new_header, new_body = self.packer.decrypt_sphinx_packet(packet, self.privk)
        routing_flag, meta_info = routing[0], routing[1:]
        if routing_flag == Dest_flag:
            dest, message = self.packer.handle_received_forward(self.params, new_body)
            if dest == [self.host, self.port, self.name]:
                return "NEW", message
            else:
                return "ERROR", []
