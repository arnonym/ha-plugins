# ![logo](icon.png) ha-sip 

### Home Assistant SIP/VoIP Gateway is a Home Assistant add-on which 
- allows the dialing and hanging up of phone numbers through a SIP end-point 
- triggering of services through dial tones (DTMF) after the call was established.
- listens for incoming calls and can trigger actions through a web-hook (the call is not picked up)
- accepting calls (optionally filtered by number)
- handle PIN input before triggering actions
- send DTMF digits to an established call (incoming or outgoing)

## Installation

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Farnonym%2Fha-plugins)

This add-on is for the Home Assistant OS or supervised installation methods mentioned in
https://www.home-assistant.io/installation/. With that in place you can install this third-party plug-in like described in
https://www.home-assistant.io/common-tasks/os#installing-third-party-add-ons. The repository URL is
`https://github.com/arnonym/ha-plugins`.

After that you need to configure your SIP account(s), TTS parameters and webhook ID. The default configuration looks like this:

```yaml
sip_global:
    port: 5060
    log_level: 5 # log level of pjsip library
    name_server: '' # comma separated list of name servers, must be set if sip server must be resolved via SRV record
sip:
    enabled: true
    registrar_uri: sip:fritz.box
    id_uri: sip:homeassistant@fritz.box
    realm: '*'
    user_name: homeassistant
    password: secure
    answer_mode: listen  # "listen" or "accept", see below
    settle_time: 1 # time to wait for playing the message/actions/etc. after call was established
    incoming_call_file: "" # config and menu definition file for incoming calls, see below
sip_2:
    enabled: false
    registrar_uri: sip:fritz.box
    id_uri: sip:anotheruser@fritz.box
    realm: '*'
    user_name: anotheruser
    password: secret
    answer_mode: listen
    settle_time: 1
    incoming_call_file: ""
tts:
    platform: google_translate
    language: en # might also be in en-US format, depending on the platform
webhook:
    id: sip_call_webhook_id
```

> **Note**
> When your `user_name` or `password` starts with a number, you need to put it in quotes like `"1234"`.

## Usage

### Outgoing calls

Outgoing calls are made via the `hassio.addon_stdin` service in the action part of an automation.
To be able to enter the full command, you must switch to YAML mode by clicking on the menu with the triple dot and
selecting `Edit in YAML`.

You can use `dial` and `hangup` with the `hassio.addon_stdin` service to control outgoing calls in an action in 
your automation:

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: dial
        number: sip:**620@fritz.box # number to call. Format depends on your SIP provider, 
                                    # but might look like 'sip:+49123456789@fritz.box' for external calls
        webhook_to_call_after_call_was_established: another_webhook_id # web-hook id which you can listen on in your actions (deprecated)
        webhook_to_call: # web-hook IDs which you can listen on in your actions (additional to the global web-hook)
            ring_timeout: another_webhook_id # can be all the same, or different
            call_established: another_webhook_id
            entered_menu: another_webhook_id
            timeout: another_webhook_id  # is called after the given time-out on a menu is reached
            dtmf_digit: another_webhook_id # is called when the calling party sends a DTMF tone
            call_disconnected: another_webhook_id
            playback_done: another_webhook_id # is called after playback of message or audio file is done
        ring_timeout: 15 # time to ring in seconds (optional, defaults to 300)
        sip_account: 1 # number of configured sip account: 1 or 2 
                       # (optional, defaults to first enabled sip account)
        menu:
            message: There's a burglar in da house.
```

If there is already an outgoing call to the same number active, the request will be ignored.

#### To hang up the call again:

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: hangup
        number: sip:**620@fritz.box
```

#### To send DTMF digits to an established call:

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: send_dtmf
        number: sip:**620@fritz.box
        digits: "123#"
        method: in_band # method can be "in_band" (default), "rfc2833" or "sip_info"
```

> **Note**
> When using a `#` digit, you need to put the whole sequence in quotes, eg. `"#5"`.

> **Warning**
> You can't use the `post_action` with `send_dtmf` because I don't see a way to know when PJSIP is done sending the tones.

#### To transfer a call to a different SIP URI:

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: transfer
        number: sip:**620@fritz.box
        transfer_to: sip:**623@fritz.box
```

#### To bridge the audio streams of two active calls:

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: bridge_audio
        number: sip:**620@fritz.box
        bridge_to: sip:**623@fritz.box
```

#### To play a message through TTS

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: play_message
        number: sip:**620@fritz.box
        message: hello!
        tts_language: en
```

#### To play an audio file

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: play_audio_file
        number: sip:**620@fritz.box
        audio_file: '/config/audio/welcome.mp3'
```

#### To stop audio playback (both audio file and message):

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: stop_playback
        number: sip:**620@fritz.box
