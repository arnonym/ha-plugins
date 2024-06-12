#!/usr/bin/with-contenv bashio

export PYTHONUNBUFFERED=1

# if the config file exists, the plugin is probably running inside home-assistant OS
# and is getting configuration from there
HOME_ASSISTANT_CONFIG_FILE=/data/options.json
if test -f "$HOME_ASSISTANT_CONFIG_FILE"; then
    echo "Getting config options from home-assistant OS."
    export PORT="$(bashio::config 'sip_global.port')"
    export LOG_LEVEL="$(bashio::config 'sip_global.log_level')"
    export NAME_SERVER="$(bashio::config 'sip_global.name_server')"
    export CACHE_DIR="$(bashio::config 'sip_global.cache_dir')"

    export SIP1_ENABLED="$(bashio::config 'sip.enabled')"
    export SIP1_ID_URI="$(bashio::config 'sip.id_uri')"
    export SIP1_REGISTRAR_URI="$(bashio::config 'sip.registrar_uri')"
    export SIP1_REALM="$(bashio::config 'sip.realm')"
    export SIP1_USER_NAME="$(bashio::config 'sip.user_name')"
    export SIP1_PASSWORD="$(bashio::config 'sip.password')"
    export SIP1_ANSWER_MODE="$(bashio::config 'sip.answer_mode')"
    export SIP1_SETTLE_TIME="$(bashio::config 'sip.settle_time')"
    export SIP1_INCOMING_CALL_FILE="$(bashio::config 'sip.incoming_call_file')"

    export SIP2_ENABLED="$(bashio::config 'sip_2.enabled')"
    export SIP2_ID_URI="$(bashio::config 'sip_2.id_uri')"
    export SIP2_REGISTRAR_URI="$(bashio::config 'sip_2.registrar_uri')"
    export SIP2_REALM="$(bashio::config 'sip_2.realm')"
    export SIP2_USER_NAME="$(bashio::config 'sip_2.user_name')"
    export SIP2_PASSWORD="$(bashio::config 'sip_2.password')"
    export SIP2_ANSWER_MODE="$(bashio::config 'sip_2.answer_mode')"
    export SIP2_SETTLE_TIME="$(bashio::config 'sip_2.settle_time')"
    export SIP2_INCOMING_CALL_FILE="$(bashio::config 'sip_2.incoming_call_file')"

    export SIP3_ENABLED="$(bashio::config 'sip_3.enabled')"
    export SIP3_ID_URI="$(bashio::config 'sip_3.id_uri')"
    export SIP3_REGISTRAR_URI="$(bashio::config 'sip_3.registrar_uri')"
    export SIP3_REALM="$(bashio::config 'sip_3.realm')"
    export SIP3_USER_NAME="$(bashio::config 'sip_3.user_name')"
    export SIP3_PASSWORD="$(bashio::config 'sip_3.password')"
    export SIP3_ANSWER_MODE="$(bashio::config 'sip_3.answer_mode')"
    export SIP3_SETTLE_TIME="$(bashio::config 'sip_3.settle_time')"
    export SIP3_INCOMING_CALL_FILE="$(bashio::config 'sip_3.incoming_call_file')"

    export TTS_PLATFORM="$(bashio::config 'tts.platform')"
    export TTS_LANGUAGE="$(bashio::config 'tts.language')"
    export HA_WEBHOOK_ID="$(bashio::config 'webhook.id')"

    export HA_BASE_URL="http://supervisor/core/api"
    export HA_TOKEN="${SUPERVISOR_TOKEN}"
else
    echo "Running in stand-alone mode."
fi

python3 --version
python3 /ha-sip/main.py
