"""
ESP32 Configuration Module
This module provides configuration options for the ESP32 SIP bridge functionality.
"""

import os
from typing import Optional


class ESP32Config:
    """
    Configuration class for ESP32 SIP bridge
    """
    def __init__(self):
        # ESP32 connection settings
        self.esp_host = os.getenv('ESP_HOST', '192.168.0.103')
        self.esp_port = int(os.getenv('ESP_PORT', 6053))
        self.esp_password = os.getenv('ESP_PASSWORD', '')
        
        # SIP target settings
        self.sip_target_uri = os.getenv('SIP_TARGET_URI', 'sip:539@192.168.128.22:5061')
        
        # Audio settings
        self.esp_clock_rate = int(os.getenv('ESP_CLOCK_RATE', 16000))
        
        # HTTP streaming settings
        self.stream_port = int(os.getenv('STREAM_PORT', 8991))
        self.call_stream_url = os.getenv('CALL_STREAM_URL', f'http://192.168.0.106:{self.stream_port}/call.wav')
        self.busy_stream_url = os.getenv('BUSY_STREAM_URL', f'http://192.168.0.106:{self.stream_port}/busy.wav')
        
        # ESP32 media player settings
        self.media_player_object_id = os.getenv('ESP_MEDIA_PLAYER_ID', 'media_player')
        
        # Call settings
        self.ring_timeout = int(os.getenv('ESP_RING_TIMEOUT', 30))
        self.call_retry_interval = int(os.getenv('ESP_CALL_RETRY_INTERVAL', 22))
        
        # Queue settings
        self.queue_max_size = int(os.getenv('ESP_QUEUE_MAX_SIZE', 2000))
        
        # Logging settings
        self.enable_audio_logging = os.getenv('ESP_ENABLE_AUDIO_LOGGING', 'true').lower() == 'true'
        self.audio_log_interval = int(os.getenv('ESP_AUDIO_LOG_INTERVAL', 100))
        
    def get_esp_connection_params(self):
        """Returns ESP32 connection parameters"""
        return {
            'host': self.esp_host,
            'port': self.esp_port,
            'password': self.esp_password
        }
    
    def get_sip_params(self):
        """Returns SIP connection parameters"""
        return {
            'target_uri': self.sip_target_uri,
            'clock_rate': self.esp_clock_rate
        }
    
    def get_streaming_params(self):
        """Returns streaming parameters"""
        return {
            'port': self.stream_port,
            'call_stream_url': self.call_stream_url,
            'busy_stream_url': self.busy_stream_url
        }
    
    def get_call_params(self):
        """Returns call parameters"""
        return {
            'ring_timeout': self.ring_timeout,
            'retry_interval': self.call_retry_interval
        }


# Global instance
esp32_config = ESP32Config()


def get_esp32_config() -> ESP32Config:
    """Returns the global ESP32 configuration instance"""
    return esp32_config