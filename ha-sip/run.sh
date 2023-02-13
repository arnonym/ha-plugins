#!/usr/bin/with-contenv bashio

export PYTHONUNBUFFERED=1

sed -i -- 's~\$PORT~'"$(bashio::config 'sip_global.port')"'~g' /ha-sip/config.py
sed -i -- 's~\$LOG_LEVEL~'"$(bashio::config 'sip_global.log_level')"'~g' /ha-sip/config.py
sed -i -- 's~\$NAME_SERVER~'"$(bashio::config 'sip_global.name_server')"'~g' /ha-sip/config.py

sed -i -- 's~\$SIP1_ENABLED~'"$(bashio::config 'sip.enabled')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP1_ID_URI~'"$(bashio::config 'sip.id_uri')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP1_REGISTRAR_URI~'"$(bashio::config 'sip.registrar_uri')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP1_REALM~'"$(bashio::config 'sip.realm')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP1_USER_NAME~'"$(bashio::config 'sip.user_name')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP1_PASSWORD~'"$(bashio::config 'sip.password')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP1_ANSWER_MODE~'"$(bashio::config 'sip.answer_mode')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP1_SETTLE_TIME~'"$(bashio::config 'sip.settle_time')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP1_INCOMING_CALL_FILE~'"$(bashio::config 'sip.incoming_call_file')"'~g' /ha-sip/config.py

sed -i -- 's~\$SIP2_ENABLED~'"$(bashio::config 'sip_2.enabled')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP2_ID_URI~'"$(bashio::config 'sip_2.id_uri')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP2_REGISTRAR_URI~'"$(bashio::config 'sip_2.registrar_uri')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP2_REALM~'"$(bashio::config 'sip_2.realm')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP2_USER_NAME~'"$(bashio::config 'sip_2.user_name')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP2_PASSWORD~'"$(bashio::config 'sip_2.password')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP2_ANSWER_MODE~'"$(bashio::config 'sip_2.answer_mode')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP2_SETTLE_TIME~'"$(bashio::config 'sip_2.settle_time')"'~g' /ha-sip/config.py
sed -i -- 's~\$SIP2_INCOMING_CALL_FILE~'"$(bashio::config 'sip_2.incoming_call_file')"'~g' /ha-sip/config.py

sed -i -- 's~\$TTS_PLATFORM~'"$(bashio::config 'tts.platform')"'~g' /ha-sip/config.py
sed -i -- 's~\$TTS_LANGUAGE~'"$(bashio::config 'tts.language')"'~g' /ha-sip/config.py
sed -i -- 's~\$HA_WEBHOOK_ID~'"$(bashio::config 'webhook.id')"'~g' /ha-sip/config.py

sed -i -- 's~\$TOKEN~'"${SUPERVISOR_TOKEN}"'~g' /ha-sip/config.py

python3 --version
python3 /ha-sip/main.py
