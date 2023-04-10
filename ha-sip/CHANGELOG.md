# Changelog

## 2.7

- Added option to play a list of messages and/or audio files
- Added option `repeat_playlist` to `post_action`: repeat whole playlist. `repeat_message` will repeat only the last item in case of a playlist.
- Added option `repeat_wait` for an extra delay between repeated messages (in seconds).
  ```yaml
    menu:
        playlist:
            - type: tts
              message: "Hello World!"
            - type: audio_file
              audio_file: "/config/audio/welcome.mp3"
        post_action: "repeat_playlist"
        repeat_wait: 2
    ```

## 2.6
- Call additional web-hooks for incoming and outgoing calls
#### Deprecation notice: `webhook_to_call_after_call_was_established` will be removed in the next release and is replaced by the more granular `webhook_to_call`.

The old config option can be converted from

```yaml
webhook_to_call_after_call_was_established: another_webhook_id
```

to

```yaml
webhook_to_call:
    call_established: another_webhook_id
```


## 2.5
- Add option to repeat message until timeout is reached

## 2.4
- add name server config for SIP servers that must be resolved via SRV record
- improve logging

## 2.3
- add account index to web-hook calls
- update to the latest stable version of pjsip

## 2.2
- add ability to play sound files (.wav, .mp3) instead of TTS message

## 2.1
- Bugfix: incoming number could not be found from a stdin action under certain circumstances
- Bugfix: `post_action` failed to run when keys are prematurely pressed

## 2.0
#### Breaking change: if you are not using 5060 as your sip port, you need to set it in global SIP options again 
- allow two SIP accounts
- accept calls and define own menu for incoming calls (configurable by SIP account)
- menu choices can consist of more than one digit
- add option to handle menu digits as PIN
- allow sending of DTMF digits to an established call
- introduce `post_action` to hang up or return after menu was selected
- add option to call webhook after menu is selected
- add `timeout` option (defaults to 300 seconds) to menu entries
- Add more web-hooks to control ha-sip from home-assistant
- update to the latest stable version of pjsip
- Revamped docs on GitHub

## 1.5
- add language option for TTS

## 1.4
- call webhook on incoming calls
- update to the latest stable version of pjsip
- Use docker hub images, instead of local build to reduce installation time and allow installation of devices with little memory
- Add icon

## 1.3
- fix build on aarch64 cpu architecture

## 1.2
- use fixed commit for known working pjsip

## 1.1
- fix wrong build image for `aarch64`
