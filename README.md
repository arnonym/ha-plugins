# ha-sip
Home Assistant SIP/VoIP Gateway is a Home Assistant plug-in which allows the dialing and hanging up of phone 
numbers through a SIP end-point and triggering of services through dial tones (DTMF) after the call was answered.

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

## Installation

This add-on is for the Home Assistant OS or supervised installation methods mentioned in 
https://www.home-assistant.io/installation/. With that in place you can install this third-party plug-in like described in
https://www.home-assistant.io/common-tasks/os#installing-third-party-add-ons. The repository URL is 
`https://github.com/arnonym/ha-plugins`.

## Usage

After installation, the add-on is activated via the `hassio.addon_stdin` service in the action part of an automation. 
To be able to enter the full command, you must switch to YAML mode by clicking on the menu with the triple dot and 
selecting `Edit in YAML`.

# Use-cases

Personally I use them in two automations:

One with the `dial` command when the doorbell was rung, and a second with `hangup` when the front door was opened, 
so I do not need to answer the call when not necessary.

# Ideas

1. Handle incoming calls with PIN protection?
2. Go back to main menu with # key or something?
