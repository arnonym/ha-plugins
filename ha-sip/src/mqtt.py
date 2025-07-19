import json
import os
import time

import paho.mqtt.client as paho_mqtt
from paho.mqtt.enums import CallbackAPIVersion

from log import log
from command_client import CommandClient
from command_handler import CommandHandler
import utils
import ha


class MqttClient:
    def __init__(
        self,
        broker_address: str,
        port: int,
        username: str,
        password: str,
        topic: str,
        topic_state: str,
        command_handler: CommandHandler
    ):
        self.client = paho_mqtt.Client(CallbackAPIVersion.VERSION2)
        self.broker_address = broker_address
        self.port = port
        self.username = username
        self.password = password
        self.topic = topic
        self.topic_state = topic_state
        self.command_handler = command_handler
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.client.username_pw_set(self.username, self.password)

    def is_connected(self):
        return self.client.is_connected()

    def reconnect(self):
        self.client.reconnect()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        log(None, 'Connected to mqtt broker with result code %s' % reason_code)
        self.client.subscribe(self.topic)

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        log(None, 'Lost connection to mqtt broker with reason code %s' % reason_code)

    def on_message(self, client, userdata, msg):
        log(None, 'Received mqtt payload: %s on topic: %s' % (msg.payload, msg.topic))
        command_list = CommandClient.list_to_json([msg.payload])
        for command in command_list:
            self.command_handler.handle_command(command, None)

    def connect(self):
        self.client.connect(self.broker_address, self.port, 60)

    def handle(self):
        if not self.client.is_connected():
            try:
                self.client.reconnect()
            except:
                log(None, 'Reconnect to mqtt broker failed. Trying again....')
                time.sleep(1)
        self.client.loop()

    def send_event(self, event: ha.WebhookEvent):
        if not self.client.is_connected():
            log(None, 'Cannot send message, mqtt client is not connected')
            return
        log(None, 'Sending mqtt message: %s to topic: %s' % (event, self.topic))
        self.client.publish(self.topic_state, json.dumps(event))

def create_client_and_connect(command_handler: CommandHandler) -> MqttClient:
    broker_address = os.environ.get('BROKER_ADDRESS', '')
    port = utils.convert_to_int(os.environ.get('BROKER_PORT', '1833'))
    mqtt_username = os.environ.get('BROKER_USERNAME', '')
    mqtt_password = os.environ.get('BROKER_PASSWORD', '')
    topic = os.environ.get('MQTT_TOPIC', 'hasip/execute')
    topic_state = os.environ.get('MQTT_STATE_TOPIC', 'hasip/state')
    client = MqttClient(broker_address, port, mqtt_username, mqtt_password, topic, topic_state, command_handler)
    client.connect()
    return client
