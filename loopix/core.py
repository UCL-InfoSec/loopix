from sphinxmix.SphinxNode import sphinx_process
from sphinxmix.SphinxClient import PFdecode, Nenc, create_forward_message
import numpy
from sphinxmix.SphinxParams import SphinxParams
from operator import attrgetter
import itertools

EXP_PARAMS_DELAY = 3
params = SphinxParams(header_len=1024) # this should be removed and passed as an argument

def setup():
    ''' Setup the parameters of the mix crypto-system '''
    G = EcGroup()
    o = G.order()
    g = G.generator()
    o_bytes = int(math.ceil(math.log(float(int(o))) / math.log(256)))
    return G, o, g, o_bytes

def get_group_characteristics(params):
    order = params.group.G.order()
    generator = params.group.G.generator()
    return order, generator

def sample_from_exponential(lambdaParam):
    return numpy.random.exponential(lambdaParam, size=None)

def generate_random_string(length):
    return numpy.random.bytes(length)

def make_sphinx_packet(receiver, path, message, drop_flag=False, type_flag=None):
    keys_nodes = take_nodes_keys(path)
    routing_info = take_nodes_routing(path, drop_flag, type_flag)
    dest = (receiver.host, receiver.port, receiver.name)
    header, body = create_forward_message(params, routing_info, keys_nodes, dest, message)
    return header, body

def take_nodes_keys(nodes):
    return [n.pubk for n in nodes]

def take_nodes_routing(nodes, drop_flag, type_flag):
    nodes_routing = []
    for i, n in enumerate(nodes):
        delay = generate_random_delay(EXP_PARAMS_DELAY)
        drop = (i == len(nodes) - 1) and drop_flag
        nodes_routing.append(Nenc([(n.host, n.port), drop, type_flag, delay, n.name]))
    return nodes_routing

def generate_random_delay(param):
    if float(param) == 0.0:
        return 0.0
    else:
        return sample_from_exponential(EXP_PARAMS_DELAY)

def decrypt_sphinx_packet(packet, params, key):
    header, body = packet
    tag, info, (new_header, new_body) = sphinx_process(params, key, header, body)
    routing = PFdecode(params, info)
    return tag, routing, new_header, new_body

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