```

### Incoming calls

#### Listen mode

In `listen` mode no call will be answered (picked up) but you can trigger an automation through a [Webhook trigger](https://www.home-assistant.io/docs/automation/trigger/#webhook-trigger) for every incoming call.
The webhook ID must match the ID set in the configuration.

You can get the caller from `{{trigger.json.caller}}` or `{{trigger.json.parsed_caller}}` for usage in e.g. the action of your automation. 
If you also use the menu ID webhook you also need to check for `{{ trigger.json.event == "incoming_call" }}` e.g. in a "Choose" action type.

Example of "incoming call" webhook message:

```json
{
    "event": "incoming_call",
    "caller": "<sip:5551234456@fritz.box>",
    "parsed_caller": "5551234456",
    "sip_account": 1
}
```

You can also answer an incoming call from home assistant by using the `hassio.addon_stdin` service:

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: answer
        number: "5551234456" # if this is unclear, you can look that up in the logs ("Registering call with id <number>")
        menu:
          message: Bye
          post_action: hangup
```

If you don't provide a menu the menu from `incoming_call_file` will be used.

#### Accept mode

In `accept` mode you can additionally make ha-sip to accept the call. For this you can define a menu per SIP account. Put a config file
into your `/config` directory of your home-assistant installation (e.g. use the samba add-on to access that directory).

Example content of `/config/sip-1-incoming.yaml`:

```yaml
allowed_numbers: # list of numbers which will be answered. If removed all numbers will be accepted
    - "5551234456"
    - "5559876543"
    - "555{*}" # matches every number starting with 555
    - "555{?}" # matches every number starting with 555 which is 4 digits long
# blocked_numbers: # alternatively you can specify the numbers not to be answered. You can't have both.
#    - "5551234456"
#    - "5559876543"
answer_after: 0 # time in seconds after the call is answered (optional, defaults to 0)
webhook_to_call: # web-hook IDs which you can listen on in your actions (additional to the global web-hook)
    call_established: another_webhook_id # can be all the same, or different
    entered_menu: another_webhook_id
    dtmf_digit: another_webhook_id
    call_disconnected: another_webhook_id
menu:
    message: Please enter your access code
    choices_are_pin: true
    choices:
        '1234':
            id: owner
            message: Welcome beautiful.
            post_action: hangup
        '5432':
            id: maintenance
            message: Your entrance has been logged.
            post_action: hangup
        'default':
            id: wrong_code
            message: Wrong code, please try again
            post_action: return
```

After that you set `incoming_call_file` in the add-on configuration to `/config/sip-1-incoming.yaml`.

## Call menu definition

used for incoming and outgoing calls.

```yaml
menu:
    id: main # If "id" is present, a message will be sent via webhook (entered_menu), see below (optional)
    message: Please enter your access code # the message to be played via TTS (optional, defaults to empty)
    language: en # TTS language (optional, defaults to the global language from add-on config)
    choices_are_pin: true # If the choices should be handled like PINs (optional, defaults to false)
    timeout: 10 # time in seconds before "timeout" choice is triggered (optional, defaults to 300)
    post_action: noop # this action will be triggered after the message was played. Can be 
                      # "noop" (do nothing), 
                      # "return <level>" (makes only sense in a sub-menu, returns <level> levels, defaults to 1), 
                      # "hangup" (hang-up the call) and
                      # "repeat_message" (repeat the message until the time-out is reached)
                      # "jump <menu-id>" (jumps to menu with id <menu-id>)
                      # (optional, defaults to noop)
    action: # action to run when menu was entered (before playing the message) (optional)
        # For details visit https://developers.home-assistant.io/docs/api/rest/, POST on /api/services/<domain>/<service>
        domain: switch # home-assistant domain
        service: turn_on # home-assistant service
        entity_id: switch.open_front_door # home assistant entity
    choices: # the list of actions available through DTMF (optional)
        '1234': # DTMF sequence, and definition of a sub-menu
            id: owner # same as above, also any other option from above can be used in this sub-menu
            message: Welcome beautiful.
            post_action: hangup 
        '5432':
            id: maintenance
            message: Your entrance has been logged.
            post_action: hangup
        '7777':
            audio_file: '/config/audio/welcome.mp3' # audio file to be played (.wav or .mp3).
            post_action: jump owner # jump to menu id 'owner'
        'default': # this will be triggered if the input does not match any specified choice
            id: wrong_code
            message: Wrong code, please try again
            post_action: return
        'timeout': # this will be triggered when there is no input 
            id: timeout
            message: Bye.
            post_action: hangup
```

> **Note** 
> The audio files need to reside in your home-assistant `config` directory, as this is the only directory accessible inside the add-on.

## Web-hooks

For most events in ha-sip there's a web-hook triggered:

