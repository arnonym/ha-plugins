# ha-sip
Home Assistant SIP Gateway is a Home Assistant plug-in which allows the dialing and hanging up of phone 
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

## Installation

This add-on is for the Home Assistant OS or supervised installation methods mentioned in 
https://www.home-assistant.io/installation/. With that in place you can install this third-party plug-in like described in
https://www.home-assistant.io/common-tasks/os#installing-third-party-add-ons. The repository URL is 
`https://github.com/arnonym/ha-plugins`.

### Use-cases

Personally I use them in two automations:

One with the `dial` command when the doorbell was rung, and a second with `hangup` when the front door was opened, 
so I do not need to answer the call when not necessary.
