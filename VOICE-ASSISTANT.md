# Use ha-sip to talk to your Home Assistant AI

This guide shows you how to set up ha-sip to enable voice conversations with your Home Assistant AI assistant through phone calls. Essentially dropping the Grandstream HT801 / HT802 requirement.

## Overview

By combining ha-sip's phone capabilities with Home Assistant's AI conversation features, you can:
- Call your home phone and talk directly to your Home Assistant AI
- Be called by Home Assistant if an automation is being triggered
- Ask questions and get spoken responses
- Control your smart home devices using natural voice commands
- Be called by home assistant

## Prerequisites

### 1. ha-sip add-on installed and configured with at least one working SIP account

 see [README.md](README.md)

### 2. Home Assistant voice assistant pipeline with speech to text, conversation agent and text to speech.

[![Open your Home Assistant instance and show your voice assistants.](https://my.home-assistant.io/badges/voice_assistants.svg)](https://my.home-assistant.io/redirect/voice_assistants/)

### 3. Home Assistant Voice over IP integration enabled.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=voip)

- In the configuration of the integration name a SIP username and a SIP port which is different from ha-sip, for example 5070


## Basic Setup

### 0. Register your ha-sip account as phone to the VOIP integration of home assistant

Create a small script to initiate a call to the VOIP integration.

Example:
```yaml
  sequence:
    - data:
        addon: c7744bff_ha-sip
        input:
          command: dial
          number: sip:[Your SIP username]@[Your home assistant ip address]:[Your SIP port]
          ring_timeout: 15
          sip_account: 1
          wait_for_audio_to_finish: true
          menu:
            message: Hello
            post_action: hangup
      action: hassio.addon_stdin
  alias: Initialize Voip
  description: ""
```
After you executed the script a new device becomes visible in the voice over ip integration. There you need to enable the swtich to allow "incoming calls".

### 1. Configure Incoming Calls for AI Conversations

Create two automations. One for accepting and briding the call to your voice assistant. A second to hangup the bridged call after you hangup your phone.

Example:
```yaml
  alias: Voip incoming call to Home Assistant AI
  description: ""
  triggers:
    - trigger: webhook
      allowed_methods:
        - POST
        - PUT
      local_only: true
      webhook_id: sip_call_webhook_id
  conditions:
    - condition: template
      value_template: >-
        {{trigger.json.parsed_caller == answer_for and trigger.json.event ==
        "incoming_call" }}
  actions:
    - action: hassio.addon_stdin
      data:
        addon: "{{ha_sip_slug}}"
        input:
          command: answer
          number: "{{ trigger.json.internal_id }}"
          webhook_to_call:
            call_disconnected: hangup_voip_assistant
          menu:
            post_action: noop
    - data:
        addon: "{{ha_sip_slug}}"
        input:
          command: dial
          number: "{{ ha_assistant_sip_url }}"
          ring_timeout: 30
          webhook_to_call:
            call_established: incoming_voip_call_established
      action: hassio.addon_stdin
    - wait_for_trigger:
        - trigger: webhook
          allowed_methods:
            - POST
            - PUT
          local_only: true
          webhook_id: incoming_voip_call_established
      timeout:
        hours: 0
        minutes: 0
        seconds: 10
        milliseconds: 0
    - data:
        addon: "{{ha_sip_slug}}"
        input:
          command: bridge_audio
          number: "{{ trigger.json.internal_id }}"
          bridge_to: "{{ ha_assistant_sip_url }}"
      action: hassio.addon_stdin
  variables:
    ha_sip_slug: "c7744bff_ha-sip"
    answer_for: "012346789"
    ha_assistant_sip_url: sip:[Your SIP username]@[Your home assistant ip address]:[Your SIP port]
  mode: single
```

```yaml
  alias: "Voip incoming call to Home Assistant AI dropped"
  description: ""
  triggers:
    - trigger: webhook
      allowed_methods:
        - POST
        - PUT
      local_only: true
      webhook_id: hangup_voip_assistant
  conditions: []
  actions:
    - action: hassio.addon_stdin
      data:
        addon: "{{ha_sip_slug}}"
        input:
          command: hangup
          number: "{{ ha_assistant_sip_url }}"
  variables:
    ha_sip_slug: "c7744bff_ha-sip"
    answer_for: "012346789"
    ha_assistant_sip_url: sip:[Your SIP username]@[Your home assistant ip address]:[Your SIP port]
  mode: single

```

### 2. Script for outgoing calls of your Voice Assistant

With this script you will be able to call your phone and bridge it to your voice assistant. We will reuse the hangup automation from above to cancel the bridged call after the phone call is hangup.

Example:
```yaml
  alias: Bridge HA VoIP to Phone
  sequence:
    - data:
        addon: "{{ha_sip_slug}}"
        input:
          command: dial
          number: "{{call_to}}"
          webhook_to_call:
            call_established: phone_connected
            call_disconnected: hangup_voip_assistant
          ring_timeout: 30
      action: hassio.addon_stdin
    - wait_for_trigger:
        - webhook_id: phone_connected
          trigger: webhook
          allowed_methods:
            - POST
            - PUT
          local_only: true
      timeout: 30
      continue_on_timeout: false
    - data:
        addon: "{{ha_sip_slug}}"
        input:
          command: dial
          number: "{{ha_assistant_sip_url}}"
          webhook_to_call:
            call_established: ha_voip_connected
          ring_timeout: 30
          wait_for_audio_to_finish: true
          menu:
            message: Hello
      action: hassio.addon_stdin
    - data:
        addon: "{{ha_sip_slug}}"
        input:
          command: bridge_audio
          number: "{{call_to}}"
          bridge_to: "{{ha_assistant_sip_url}}"
      action: hassio.addon_stdin
  variables:
    ha_sip_slug: "c7744bff_ha-sip"
    call_to: "sip:012346789@sip-provider"
    ha_assistant_sip_url: sip:[Your SIP username]@[Your home assistant ip address]:[Your SIP port]
  mode: single
  description: ""

```