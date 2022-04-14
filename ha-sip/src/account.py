import pjsua2 as pj

import call


class MyAccountConfig(object):
    def __init__(
        self,
        id_uri: str,
        registrar_uri: str,
        realm: str,
        user_name: str,
        password: str
    ):
        self.id_uri = id_uri
        self.registrar_uri = registrar_uri
        self.realm = realm
        self.user_name = user_name
        self.password = password
        self.ice_enabled = True


class Account(pj.Account):
    def __init__(self, end_point: pj.Endpoint, callback: call.CallCallback):
        pj.Account.__init__(self)
        self.end_point = end_point
        self.callback = callback

    def create(self, cfg: MyAccountConfig, make_default=False):
        account_config = pj.AccountConfig()
        account_config.idUri = cfg.id_uri
        account_config.regConfig.registrarUri = cfg.registrar_uri
        credentials = pj.AuthCredInfo('digest', cfg.realm, cfg.user_name, 0, cfg.password)
        account_config.sipConfig.authCreds.append(credentials)
        account_config.natConfig.iceEnabled = cfg.ice_enabled
        return pj.Account.create(self, account_config, make_default)

    def onRegState(self, prm):
        print('| OnRegState:', prm.code, prm.reason)

    def onIncomingCall(self, prm):
        c = call.Call(self.end_point, self, prm.callId, prm.callId, self.callback)
        ci = c.getInfo()
        print('| Incoming call  from  \'%s\'' % ci.remoteUri)
        # Ignore call for now:
        # call_prm = pj.CallOpParam()
        # call_prm.statusCode = 200
        # c.answer(call_prm)


def create_account(end_point: pj.Endpoint, cfg: MyAccountConfig, callback: call.CallCallback):
    account = Account(end_point, callback)
    account.create(cfg, make_default=True)
    return account
