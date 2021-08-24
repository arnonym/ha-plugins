# ha-sip
Home Assistant SIP Gateway is a Home Assistant plug-in which allows the dialing and hanging up of phone 
numbers through a SIP end-point.

You can use `dial` and `hangup` with the `hassio.addon_stdin` service to control outgoing calls:

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

### Use-cases

Personally I use them in two automations:

One with the `dial` command when the doorbell was rung, and a second with `hangup` when the front door was opened.
