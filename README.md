# ha-sip
Home Assistant SIP/VoIP Gateway is a Home Assistant add-on which 
- allows the dialing and hanging up of phone numbers through a SIP end-point and triggering of services through dial tones (DTMF)
  after the call was answered.
- listens for incoming calls and can trigger actions (the call is not picked up)
- accepting calls (optionally filtered by number)
- handle PIN input before triggering actions

You can use `dial` and `hangup` with the `hassio.addon_stdin` service to control outgoing calls in an action in 
your automation:

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: dial
        number: sip:**620@fritz.box
        sip_account: 1
```

If you have 2 sip accounts configured you can specify `sip_account` with the values `1` or `2`.

To hang up the call again:

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: hangup
        number: sip:**620@fritz.box
```

If there is already an outgoing call to the same number active, the request will be ignored.

To trigger services through DTMF you can define a menu on a call:

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: dial
        number: sip:**620@fritz.box
        menu:
            message: Press one to open the door, two to turn on light outside
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
```

To only play a message you can just specify `message` without any `choices`:

```yaml
service: hassio.addon_stdin
data_template:
    addon: c7744bff_ha-sip
    input:
        command: dial
        number: sip:**620@fritz.box
        ring_timeout: 15
    menu:
        message: There's a burglar in da house.
```

If you specify `ring_timeout` the call will be interrupted after that delay (in seconds). The default is 300.

You can also enable PIN mode, so the input of numbers is not interrupted at the first wrong input:

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

The `default` choice will be triggered if the entered PIN is not correct. The 'timeout' choice is activated after the specified `timeout` 
(you may have guessed). You can also use those in the standard (no PIN) mode.

In this example, an `id` is also given in the menu. After entering the correct pin a message will be sent 
to the webhook with the following content:

```json
{
    "event": "entered_menu",
    "menu_id": "owner"
}
```

Also, the `post_action` (can be `return`, `hangup` and `noop`) and `timeout` (number of seconds to wait for user input) options are used in this example. 

## Installation

This add-on is for the Home Assistant OS or supervised installation methods mentioned in 
https://www.home-assistant.io/installation/. With that in place you can install this third-party plug-in like described in
https://www.home-assistant.io/common-tasks/os#installing-third-party-add-ons. The repository URL is 
`https://github.com/arnonym/ha-plugins`.

After that you need to configure your SIP account(s), TTS parameters and webhook ID. The default configuration looks like this:

```yaml
sip_global:
    port: 5060
sip:
    enabled: true
    registrar_uri: sip:fritz.box
    id_uri: sip:homeassistant@fritz.box
    realm: '*'
    user_name: homeassistant
    password: secure
    answer_mode: listen
    incoming_call_file: ""
sip_2:
    enabled: false
    registrar_uri: sip:fritz.box
    id_uri: sip:anotheruser@fritz.box
    realm: '*'
    user_name: anotheruser
    password: secret
    answer_mode: listen
    incoming_call_file: ""
tts:
    platform: google_translate
    language: en
webhook:
    id: sip_call_webhook_id
```

## Usage

### Outgoing calls

Outgoing calls are made via the `hassio.addon_stdin` service in the action part of an automation. 
To be able to enter the full command, you must switch to YAML mode by clicking on the menu with the triple dot and 
selecting `Edit in YAML`. See examples above.

### Incoming calls

In `listen` mode you can trigger an automation through the [Webhook trigger type](https://www.home-assistant.io/docs/automation/trigger/#webhook-trigger). 
The webhook ID must match the ID set in the configuration. You can get the caller from `{{trigger.json.caller}}` for usage in e.g. the action
of your automation. If you also use the menu ID webhook you also need to check for `{{ trigger.json.event == "incoming_call" }}` e.g. in a "Choose"
action type.

In `accept` mode you can additionally make ha-sip to accept the call. For this you can define a menu per SIP account. Put a config file 
into your `config` directory of your home-assistant installation (e.g. use the samba add-on to access that directory). 
This could look like this:

```yaml
allowed_numbers:
    - 5551234456
    - 5559876543
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

After that you can set `incoming_call_file` in the add-on configuration to `/config/incoming-sip1.yaml` (if you named it like that).

If you remove the `allowed_numbers` section all calls are answered.

# Use-cases

Personally I use them in two automations:

One with the `dial` command when the doorbell was rung, and a second with `hangup` when the front door was opened, 
so I do not need to answer the call when not necessary.

