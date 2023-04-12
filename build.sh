#!/usr/bin/env bash

export TMP_URL=~/tmp/ha-plugins-next
export REPO_URL=https://github.com/topic2k/ha-plugins
export NEXT_REPO_URL=https://github.com/topic2k/ha-plugins-next
export NEXT_REPO_SSH=git@github.com:topic2k/ha-plugins.git

function check_environment () {
    if [ -z "$DOCKER_HUB_PASSWORD" ] || [ -z "$DOCKER_HUB_USER" ]
    then
        echo "\$DOCKER_HUB_PASSWORD must be set"
        exit 1
    fi
}

case "$1" in
    build-next)
        check_environment
        echo "Building on next repo (aarch64 only)..."
        rm -rf $TMP_URL
        git clone -b next $REPO_URL $TMP_URL
        REPO_JSON=$TMP_URL/repository.json
        contents="$(jq --indent 4 '.name = "Home Assistant addons by Arne Gellhaus (next version) (forked by '$DOCKER_HUB_USER')"' $REPO_JSON)" && echo -E "${contents}" > $REPO_JSON
        contents="$(jq --indent 4 '.url = env.NEXT_REPO_URL' $REPO_JSON)" && echo -E "${contents}" > $REPO_JSON
        CONFIG_JSON=$TMP_URL/ha-sip/config.json
        contents="$(jq --indent 4 '.name = "ha-sip-next"' $CONFIG_JSON)" && echo -E "${contents}" > $CONFIG_JSON
        contents="$(jq --indent 4 '.slug = "ha-sip-next"' $CONFIG_JSON)" && echo -E "${contents}" > $CONFIG_JSON
        contents="$(jq --indent 4 '.url = env.NEXT_REPO_URL' $CONFIG_JSON)" && echo -E "${contents}" > $CONFIG_JSON
        contents="$(jq --indent 4 '.description = "Home-Assistant SIP Gateway (next version)"' $CONFIG_JSON)" && echo -E "${contents}" > $CONFIG_JSON
        contents="$(jq --indent 4 '.image = "'$DOCKER_HUB_USER'/{arch}-ha-sip-next"' $CONFIG_JSON)" && echo -E "${contents}" > $CONFIG_JSON
        if [ -z "$2" ]
          then
            echo "Don't overwrite version."
          else
            echo "Set version to $2"
            export OVERWRITE_VERSION=$2
            contents="$(jq --indent 4 '.version = env.OVERWRITE_VERSION' $CONFIG_JSON)" && echo -E "${contents}" > $CONFIG_JSON
        fi
        cd $TMP_URL || exit
        git commit -a -m "Changes for next repository."
        git remote set-url origin $NEXT_REPO_SSH
        git push --force
        docker run \
            --rm --privileged -v /var/run/docker.sock:/var/run/docker.sock:ro \
            homeassistant/amd64-builder:dev \
            --no-cache --aarch64 \
            -t ha-sip -r $NEXT_REPO_URL -b next \
            --docker-user "$DOCKER_HUB_USER" --docker-password "$DOCKER_HUB_PASSWORD"
        ;;
    build)
        check_environment
        echo "Building prod (all archs)..."
        docker run \
            --rm --privileged -v /var/run/docker.sock:/var/run/docker.sock:ro \
            homeassistant/amd64-builder:dev \
            --no-cache --all \
            -t ha-sip -r $REPO_URL -b next \
            --docker-user "$DOCKER_HUB_USER" --docker-password "$DOCKER_HUB_PASSWORD"
        ;;
    update)
        echo "Updating builder..."
        docker pull homeassistant/amd64-builder:dev
        ;;
    test)
        echo "Running type-check..."
        pyright ha-sip
        ;;
    create-venv)
        SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
        rm -rf $SCRIPT_DIR/venv $SCRIPT_DIR/deps
        python3 -m venv $SCRIPT_DIR/venv
        source $SCRIPT_DIR/venv/bin/activate
        pip3 install pydub requests PyYAML typing_extensions
        mkdir $SCRIPT_DIR/deps
        cd $SCRIPT_DIR/deps || exit
        git clone --depth 1 --branch 2.13 https://github.com/pjsip/pjproject.git
        cd pjproject || exit
        ./configure --enable-shared --disable-libwebrtc --prefix $SCRIPT_DIR/venv
        make
        make dep
        make install
        cd pjsip-apps/src/swig || exit
        make python
        cd python || exit
        python setup.py install
        ;;
    *)
        echo "Supply one of 'build-next', 'build', 'test', 'update' or 'create-venv'"
        exit 1
        ;;
esac
