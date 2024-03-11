# Changelog

## 3.6
- update to the latest stable version of pjsip

## 3.5.1
- Add error handling for getting TTS messages

## 3.5
- Add command to `stop_playback`
- Add command to play audio file or message
- New webhooks for playback done, ring timeout, and menu timeout

## 3.4
- Add additional data to home-assistant service calls (e.g. add variables to script calls)
- Additional logging for troubleshooting

## 3.3
- Disable debug mode for pjsip

## 3.2
- Updated pjsip to latest version

## 3.1
- Reverted slug change because requirements where changed again in 2023.9.2 and created issues. If you already changed the slug in your automations you need to redo that. Sorry for any inconvenience.

## 3.0
- Changed slug to new requirements in home-assistant 2023.9
- Added option to call commands directly from menu 
  (previously only possible through stdin action in home-assistant)
- Updated pjsip to latest version

## 2.9
- Allow transfer of calls
- Bridge audio streams between calls
- Add handling of wav files returned from TTS services
- Allow three SIP accounts

## 2.8
- Add fault-handler
- Upgrade to python 3.10
- Use alpine image instead of ubuntu

## 2.7
- More flexible `return` post action: specify how many levels to go back from the sub-menu
- Added `jump` post action to jump to any menu with an id
- Add wildcard support for incoming call `allowed_numbers` and `blocked_numbers` filter
- Bugfix: time-out not reset when returning to parent menu

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
