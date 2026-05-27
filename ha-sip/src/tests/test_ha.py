import unittest
import sys
from unittest.mock import MagicMock, patch

sys.modules.setdefault('websockets', MagicMock())

import ha


def make_ha_config(webhook_base_url=None):
    return ha.HaConfig(
        base_url='http://supervisor/core/api',
        websocket_url='ws://supervisor/core/websocket',
        token='token123',
        tts_config={
            'platform': None,
            'engine_id': None,
            'language': 'en',
            'voice': None,
            'debug_print': 'false',
        },
        webhook_id='default_hook',
        cache_dir=None,
        webhook_base_url=webhook_base_url,
    )


class HaWebhookTest(unittest.TestCase):
    def test_get_webhook_url_defaults_to_base_url(self):
        config = make_ha_config()
        self.assertEqual(config.get_webhook_url('abc'), 'http://homeassistant:8123/api/webhook/abc')

    def test_get_webhook_url_uses_webhook_base_url(self):
        config = make_ha_config(webhook_base_url='http://127.0.0.1:8123/api')
        self.assertEqual(config.get_webhook_url('abc'), 'http://127.0.0.1:8123/api/webhook/abc')

    @patch('ha.requests.post')
    def test_trigger_webhook_uses_dedicated_webhook_base_url(self, post_mock):
        response = MagicMock()
        response.ok = True
        response.status_code = 200
        response.content = b'ok'
        post_mock.return_value = response

        config = make_ha_config(webhook_base_url='http://127.0.0.1:8123/api')
        ha.trigger_webhook(config, {'event': 'incoming_call'})

        post_mock.assert_called_once_with(
            'http://127.0.0.1:8123/api/webhook/default_hook',
            json={'event': 'incoming_call'},
            headers={
                'Authorization': 'Bearer token123',
                'content-type': 'application/json',
            },
            timeout=8,
        )
