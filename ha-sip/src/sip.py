import pjsua2 as pj

from options_global import GlobalOptions
from log import log


class MyEndpointConfig(object):
    def __init__(self, port: int, log_level: int, name_server: list[str], global_options: GlobalOptions):
        self.port = port
        self.log_level = log_level
        self.name_server = name_server
        self.global_options = global_options


def create_endpoint(ep_config: MyEndpointConfig) -> pj.Endpoint:
    ep_cfg = pj.EpConfig()
    ep_cfg.logConfig.level = ep_config.log_level
    ep_cfg.uaConfig.threadCnt = 0
    ep_cfg.uaConfig.mainThreadOnly = True
    if ep_config.name_server:
        nameserver = pj.StringVector()
        for ns in ep_config.name_server:
            nameserver.append(ns)
        ep_cfg.uaConfig.nameserver = nameserver
    if ep_config.global_options.stun_server:
        log(None, f"STUN server enabled: {ep_config.global_options.stun_server}")
        ep_cfg.uaConfig.stunServer.append(ep_config.global_options.stun_server)
    end_point = pj.Endpoint()
    end_point.libCreate()
    end_point.libInit(ep_cfg)
    codecs = end_point.codecEnum2()
    log(None, f"Supported audio codecs: {', '.join(c.codecId for c in codecs)}")
    end_point.audDevManager().setNullDev()
    if ep_config.global_options.enable_udp:
        log(None, f"UDP transport enabled on port {ep_config.port}")
        sip_tp_config_udp = pj.TransportConfig()
        sip_tp_config_udp.port = ep_config.port
        end_point.transportCreate(pj.PJSIP_TRANSPORT_UDP, sip_tp_config_udp)
    if ep_config.global_options.enable_tcp:
        log(None, f"TCP transport enabled on port {ep_config.port}")
        sip_tp_config_tcp = pj.TransportConfig()
        sip_tp_config_tcp.port = ep_config.port
        end_point.transportCreate(pj.PJSIP_TRANSPORT_TCP, sip_tp_config_tcp)
    if ep_config.global_options.enable_tls:
        log(None, f"TLS transport enabled on port {ep_config.global_options.tls_port}")
        sip_tp_config_tls = pj.TransportConfig()
        sip_tp_config_tls.port = ep_config.global_options.tls_port
        end_point.transportCreate(pj.PJSIP_TRANSPORT_TLS, sip_tp_config_tls)
    end_point.libStart()
    return end_point
