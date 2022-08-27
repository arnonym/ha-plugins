import pjsua2 as pj


class MyEndpointConfig(object):
    def __init__(self, port: int, log_level: int):
        self.port = port
        self.log_level = log_level


def create_endpoint(config: MyEndpointConfig) -> pj.Endpoint:
    ep_cfg = pj.EpConfig()
    ep_cfg.uaConfig.threadCnt = 0
    ep_cfg.uaConfig.mainThreadOnly = True
    ep_cfg.logConfig.level = config.log_level
    end_point = pj.Endpoint()
    end_point.libCreate()
    end_point.libInit(ep_cfg)
    end_point.audDevManager().setNullDev()
    sip_tp_config = pj.TransportConfig()
    sip_tp_config.port = config.port
    end_point.transportCreate(pj.PJSIP_TRANSPORT_UDP, sip_tp_config)
    end_point.libStart()
    return end_point
