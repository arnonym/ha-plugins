#!/usr/bin/with-contenv bashio

export PYTHONUNBUFFERED=1

sed -i -- 's~\$PORT~'"$(bashio::config 'sip.port')"'~g' /ha-sip/config.py
sed -i -- 's~\$ID_URI~'"$(bashio::config 'sip.id_uri')"'~g' /ha-sip/config.py
sed -i -- 's~\$REGISTRAR_URI~'"$(bashio::config 'sip.registrar_uri')"'~g' /ha-sip/config.py
sed -i -- 's~\$REALM~'"$(bashio::config 'sip.realm')"'~g' /ha-sip/config.py
sed -i -- 's~\$USER_NAME~'"$(bashio::config 'sip.user_name')"'~g' /ha-sip/config.py
sed -i -- 's~\$PASSWORD~'"$(bashio::config 'sip.password')"'~g' /ha-sip/config.py

sed -i -- 's~\$TTS_PLATFORM~'"$(bashio::config 'tts.platform')"'~g' /ha-sip/config.py
sed -i -- 's~\$WEBHOOK_ID~'"$(bashio::config 'webhook.id')"'~g' /ha-sip/config.py

sed -i -- 's~\$TOKEN~'"${SUPERVISOR_TOKEN}"'~g' /ha-sip/config.py

python3 /ha-sip/main.py
