import json
from support_formats import Params

class JSONReader(object):
    def __init__(self, fileName):
        with open(fileName) as infile:
            self._PARAMS = json.load(infile)

    def get_client_config_params(self):
        exp_params_loops = float(self._PARAMS["parametersClients"]["EXP_PARAMS_LOOPS"])
        exp_params_drop = float(self._PARAMS["parametersClients"]["EXP_PARAMS_DROP"])
        exp_params_payload = float(self._PARAMS["parametersClients"]["EXP_PARAMS_PAYLOAD"])
        exp_params_delay = float(self._PARAMS["parametersClients"]["EXP_PARAMS_DELAY"])
        database_name = self._PARAMS["parametersClients"]["DATABASE_NAME"]
        time_pull = float(self._PARAMS["parametersClients"]["TIME_PULL"])
        noise_length = int(self._PARAMS["parametersMixnodes"]["NOISE_LENGTH"])
        data_dir = self._PARAMS["parametersClients"]["DATA_DIR"]

        config_params = Params(EXP_PARAMS_LOOPS = exp_params_loops,
                                EXP_PARAMS_DROP = exp_params_drop,
                                EXP_PARAMS_PAYLOAD = exp_params_payload,
                                EXP_PARAMS_DELAY = exp_params_delay,
                                DATABASE_NAME = database_name,
                                NOISE_LENGTH = noise_length,
                                TIME_PULL = time_pull,
                                DATA_DIR = data_dir)
        return config_params

    def get_mixnode_config_params(self):
        exp_params_loops = float(self._PARAMS["parametersMixnodes"]["EXP_PARAMS_LOOPS"])
        exp_params_delay = float(self._PARAMS["parametersMixnodes"]["EXP_PARAMS_DELAY"])
        database_name = self._PARAMS["parametersMixnodes"]["DATABASE_NAME"]
        noise_length = int(self._PARAMS["parametersMixnodes"]["NOISE_LENGTH"])
        max_delay_time = int(self._PARAMS["parametersMixnodes"]["MAX_DELAY_TIME"])

        config_params = Params(EXP_PARAMS_LOOPS = exp_params_loops,
                                EXP_PARAMS_DELAY = exp_params_delay,
                                DATABASE_NAME = database_name,
                                MAX_DELAY_TIME = max_delay_time,
                                NOISE_LENGTH = noise_length)
        return config_params

    def get_provider_config_params(self):
        config_params = self.get_mixnode_config_params()
        max_retrieve = int(self._PARAMS["parametersProviders"]["MAX_RETRIEVE"])
        config_params = config_params._replace(MAX_RETRIEVE = max_retrieve)
        return config_params
