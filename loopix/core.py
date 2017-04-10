from loopix import supportFunctions as sf

class LoopixClient(object):
    PATH_LENGTH = int(_PARAMS["parametersClients"]["PATH_LENGTH"])
    EXP_PARAMS_PAYLOAD = (
        float(_PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"]), None)

    EXP_PARAMS_LOOPS = (
        float(_PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"]), None)
    EXP_PARAMS_COVER = (
        float(_PARAMS["parametersClients"]["EXP_PARAMS_COVER"]), None)
    EXP_PARAMS_DELAY = (
        float(_PARAMS["parametersClients"]["EXP_PARAMS_DELAY"]), None)

    def __init__(self, name, providerId, privk, pubk):
        self.name = name
        self.providerId = providerId
        self.privk = privk
        self.pubk = pubk
        self.buffer = []

    def create_drop_message(self, mixers, receiver):
        randomMessage = sf.generateRandomNoise(NOISE_LENGTH)
        return self.makeSphinxPacket(
            receiver, mixers, randomMessage, dropFlag=True)

    def create_loop_message(self, mixers, timestamp):
        """ Function creates a heartbeat - a noise message for which the sender and the receiver are the same entity.

                Args:
                mixes (list): list of mixnodes which the message should go through,
                timestamp (?): a timestamp at which the message was created.
        """
        try:
            heartMsg = sf.generateRandomNoise(NOISE_LENGTH)
            (header, body) = self.makeSphinxPacket(
                self, mixers, 'HT' + heartMsg + str(timestamp), dropFlag=False)
            return (header, body)
        except Exception, e:
            print "[%s] > ERROR createHeartbeat: %s" % (self.name, str(e))
            return None

    def makeSphinxPacket(self, receiver, mixers, message, dropFlag=False):
        path = [self.provider] + mixers + [receiver.provider] + [receiver]
        keys_nodes = [n.pubk for n in path]

        nodes_routing = []
        for i in range(len(path)):
            if float(EXP_PARAMS_DELAY[0]) == 0.0:
                delay = 0.0
            else:
                delay = sf.sampleFromExponential(EXP_PARAMS_DELAY)
            if i == len(path) - 1 and dropFlag:
                nodes_routing.append(
                    Nenc([(path[i].host, path[i].port), True, delay, path[i].name]))
            else:
                nodes_routing.append(
                    Nenc([(path[i].host, path[i].port), False, delay, path[i].name]))

        # Destination of the message
        dest = (receiver.host, receiver.port, receiver.name)
        header, body = create_forward_message(self.params, nodes_routing, keys_nodes, dest, message)
        return (header, body)

    def next_message(self, mixList):
        if len(self.buffer) > 0:
            return self.buffer.pop(0)
        else:
            return self.create_drop_message(mixList, ???)

    def get_buffered_message(self):
        while True:
            interval = sf.sampleFromExponential(EXP_PARAMS_PAYLOAD)
            time.sleep(interval)
            yield self.next_message()

    def decrypt_message(self, message, (host, port)):
        """ Function allows to decyrpt and read a received message.

                Args:
                message (list) - received packet,
                host (str) - host of a provider,
                port (int) - port of a provider.
        """
        try:
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
                    return None
        except Exception, e:
            print "[%s] > ERROR: During message reading: %s" % (self.name, str(e))

    def process_message(self, data, host, port):
        try:
            message = petlib.pack.decode(data)
            msg = self.decrypt_message(message, (host, port))
            if msg.startswith("HT"):
                print "[%s] > Heartbeat looped back" % self.name
            else:
                print "[%s] > New message unpacked." % (self.name)
            return msg
        except Exception, e:
            print "[%s] > ERROR: Message reading error: %s" % (self.name, str(e))
            print data

    def takePathSequence(self, mixnet, length):
        """ Function takes a random path sequence build of active mixnodes. If the
        default length of the path is bigger that the number of available mixnodes,
        then all mixnodes are used as path.

                Args:
                mixnet (list) - list of active mixnodes,
                length (int) - length of the path which we want to build.
        """
        ENTRY_NODE = 0
        MIDDLE_NODE = 1
        EXIT_NODE = 2
        GROUPS = [ENTRY_NODE, MIDDLE_NODE, EXIT_NODE]

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

    def __init__(self, host, port, name, setup, privk, pubk):
        self.host = host
        self.port = port
        self.name = name
        self.setup = setup
        self.G, self.o, self.g, self.o_bytes = self.setup
        self.privk = privk
        self.pubk = pubk
        self.params = SphinxParams(header_len=1024)

    def createSphinxHeartbeat(self, mixes, timestamp, typeFlag=None):
        heartMsg = sf.generateRandomNoise(NOISE_LENGTH)
        path = mixes + [self]
        header, body = self.packIntoSphinxPacket('HT' + heartMsg, path, typeFlag)
        return (header, body)

    def packIntoSphinxPacket(self, message, path):
        keys_nodes = [n.pubk for n in path]
        nodes_routing = []

        for i in range(len(path)):
            if float(EXP_PARAMS_DELAY[0]) == 0.0:
                delay = 0.0
            else:
                delay = sf.sampleFromExponential(self.EXP_PARAMS_DELAY)
            nodes_routing.append(
                Nenc([(path[i].host, path[i].port), False, delay, path[i].name]))

        dest = (self.host, self.port, self.name)
        header, body = create_forward_message(
            self.params, nodes_routing, keys_nodes, dest, message)
        return (header, body)

    def process_sphinx_packet(self, message):
        header, body = message
        ret_val = sphinx_process(self.params, self.privk, header, body)
        return ret_val

    def process_message(self, data):
        peeledData = self.process_sphinx_packet(data)
        (tag, info, (header, body)) = peeledData
        # routing_flag, meta_info = PFdecode(self.params, info)
        routing = PFdecode(self.params, info)
        if routing[0] == Relay_flag:
            routing_flag, meta_info = routing
            next_addr, dropFlag, delay, next_name = meta_info
            time.sleep(delay)
            return "RELAY", petlib.pack.encode((header, body)), next_addr

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

    def process_messages(self):
        while True:
            msg = inputqueue.pop()
            # THREAD
            processed = self.process_message(msg)
            if processed[0] == "RELAY":
                outboxqueue.add(processed)


class LoopixProvider(LoopixMixNode):
    def __init__(self, *args, **kwargs):
        LoopixMixNode.__init__(self, *args, **kwargs)
        self.storage = {}

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

    def process_message(self, data):
        peeledData = self.process_sphinx_packet(data)
        (tag, info, (header, body)) = peeledData
        #routing_flag, meta_info = PFdecode(self.params, info)
        routing = PFdecode(self.params, info)
        if routing[0] == Relay_flag:
            routing_flag, meta_info = routing
            next_addr, dropFlag, typeFlag, delay, next_name = meta_info
            if dropFlag:
                print "[%s] > Drop message." % self.name
            else:
                if next_name in self.clientList:
                    self.saveInStorage(next_name,
                                       petlib.pack.encode((header, body)))
                else:
                    time.sleep(delay)
                    return "RELAY", petlib.pack.encode((header, body)), next_addr
        elif routing[0] == Dest_flag:
            dest, message = receive_forward(self.params, body)
            if dest[-1] == self.name:
                if message.startswith('HT'):
                    # print "[%s] > Heartbeat looped back" % self.name
                    pass
                if message.startswith('TAG'):
                    # print "[%s] > Tagged message received" % self.name
                    self.measureLatency(message)
                self.bProcessed += 1
            else:
                raise Exception("Destination did not match")
