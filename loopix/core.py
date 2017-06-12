from sphinxmix.SphinxNode import sphinx_process
from sphinxmix.SphinxClient import PFdecode, Nenc, create_forward_message, receive_forward
import numpy
from sphinxmix.SphinxParams import SphinxParams
from operator import attrgetter
import itertools
from json_reader import JSONReader
from support_formats import Params
from petlib.ec import EcGroup
from petlib.ec import EcPt
from petlib.bn import Bn
import math

jsonReader = JSONReader('config.json')
config = jsonReader.get_client_config_params()

def setup():
    ''' Setup the parameters of the mix crypto-system '''
    G = EcGroup()
    o = G.order()
    g = G.generator()
    o_bytes = int(math.ceil(math.log(float(int(o))) / math.log(256)))
    return G, o, g, o_bytes

def sample_from_exponential(lambdaParam):
    return numpy.random.exponential(lambdaParam, size=None)

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
    grouped_mixes = [list(group) for key,group in itertools.groupby(sorted_mixes,lambda x: x.group)]
    return grouped_mixes


class SphinxPacker(object):
    def __init__(self, params):
        self.sec_params, self.config = params

    def make_sphinx_packet(self, receiver, path, message, drop_flag=False, type_flag=None):
        keys_nodes = self.take_nodes_keys(path)
        routing_info = self.take_nodes_routing(path, drop_flag, type_flag)
        dest = (receiver.host, receiver.port, receiver.name)
        header, body = create_forward_message(self.sec_params, routing_info, keys_nodes, dest, message)
        return header, body

    def take_nodes_keys(self, nodes):
        return [n.pubk for n in nodes]

    def take_nodes_routing(self, nodes, drop_flag, type_flag):
        nodes_routing = []
        for i, n in enumerate(nodes):
            delay = self.generate_random_delay(config.EXP_PARAMS_DELAY)
            drop = (i == len(nodes) - 1) and drop_flag
            nodes_routing.append(Nenc([(n.host, n.port), drop, type_flag, delay, n.name]))
        return nodes_routing

    def generate_random_delay(self, param):
        if float(param) == 0.0:
            return 0.0
        else:
            return sample_from_exponential(config.EXP_PARAMS_DELAY)

    def decrypt_sphinx_packet(self, packet, key):
        header, body = packet
        tag, info, (new_header, new_body) = sphinx_process(self.sec_params, key, header, body)
        routing = PFdecode(self.sec_params, info)
        return tag, routing, new_header, new_body

    def handle_received_forward(self, packet):
        return receive_forward(self.sec_params, packet)
