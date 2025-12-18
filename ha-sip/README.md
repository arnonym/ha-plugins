# ha-sip

Home Assistant SIP Gateway with ESP32 support

## Overview

ha-sip is a Home Assistant add-on that provides SIP gateway functionality. It allows you to connect SIP phones, PBX systems, and other SIP devices to Home Assistant for advanced automation and voice control.

This version includes additional support for ESP32 devices, enabling bidirectional audio communication between ESP32 devices and SIP endpoints.

## Features

- SIP client functionality for Home Assistant integration
- Support for multiple SIP accounts
- Voice assistant integration
- Audio streaming capabilities
- **NEW: ESP32 SIP bridge functionality**
  - Bidirectional audio bridge between ESP32 and SIP endpoints
  - Support for ESP32 voice assistant functionality
  - Audio streaming from SIP to ESP32 via HTTP
  - Automatic call handling with ring tones

## Installation

### As Home Assistant Add-on

1. Add this repository to your Home Assistant add-on store
2. Install the ha-sip add-on
3. Configure the settings according to your SIP provider
4. Enable ESP32 functionality if needed (see ESP32 section below)

### Standalone Usage

1. Clone this repository
2. Install dependencies (see Dockerfile for details)
3. Configure environment variables
4. Run with `python src/main.py`

## Configuration

### Basic SIP Configuration

Configure your SIP settings in the add-on configuration or via environment variables:

```yaml
sip_global:
  port: 5060
  log_level: 5
  name_server: ""
  cache_dir: ""
  global_options: ""

sip:
  enabled: true
  registrar_uri: "sip:your-voip-provider.com"
  id_uri: "sip:username@your-voip-provider.com"
  realm: "*"
  user_name: "username"
  password: "password"
  answer_mode: "listen"
  settle_time: 1
  incoming_call_file: ""
  options: ""
```

### ESP32 Configuration

To enable ESP32 functionality, configure the ESP32 section:

```yaml
esp32:
  enabled: true
  host: "192.168.0.103"  # IP address of your ESP32 device
  port: 6053              # ESPHome API port
  password: ""            # Password if required
  sip_target_uri: "sip:539@192.168.128.22:5061"  # SIP URI to call
  clock_rate: 16000       # Audio sample rate (Hz)
  stream_port: 8991       # HTTP streaming port for audio
```

## ESP32 Integration

For detailed ESP32 setup instructions, see [ESP32_INTEGRATION.md](ESP32_INTEGRATION.md)

### Requirements

- ESP32 device with audio capabilities (I2S, PDM, or similar)
- ESPHome firmware with voice assistant support
- Media player component for audio playback
- Microphone for audio input

### Setup Process

1. Configure your ESP32 with ESPHome with voice assistant and media player components
2. Configure ha-sip with ESP32 settings
3. Start the add-on
4. The ESP32 SIP bridge will automatically connect to your device
5. When voice assistant activates on ESP32, a SIP call will be initiated

## Usage

### Basic Usage

Once configured, ha-sip will:
- Register with your SIP provider
- Listen for incoming calls
- Execute Home Assistant webhooks based on call events
- Process outgoing calls as configured

### ESP32 Usage

With ESP32 enabled:
- When ESP32 voice assistant activates, a SIP call is automatically initiated
- Audio from the SIP call is streamed to the ESP32 device
- Audio from ESP32 microphone is sent to the SIP call
- Ring tones and busy signals are played on the ESP32 device

## Troubleshooting

- Check that SIP settings are correct for your provider
- Verify network connectivity for all ports
- Enable debug logging to see detailed information
- For ESP32 issues, ensure ESPHome API is accessible and device has proper audio configuration

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the terms specified in the original repository.