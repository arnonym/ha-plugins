import os
from enum import Enum
from typing import Optional, Callable, Union, TypedDict

import ha

import pjsua2 as pj


class CallStateChange(Enum):
    CALL = 1
    HANGUP = 2


CallCallback = Callable[[CallStateChange, str, 'Call'], None]
StateType = Union[str, int, bool, float]


class Action(TypedDict):
    domain: str
    service: str
    entity_id: str


class Menu(TypedDict):
    message: str
    action: Optional[Action]
    choices: dict[int, 'Menu']  # type: ignore


class Call(pj.Call):
    def __init__(self, end_point: pj.Endpoint, account: pj.Account, call_id: str, uri_to_call: str, menu: Optional[Menu],
                 callback: CallCallback, ha_config: ha.HaConfig):
        pj.Call.__init__(self, account, call_id)
        self.end_point = end_point
        self.account = account
        self.uri_to_call = uri_to_call
        self.menu = menu
        self.callback = callback
        self.ha_config = ha_config
        self.connected: bool = False
        self.callback(CallStateChange.CALL, self.uri_to_call, self)
        self.player: Optional[pj.AudioMediaPlayer] = None
        self.audio_media: Optional[pj.AudioMedia] = None
        self.played_message = False

    def onCallState(self, prm):
        ci = self.getInfo()
        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            self.connected = True
            print('| Call connected')
        elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            self.connected = False
            self.account.c = None
            self.account.acceptCall = False
            self.account.inCall = False
            self.account.call_id = None
            self.callback(CallStateChange.HANGUP, self.uri_to_call, self)
            print('| Call disconnected')
        else:
            print('| Unknown state:', ci.state)

    def onCallMediaState(self, prm):
        call_info = self.getInfo()
        print('| onCallMediaState', call_info.state)
        for media_index, media in enumerate(call_info.media):
            if media.type == pj.PJMEDIA_TYPE_AUDIO and call_info.stateText == 'CONFIRMED':
                self.audio_media = self.getAudioMedia(media_index)
                self.handle_menu_entry(self.menu)

    def onDtmfDigit(self, prm: pj.OnDtmfDigitParam):
        print('| onDtmfDigit: digit', prm.digit)
        if not self.menu:
            return
        digit = prm.digit
        choices = self.menu.get('choices')
        if choices and digit in choices:
            self.menu = choices[digit]
        self.handle_menu_entry(self.menu)

    def handle_menu_entry(self, menu_entry: Optional[Menu]) -> None:
        if not menu_entry:
            return
        message = menu_entry.get('message', 'No message provided')
        self.play_message(message)
        action = menu_entry.get('action')
        if not action:
            print('| No action supplied')
            return
        domain = action.get('domain')
        service = action.get('service')
        entity_id = action.get('entity_id')
        if (not domain) or (not service) or (not entity_id):
            print('| Error: one of domain, service or entity_id was not provided')
            return
        print('| Calling home assistant service on domain', domain, 'service', service, 'with entity', entity_id)
        try:
            ha.call_service(self.ha_config, domain, service, entity_id)
        except Exception as e:
            print('| Error calling home-assistant service:', e)

    def play_message(self, message: str) -> None:
        if self.played_message:  # pjsip never returns control if createPlayer is called while another wav is still playing. stopTransmit() is useless.
            return
        self.played_message = True
        print('| Playing message:', message)
        self.player = pj.AudioMediaPlayer()
        sound_file_name, must_be_deleted = ha.create_and_get_tts(self.ha_config, message)
        self.player.createPlayer(file_name=sound_file_name)
        self.player.startTransmit(self.audio_media)
        if must_be_deleted:
            # looks like `createPlayer` is loading the file to memory, and it can be removed already
            os.remove(sound_file_name)

    def hangup_call(self):
        call_prm = pj.CallOpParam(True)
        pj.Call.hangup(self, call_prm)
    
    def dtmf(self,dtmfToDial):
        pj.Call.dial_dtmf(int(dtmfToDial))


def make_call(ep: pj.Endpoint, account: pj.Account, uri_to_call: str, menu: Optional[Menu], callback: CallCallback, ha_config: ha.HaConfig):
    new_call = Call(ep, account, pj.PJSUA_INVALID_ID, uri_to_call, menu, callback, ha_config)
    call_param = pj.CallOpParam(True)
    new_call.makeCall(uri_to_call, call_param)
    return new_call
