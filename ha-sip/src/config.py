import os

COMMAND_SOURCE = os.environ.get('COMMAND_SOURCE', 'stdin')

PORT = os.environ.get('PORT', '')
LOG_LEVEL = os.environ.get('LOG_LEVEL', '')
NAME_SERVER = os.environ.get('NAME_SERVER', '')

SIP1_ENABLED = os.environ.get('SIP1_ENABLED', '')
SIP1_ID_URI = os.environ.get('SIP1_ID_URI', '')
SIP1_REGISTRAR_URI = os.environ.get('SIP1_REGISTRAR_URI', '')
SIP1_REALM = os.environ.get('SIP1_REALM', '')
SIP1_USER_NAME = os.environ.get('SIP1_USER_NAME', '')
SIP1_PASSWORD = os.environ.get('SIP1_PASSWORD', '')
SIP1_ANSWER_MODE = os.environ.get('SIP1_ANSWER_MODE', '')
SIP1_SETTLE_TIME = os.environ.get('SIP1_SETTLE_TIME', '')
SIP1_INCOMING_CALL_FILE = os.environ.get('SIP1_INCOMING_CALL_FILE', '')

SIP2_ENABLED = os.environ.get('SIP2_ENABLED', '')
SIP2_ID_URI = os.environ.get('SIP2_ID_URI', '')
SIP2_REGISTRAR_URI = os.environ.get('SIP2_REGISTRAR_URI', '')
SIP2_REALM = os.environ.get('SIP2_REALM', '')
SIP2_USER_NAME = os.environ.get('SIP2_USER_NAME', '')
SIP2_PASSWORD = os.environ.get('SIP2_PASSWORD', '')
SIP2_ANSWER_MODE = os.environ.get('SIP2_ANSWER_MODE', '')
SIP2_SETTLE_TIME = os.environ.get('SIP2_SETTLE_TIME', '')
SIP2_INCOMING_CALL_FILE = os.environ.get('SIP2_INCOMING_CALL_FILE', '')

SIP3_ENABLED = os.environ.get('SIP3_ENABLED', '')
SIP3_ID_URI = os.environ.get('SIP3_ID_URI', '')
SIP3_REGISTRAR_URI = os.environ.get('SIP3_REGISTRAR_URI', '')
SIP3_REALM = os.environ.get('SIP3_REALM', '')
SIP3_USER_NAME = os.environ.get('SIP3_USER_NAME', '')
SIP3_PASSWORD = os.environ.get('SIP3_PASSWORD', '')
SIP3_ANSWER_MODE = os.environ.get('SIP3_ANSWER_MODE', '')
SIP3_SETTLE_TIME = os.environ.get('SIP3_SETTLE_TIME', '')
SIP3_INCOMING_CALL_FILE = os.environ.get('SIP3_INCOMING_CALL_FILE', '')

TTS_PLATFORM = os.environ.get('TTS_PLATFORM', '')
TTS_LANGUAGE = os.environ.get('TTS_LANGUAGE', '')

HA_BASE_URL = os.environ.get('HA_BASE_URL', '')
HA_TOKEN = os.environ.get('HA_TOKEN', '')
HA_WEBHOOK_ID = os.environ.get('HA_WEBHOOK_ID', '')
