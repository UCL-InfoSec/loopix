import json
import time
import petlib
import random
from sphinxmix.SphinxClient import Nenc, create_forward_message, PFdecode, \
    Relay_flag, Dest_flag, receive_forward
from sphinxmix.SphinxParams import SphinxParams
from sphinxmix.SphinxNode import sphinx_process
from format3 import Mix, Provider, User

#from loopix import supportFunctions as sf
import supportFunctions as sf

with open('config.json') as infile:
    _PARAMS = json.load(infile)

MAX_RETRIEVE = 500



def makeSphinxPacket(params, exp_delay, receiver, path, message,
                     dropFlag=False):
    path.append(receiver)
    keys_nodes = [n.pubk for n in path]
    nodes_routing = []
    path_length = len(path)
    for i, node in enumerate(path):
        if exp_delay == 0.0:
            delay = 0.0
        else:
            delay = sf.sampleFromExponential((exp_delay, None))
        drop = dropFlag and i == path_length - 1
        nodes_routing.append(
                Nenc([(node.host, node.port), drop, delay, node.name]))

    # Destination of the message
    dest = (receiver.host, receiver.port, receiver.name)
    header, body = create_forward_message(
        params, nodes_routing, keys_nodes, dest, message)
    return (header, body)



class LoopixClient(object):
    PATH_LENGTH = int(_PARAMS["parametersClients"]["PATH_LENGTH"])
    EXP_PARAMS_PAYLOAD = (
        float(_PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"]), None)

    EXP_PARAMS_LOOPS = (
        float(_PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"]), None)
    EXP_PARAMS_COVER = (
        float(_PARAMS["parametersClients"]["EXP_PARAMS_COVER"]), None)
    EXP_PARAMS_DELAY = float(_PARAMS["parametersClients"]["EXP_PARAMS_DELAY"])
    NOISE_LENGTH = float(_PARAMS["parametersClients"]["NOISE_LENGTH"])

    def __init__(self, host, port, name, provider, privk, pubk):
        self.host = host
        self.port = port
        self.name = name
        self.provider = provider
        self.privk = privk
        self.pubk = pubk
        self.params = SphinxParams(header_len=1024)
        self.buffer = []

    def selectRandomProvider(self):
        return random.choice(self.providers)

    def create_drop_message(self, mixers):
        randomProvider = self.selectRandomProvider()
        randomMessage = sf.generateRandomNoise(self.NOISE_LENGTH)
        path = [self.provider] + mixers
        (header, body) = makeSphinxPacket(
            self.params, self.EXP_PARAMS_DELAY,
            randomProvider, path, randomMessage, dropFlag=True)
        return petlib.pack.encode((header, body))

    def create_loop_message(self, mixers, timestamp):
        path = [self.provider] + mixers + [self.provider]
        heartMsg = sf.generateRandomNoise(self.NOISE_LENGTH)
        (header, body) = makeSphinxPacket(
            self.params, self.EXP_PARAMS_DELAY,
            self, path, 'HT' + heartMsg + str(timestamp), dropFlag=False)
        return petlib.pack.encode((header, body))

    def next_message(self, mixList):
        if len(self.buffer) > 0:
            return self.buffer.pop(0)
        else:
            return self.create_drop_message(mixList)

    def get_buffered_message(self):
        while True:
            interval = sf.sampleFromExponential(self.EXP_PARAMS_PAYLOAD)
            time.sleep(interval)
            yield self.next_message()

    def decrypt_message(self, message):
        (header, body) = message
        peeledData = sphinx_process(self.params, self.privk, header, body)
        (tag, info, (header, body)) = peeledData
        routing = PFdecode(self.params, info)
        if routing[0] == Dest_flag:
            dest, message = receive_forward(self.params, body)
            if dest[-1] == self.name:
                return message
            else:
                raise Exception("Destination did not match")

    def process_message(self, data):
        try:
            message = petlib.pack.decode(data)
            msg = self.decrypt_message(message)
            if msg.startswith("HT"):
                print "[%s] > Heartbeat looped back" % self.name
            else:
                print "[%s] > New message unpacked." % (self.name)
            return msg
        except Exception, e:
            print "[%s] > ERROR: Message reading error: %s" % (self.name, str(e))
            print data

    def takePathSequence(self, mixnet):
        """ Function takes a random path sequence build of active mixnodes. If the
        default length of the path is bigger that the number of available mixnodes,
        then all mixnodes are used as path.

                Args:
                mixnet (list) - list of active mixnodes,
        """
        ENTRY_NODE = 0
        MIDDLE_NODE = 1
        EXIT_NODE = 2

        randomPath = []
        try:
            entries = [x for x in mixnet if x.group == ENTRY_NODE]
            middles = [x for x in mixnet if x.group == MIDDLE_NODE]
            exits = [x for x in mixnet if x.group == EXIT_NODE]

            entryMix = random.choice(entries)
            middleMix = random.choice(middles)
            exitMix = random.choice(exits)

            randomPath = [entryMix, middleMix, exitMix]
            return randomPath
        except Exception, e:
            print "[%s] > ERROR: During path generation: %s" % (self.name, str(e))



class LoopixMixNode(object):
    PATH_LENGTH = 3
    EXP_PARAMS_DELAY = (float(_PARAMS["parametersMixnodes"]["EXP_PARAMS_DELAY"]), None)
    EXP_PARAMS_LOOPS = (float(_PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"]), None)
    TAGED_HEARTBEATS = _PARAMS["parametersMixnodes"]["TAGED_HEARTBEATS"]
    NOISE_LENGTH = float(_PARAMS["parametersMixnodes"]["NOISE_LENGTH"])

    def __init__(self, host, port, name, privk, pubk, group=None):
        self.host = host
        self.port = port
        self.name = name
        self.privk = privk
        self.pubk = pubk
        self.params = SphinxParams(header_len=1024)
        self.group = group

    def createSphinxHeartbeat(self, mixers, timestamp):
        heartMsg = sf.generateRandomNoise(self.NOISE_LENGTH)
        header, body = makeSphinxPacket(
            self.params, self.EXP_PARAMS_DELAY, self, mixers, 'HT' + heartMsg)
        return (header, body)

    def process_sphinx_packet(self, message):
        header, body = message
        ret_val = sphinx_process(self.params, self.privk, header, body)
        return ret_val

    def handle_relay(self, header, body, meta_info):
        next_addr, dropFlag, delay, next_name = meta_info
        new_message = petlib.pack.encode((header, body))
        return "RELAY", delay, new_message, next_addr

    def process_message(self, data):
        peeledData = self.process_sphinx_packet(data)
        (tag, info, (header, body)) = peeledData
        # routing_flag, meta_info = PFdecode(self.params, info)
        routing = PFdecode(self.params, info)
        if routing[0] == Relay_flag:
            routing_flag, meta_info = routing
            return self.handle_relay(header, body, meta_info)
        elif routing[0] == Dest_flag:
            dest, message = receive_forward(self.params, body)
            print "[%s] > Message received" % self.name
            if dest[-1] == self.name:
                if message.startswith('HT'):
                    print "[%s] > Heartbeat looped pack" % self.name
                    return "DEST", message
            else:
                raise Exception("Destionation did not match")
        else:
            print 'Flag not recognized'



class LoopixProvider(LoopixMixNode):
    def __init__(self, *args, **kwargs):
        LoopixMixNode.__init__(self, *args, **kwargs)
        self.storage = {}
        self.clientList = []

    def saveInStorage(self, key, value):
        if key in self.storage:
            self.storage[key].append(value)
        else:
            self.storage[key] = [value]

    def handle_package(self, data):
        if data[:8] == "PULL_MSG":
            return self.get_user_messages(data[8:])
        return self.process_message(data)

    def get_user_messages(self, name):
        if name in self.storage:
            messages = self.storage[name]
            popped, rest = messages[:MAX_RETRIEVE], messages[MAX_RETRIEVE:]
            self.storage[name] = rest
            return popped
        return []

    def handle_relay(self, header, body, meta_info):
        next_addr, dropFlag, delay, next_name = meta_info
        if dropFlag:
            print "[%s] > Drop message." % self.name
            return "DROP", None
        else:
            new_message = petlib.pack.encode((header, body))
            if next_name in self.clientList:
                return "STORE", new_message, next_name
            else:
                return "RELAY", delay, new_message, next_addr




setup_mixes = []
setup_providers = []
setup_clients = []

def generate_key_pair():
    params = SphinxParams()
    o = params.group.G.order()

    priv = o.random()
    pubk = priv * params.group.g
    return priv, pubk

for i in range(3):
    mpriv, mpubk = generate_key_pair()
    mix = Mix('Mix%d'%i, 9000+i, '1.2.3.4', mpubk, i % 3)
    setup_mixes.append((mix, mpriv))


for i in range(3):
    ppriv, ppubk = generate_key_pair()
    provider = Provider('Provider%d'%i, 9010+i, '1.2.3.4', ppubk)
    setup_providers.append((provider, ppriv))

for i in range(3):
    upriv, upubk = generate_key_pair()
    user = User("User%d"%i, 9015+i, '1.2.3.4', upubk, setup_providers[i][0])
    setup_clients.append((user, upriv))



loopix_clients = []
loopix_mixnodes = []
loopix_providers = []

for mix in setup_mixes:
    mix_pubdata, mix_privk = mix
    mix = LoopixMixNode(mix_pubdata.host, mix_pubdata.port, mix_pubdata.name, mix_privk, mix_pubdata.pubk, mix_pubdata.group)
    loopix_mixnodes.append(mix)

for p in setup_providers:
    p_pubdata, p_privk = p
    provider = LoopixProvider(p_pubdata.host, p_pubdata.port, p_pubdata.name, p_privk, p_pubdata.pubk)
    loopix_providers.append(provider)

 
for u in setup_clients:
    u_pubdata, u_privk = u
    user = LoopixClient(u_pubdata.host, u_pubdata.port, u_pubdata.name, u_pubdata.provider, u_privk, u_pubdata.pubk)
    loopix_clients.append(user)


mixnodes = (loopix_mixnodes, [x[0] for x in setup_mixes])
providers = (loopix_providers, [x[0] for x in setup_providers])
clients = (loopix_clients, [x[0] for x in setup_clients])

def get_clients_provider(client):
    for p in providers[0]:
        if client.provider.name == p.name:
            return p
    return None

test_client = random.choice(clients[0])
test_provider = get_clients_provider(test_client)
test_provider.clientList = clients[1]

pub_mix_path = test_client.takePathSequence(mixnodes[1])
process_path = [test_provider] + mixnodes[0] + [test_provider]
#-----------------------------CHECK IF LOOPS WORK CORRECT-------------------------
loop_message = test_client.create_loop_message(pub_mix_path, time.time())


message = loop_message
for entity in process_path:
    flag, delay, message, new_addr = entity.process_message(petlib.pack.decode(message))

test_client.process_message(message)

#-----------------------------CHECK IF DROP MESSAGE WORKS CORRECT-------------------------
test_client.providers = providers[1]
drop_message = test_client.create_drop_message(pub_mix_path)
 

