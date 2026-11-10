#!/usr/bin/env bash

java -version

# if the config file exists, the plugin is probably running inside home-assistant OS
# and is getting configuration from there
HOME_ASSISTANT_CONFIG_FILE=/data/options.json
if test -f "$HOME_ASSISTANT_CONFIG_FILE"; then
    echo "Getting config options from home-assistant OS."
    /run-in-ha.sh
else
    echo "Running standalone version of ha-sip."
    /run-standalone.sh
fi