### `incoming_call`

```json
{
    "event": "incoming_call",
    "caller": "<sip:5551234456@fritz.box>",
    "parsed_caller": "5551234456",
    "sip_account": 1
}
```

### `call_established`

```json
{
    "event": "call_established",
    "caller": "<sip:5551234456@fritz.box>",
    "parsed_caller": "5551234456",
    "sip_account": 1
}
```

### `entered_menu`

```json
{
    "event": "entered_menu",
    "caller": "<sip:5551234456@fritz.box>",
    "parsed_caller": "5551234456",
    "menu_id": "owner",
    "sip_account": 1
}
```

### `dtmf_digit`

```json
{
    "event": "dtmf_digit",
    "caller": "<sip:5551234456@fritz.box>",
    "parsed_caller": "5551234456",
    "digit": "1",
    "sip_account": 1
}
```

### `call_disconnected`

```json
{
    "event": "call_disconnected",
    "caller": "<sip:5551234456@fritz.box>",
    "parsed_caller": "5551234456",
    "sip_account": 1
}
```

### `playback_done` for message (TTS)

```json
{
    "event": "playback_done",
    "caller": "<sip:5551234456@fritz.box>",
    "parsed_caller": "5551234456",
    "sip_account": 1,
    "type": "message",
    "message": "message that has been played"
}
```

### `playback_done` for audio file

```json
{
    "event": "playback_done",
    "caller": "<sip:5551234456@fritz.box>",
    "parsed_caller": "5551234456",
    "sip_account": 1,
    "type": "audio_file",
    "audio_file": "/config/audio/welcome.mp3"
}
```

### `ring_timeout`

```json
{
    "event": "ring_timeout",
    "caller": "<sip:5551234456@fritz.box>",
    "parsed_caller": "5551234456",
    "sip_account": 1
}
```

### `timeout`

```json
{
    "event": "timeout",
    "caller": "<sip:5551234456@fritz.box>",
    "parsed_caller": "5551234456",
    "sip_account": 1,
    "menu_id": "main"
}
```

## Examples

#### Trigger services through DTMF on an outgoing call

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: dial
        number: sip:**620@fritz.box
        menu:
            message: Press one to open the door, two to turn on light outside, three to play music
            choices:
                '1':
                    message: Door has been opened
                    action:
                        domain: switch
                        service: turn_on
                        entity_id: switch.open_front_door
                '2':
                    message: Light outside has been switched on
                    action:
                        domain: light
                        service: turn_on
                        entity_id: light.outside
                '3':
                    message: Play music
                    action:
                        domain: script
                        service: turn_on
                        entity_id: script.play_music_please
                        service_data:
                          variables:
                            song: 'Never gonna give you up'
```

#### Play a message without DTMF interaction on sip account 1

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: dial
        number: sip:**620@fritz.box
        ring_timeout: 15
        sip_account: 1
    menu:
        message: There's a burglar in da house.
```

#### Use PIN protection on outgoing call

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: dial
        number: sip:**620@fritz.box
        menu:
            message: Please enter your access code
            choices_are_pin: true
            timeout: 10
            choices:
                '1234':
                    id: owner
                    message: Welcome beautiful.
                    post_action: hangup
                '5432':
                    id: maintenance
                    message: Your entrance has been logged.
                    post_action: hangup
                'default':
                    id: wrong_code
                    message: Wrong code, please try again
                    post_action: return
                'timeout':
                    id: timeout
                    message: Bye.
                    post_action: hangup
```

All the examples are working also for incoming calls when you copy the `menu` part into your incoming configuration yaml.

## Troubleshooting

The first place to look is the log of the ha-sip add-on. There you can see individual SIP messages and the logs of
ha-sip itself (prefixed with "|").

## Example use-cases

One automation with the `dial` command when the doorbell was rung, and a second with `hangup` when the front door was opened, 
so I do not need to answer the call when not necessary.

I would like to hear from you in which scenario you are using ha-sip!

## Development

1. Create a virtual environment with pjsip and dependencies installed running `./build.sh create-venv` from the root directory of the repo
2. Activate virtual env with `source venv/bin/activate` (bash, might be different with other shells)
3. Copy `ha-sip/src/config.py` to `ha-sip/src/config_local.py` and replace the variable place-holders with your real configuration.

   `HA_BASE_URL` is something like "http://homeassistant.local:8123/api"
   
   The access token is created from http://homeassistant.local:8123/profile 
4. Run `./build.sh run-local` to run the add-on locally
5. Paste commands as json (without line-breaks) into stdin of the running add-on:

   Example: 
   ```json
   { "command": "dial", "number": "sip:**620@fritz.box", "menu": { "message": "Hello from ha-sip.", "language": "en" } }
   ```
