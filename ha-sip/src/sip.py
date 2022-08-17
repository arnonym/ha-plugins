import pjsua2 as pj


class MyEndpointConfig(object):
    def __init__(
        self,
        port: int,
    ):
        self.port = port


def create_endpoint(config: MyEndpointConfig):
    ep_cfg = pj.EpConfig()
    ep_cfg.uaConfig.threadCnt = 0
    ep_cfg.uaConfig.mainThreadOnly = True
    ep_cfg.logConfig.level = 5
    end_point = pj.Endpoint()
    end_point.libCreate()
    end_point.libInit(ep_cfg)
    end_point.audDevManager().setNullDev()
    sip_tp_config = pj.TransportConfig()
    sip_tp_config.port = config.port
    end_point.transportCreate(pj.PJSIP_TRANSPORT_UDP, sip_tp_config)
    end_point.libStart()
    return end_point
