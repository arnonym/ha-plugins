#!/usr/bin/with-contenv bashio

export PYTHONUNBUFFERED=1

sed -i -- 's~\$PORT~'"$(bashio::config 'port')"'~g' ha-sip/config.py
sed -i -- 's~\$ID_URI~'"$(bashio::config 'id_uri')"'~g' ha-sip/config.py
sed -i -- 's~\$REGISTRAR_URI~'"$(bashio::config 'registrar_uri')"'~g' ha-sip/config.py
sed -i -- 's~\$REALM~'"$(bashio::config 'realm')"'~g' ha-sip/config.py
sed -i -- 's~\$USER_NAME~'"$(bashio::config 'user_name')"'~g' ha-sip/config.py
sed -i -- 's~\$PASSWORD~'"$(bashio::config 'password')"'~g' ha-sip/config.py

python3 /ha-sip/main.py
