# Changelog

## 1.6
#### Breaking change: if you are not using 5060 as your sip port, you need to set it in global SIP options again 
- allow two SIP accounts
- accept calls and define own menu for incoming calls (configurable by SIP account)
- menu choices can consist of more than one digit
- add option to handle menu digits as PIN
- allow sending of DTMF digits to an established call
- introduce `post_action` to hang up or return after menu was selected
- add option to call webhook after menu is selected
- add `timeout` option (defaults to 300 seconds) to menu entries
- update to the latest stable version of pjsip
- Revamped docs on GitHub

## 1.5
- Add language option for TTS

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
