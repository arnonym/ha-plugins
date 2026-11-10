#!/usr/bin/with-contenv bashio

export PORT="$(bashio::config 'sip_global.port')"
export LOG_LEVEL="$(bashio::config 'sip_global.log_level')"
export NAME_SERVER="$(bashio::config 'sip_global.name_server')"
export CACHE_DIR="$(bashio::config 'sip_global.cache_dir')"
export GLOBAL_OPTIONS="$(bashio::config 'sip_global.global_options')"

# `sip` is a list of accounts. Entry n (counting from 1) becomes the SIP<n>_* variables
# the app reads -- e.g. `id_uri` of the second entry becomes SIP2_ID_URI -- so an
# account's number, as used by commands, webhooks and sensors, is its position in the
# list. Values are quoted with @sh for the eval; null (an unset optional field) becomes
# empty, while false and 0 are kept as they are.
eval "$(jq -r '
    (.sip // [])
    | to_entries[]
    | (.key + 1) as $n
    | .value
    | to_entries[]
    | "export SIP\($n)_\(.key | ascii_upcase)=\((if .value == null then "" else .value | tostring end) | @sh)"
' /data/options.json)"

export TTS_ENGINE_ID="$(bashio::config 'tts.engine_id')"
export TTS_PLATFORM="$(bashio::config 'tts.platform')"
export TTS_LANGUAGE="$(bashio::config 'tts.language')"
export TTS_VOICE="$(bashio::config 'tts.voice')"
export TTS_DEBUG_PRINT="$(bashio::config 'tts.debug_print')"

export HA_WEBHOOK_ID="$(bashio::config 'webhook.id')"

export SENSOR_ENABLED="$(bashio::config 'sensors.enabled')"
export SENSOR_ENTITY_PREFIX="$(bashio::config 'sensors.entity_prefix')"

export HA_BASE_URL="http://supervisor/core/api"
export HA_WEBSOCKET_URL="ws://supervisor/core/websocket"
export HA_TOKEN="${SUPERVISOR_TOKEN}"

java -Djava.library.path=/usr/lib/pjsip-jni -jar /ha-sip/ha-sip.jar
