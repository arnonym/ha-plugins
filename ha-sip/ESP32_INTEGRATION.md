# ESP32 SIP Bridge Integration

This document describes how to integrate ESP32 devices with the ha-sip project to enable SIP calling functionality.

## Overview

The ESP32 SIP Bridge enables bidirectional audio communication between ESP32 devices and SIP endpoints. This allows ESP32 devices with audio capabilities to make and receive SIP calls through the ha-sip gateway.

## Features

- Bidirectional audio bridge between ESP32 and SIP endpoints
- Support for ESP32 voice assistant functionality
- Audio streaming from SIP to ESP32 via HTTP
- Automatic call handling with ring tones
- Configurable audio parameters (sample rate, etc.)

## Configuration

### Environment Variables

Add the following variables to your `.env` file:

```bash
# Enable ESP32 functionality
ESP32_ENABLED=true

# ESP32 connection settings
ESP32_HOST=192.168.0.103          # IP address of your ESP32 device
ESP32_PORT=6053                   # ESPHome API port
ESP32_PASSWORD=                   # Password if required

# SIP settings for ESP32 calls
ESP32_SIP_TARGET_URI=sip:539@192.168.128.22:5061  # SIP URI to call
ESP32_CLOCK_RATE=16000            # Audio sample rate (Hz)
ESP32_STREAM_PORT=8991            # HTTP streaming port for audio
```

### Home Assistant Add-on Configuration

If using as a Home Assistant add-on, configure the `config.json` with the ESP32 section:

```json
{
  "options": {
    "esp32": {
      "enabled": true,
      "host": "192.168.0.103",
      "port": 6053,
      "password": "",
      "sip_target_uri": "sip:539@192.168.128.22:5061",
      "clock_rate": 16000,
      "stream_port": 8991
    }
  }
}
```

## ESP32 Setup Requirements

Your ESP32 device must be configured with:

1. ESPHome firmware with voice assistant support
2. A media player component for audio playback
3. Audio input/output capabilities (I2S, PDM, or similar)

Example ESPHome configuration:

```yaml
esphome:
  name: esp32-audio
  platform: ESP32
  board: esp32dev

# Enable voice assistant
voice_assistant:

# Media player for audio playback
media_player:

# I2S audio configuration
i2s_audio:
  i2s_dout_pin: GPIO26
  i2s_bclk_pin: GPIO27
  i2s_lrclk_pin: GPIO25

# Microphone input
microphone:
  - platform: i2s
    i2s_din_pin: GPIO14
    adc_type: external
    channel: right
    sample_rate: 16000
    bits_per_sample: 16bit

# Speaker output
speaker:
  - platform: i2s
    i2s_dout_pin: GPIO26
    mode: dac
```

## How It Works

1. When enabled, the ESP32 SIP bridge connects to your ESP32 device using the ESPHome API
2. The bridge establishes a SIP connection using the existing ha-sip configuration
3. When a call is initiated, the bridge:
   - Plays a ring tone on the ESP32 device
   - Establishes bidirectional audio streaming
   - Handles call state management
4. Audio from the SIP call is streamed to the ESP32 via HTTP
5. Audio from the ESP32 is forwarded to the SIP call in real-time

## Audio Streaming

The bridge creates an HTTP server on port 8991 (configurable) that serves:

- `/call.wav` - Ring tone for incoming calls
- `/busy.wav` - Busy tone when call is rejected
- `/stream_sip.wav` - Live audio stream from SIP to ESP32 during calls

## Call Flow

1. ESP32 device activates voice assistant
2. Bridge detects activation and initiates SIP call to target URI
3. Ring tone is played on ESP32 while waiting for answer
4. If call is answered, bidirectional audio bridge is established
5. Audio from SIP call is streamed to ESP32 speaker
6. Audio from ESP32 microphone is sent to SIP call
7. When call ends, bridge is torn down and audio streaming stops

## Troubleshooting

- Ensure ESP32 device is accessible on the network
- Verify ESPHome API is enabled and accessible
- Check that the media_player component is properly configured on ESP32
- Monitor logs for connection and audio streaming status
- Ensure network ports (SIP, ESPHome API, HTTP stream) are accessible

## Limitations

- Requires ESP32 with audio capabilities
- Audio quality depends on network conditions
- Only one simultaneous ESP32 call supported
- Requires proper audio input/output configuration on ESP32