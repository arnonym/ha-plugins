# ha-sip
Home Assistant SIP/VoIP Gateway is a Home Assistant add-on which 
- allows the dialing and hanging up of phone numbers through a SIP end-point and triggering of services through dial tones (DTMF)
  after the call was answered.
- listens for incoming calls and can trigger actions (the call is not picked up)

You can use `dial` and `hangup` with the `hassio.addon_stdin` service to control outgoing calls in an action in 
your automation:

```yaml
service: hassio.addon_stdin
data_template:
  addon: c7744bff_ha-sip
  input:
    command: dial
    number: sip:**620@fritz.box
```

or to hang up the call again:

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
```

To only play a message you can just specify `message` without any `choices`:

```yaml
service: hassio.addon_stdin
data_template:
  addon: c7744bff_ha-sip
  input:
    command: dial
    number: sip:**620@fritz.box
    menu:
      message: There's a burglar in da house.
```

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
```

In this example, an `id` is also given in the menu. After entering the correct pin a message will be sent 
to the webhook with the following content:

```json
{
    "event": "entered_menu",
    "menu_id": "owner"
}
```

Also, the `post_action` and `timeout` options are used in this example. 

## Installation

This add-on is for the Home Assistant OS or supervised installation methods mentioned in 
https://www.home-assistant.io/installation/. With that in place you can install this third-party plug-in like described in
https://www.home-assistant.io/common-tasks/os#installing-third-party-add-ons. The repository URL is 
`https://github.com/arnonym/ha-plugins`.

After that you need to configure your SIP account, TTS parameters and webhook ID. The default configuration looks like this:

```yaml
sip:
  registrar_uri: sip:fritz.box
  port: 5060
  id_uri: sip:homeassistant@fritz.box
  realm: '*'
  user_name: homeassistant
  password: secure
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

You can trigger an automation through the [Webhook trigger type](https://www.home-assistant.io/docs/automation/trigger/#webhook-trigger). 
The webhook ID must match the ID set in the configuration. You can get the caller from `{{trigger.json.caller}}` for usage in e.g. the action
of your automation. If you also use the menu ID webhook you also need to check for `{{ trigger.json.event == "incoming_call" }}` e.g. in a "Choose"
action type.

# Use-cases

Personally I use them in two automations:

One with the `dial` command when the doorbell was rung, and a second with `hangup` when the front door was opened, 
so I do not need to answer the call when not necessary.

# Ideas

1. Handle incoming calls with PIN protection?
2. Go back to main menu with # key or something?
