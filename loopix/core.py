from operator import attrgetter
import itertools
import math
import os
import numpy
from sphinxmix.SphinxNode import sphinx_process
from sphinxmix.SphinxClient import PFdecode, Nenc, create_forward_message, receive_forward
from json_reader import JSONReader
from petlib.ec import EcGroup

jsonReader = JSONReader(os.path.join(os.path.dirname(__file__), 'config.json'))
config = jsonReader.get_client_config_params()

def setup():
    ''' Setup the parameters of the mix crypto-system '''
    group = EcGroup()
    order = group.order()
    generator = group.generator()
    o_bytes = int(math.ceil(math.log(float(int(order))) / math.log(256)))
    return group, order, generator, o_bytes

def sample_from_exponential(lambda_param):
    return numpy.random.exponential(lambda_param, size=None)

def generate_random_string(length):
    return numpy.random.bytes(length)

def take_mix_sequence(current_layer, num_all_layers):
    sequence = []
    j = current_layer + 1
    while j != current_layer:
        sequence.append(j % num_all_layers)
        j = (j + 1) % num_all_layers
    return sequence

def group_layered_topology(mixes):
    sorted_mixes = sorted(mixes, key=attrgetter('group'))
    grouped_mixes = [list(group) for _, group in itertools.groupby(sorted_mixes,
                                                                   lambda x: x.group)]
    return grouped_mixes


class SphinxPacker(object):
    def __init__(self, params):
        self.sec_params, self.config = params

    def make_sphinx_packet(self, receiver, path, message, drop_flag=False, type_flag=None):
        keys_nodes = self.take_nodes_keys(path)
        routing_info = self.take_nodes_routing(path, drop_flag, type_flag)
        dest = (receiver.host, receiver.port, receiver.name)
        header, body = create_forward_message(self.sec_params,
                                              routing_info, keys_nodes, dest, message)
        return header, body

    def take_nodes_keys(self, nodes):
        return [n.pubk for n in nodes]

    def take_nodes_routing(self, nodes, drop_flag, type_flag):
        nodes_routing = []
        for i, node in enumerate(nodes):
            delay = self.generate_random_delay(self.config.EXP_PARAMS_DELAY)
            drop = (i == len(nodes) - 1) and drop_flag
            nodes_routing.append(Nenc([(node.host, node.port), drop, type_flag, delay, node.name]))
        return nodes_routing

    def generate_random_delay(self, param):
        if float(param) == 0.0:
            return 0.0
        else:
            return sample_from_exponential(self.config.EXP_PARAMS_DELAY)

    def decrypt_sphinx_packet(self, packet, key):
        header, body = packet
        tag, info, (new_header, new_body) = sphinx_process(self.sec_params, key, header, body)
        routing = PFdecode(self.sec_params, info)
        return tag, routing, new_header, new_body

    def handle_received_forward(self, packet):
        return receive_forward(self.sec_params, packet)
