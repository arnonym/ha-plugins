import pjsua2 as pj

from log import log


class MyEndpointConfig(object):
    def __init__(self, port: int, log_level: int, name_server: list[str]):
        self.port = port
        self.log_level = log_level
        self.name_server = name_server


def create_endpoint(config: MyEndpointConfig) -> pj.Endpoint:
    ep_cfg = pj.EpConfig()
    ep_cfg.uaConfig.threadCnt = 0
    ep_cfg.uaConfig.mainThreadOnly = True
    if config.name_server:
        nameserver = pj.StringVector()
        for ns in config.name_server:
            nameserver.append(ns)
        ep_cfg.uaConfig.nameserver = nameserver
    ep_cfg.logConfig.level = config.log_level
    end_point = pj.Endpoint()
    end_point.libCreate()
    end_point.libInit(ep_cfg)
    codecs = end_point.codecEnum2()
    log(None, "Supported audio codecs: %s" % ", ".join(c.codecId for c in codecs))
    end_point.audDevManager().setNullDev()
    sip_tp_config = pj.TransportConfig()
    sip_tp_config.port = config.port
    end_point.transportCreate(pj.PJSIP_TRANSPORT_UDP, sip_tp_config)
    end_point.libStart()
    return end_point
