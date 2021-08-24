import os
from enum import Enum
from typing import Callable, TypeVar

import constants

import pjsua2 as pj


class CallStateChange(Enum):
    CALL = 1
    HANGUP = 2


CallType = TypeVar('CallType', bound='Call')
CallCallback = Callable[[CallStateChange, str, CallType], None]


class Call(pj.Call):
    def __init__(self, end_point: pj.Endpoint, account: pj.Account, call_id: str, uri_to_call: str, callback: CallCallback):
        pj.Call.__init__(self, account, call_id)
        self.end_point = end_point
        self.account = account
        self.uri_to_call = uri_to_call
        self.callback = callback
        self.on_hold = False
        self.connected = False
        self.callback(CallStateChange.CALL, self.uri_to_call, self)
        self.player = pj.AudioMediaPlayer()
        sound_file = os.path.join(constants.ROOT_PATH, "sound/answer.wav")
        self.player.createPlayer(file_name=sound_file)

    def onCallState(self, prm):
        ci = self.getInfo()
        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            self.connected = True
            print("########################################## Call connected")
        if ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            self.connected = False
            self.on_hold = False
            self.account.c = None
            self.account.acceptCall = False
            self.account.inCall = False
            self.account.call_id = None
            self.callback(CallStateChange.HANGUP, self.uri_to_call)
            print("########################################## Call disconnected")

    def onCallMediaState(self, prm):
        call_info = self.getInfo()
        print("########################################## onCallMediaState", call_info.state)
        for media_index, media in enumerate(call_info.media):
            if media.type == pj.PJMEDIA_TYPE_AUDIO and call_info.stateText == "CONFIRMED":
                self.play_media(media_index)

    def play_media(self, media_index):
        audio_media = self.getAudioMedia(media_index)
        self.player.startTransmit(audio_media)

    def hangup_call(self):
        call_prm = pj.CallOpParam(True)
        pj.Call.hangup(self, call_prm)


def make_call(ep: pj.Endpoint, account: pj.Account, uri_to_call: str, callback: CallCallback):
    new_call = Call(ep, account, pj.PJSUA_INVALID_ID, uri_to_call, callback)
    call_param = pj.CallOpParam(True)
    new_call.makeCall(uri_to_call, call_param)
    return new_call
