#!/usr/bin/env bash

export TMP_URL=~/tmp/ha-plugins-next

if [ -z "$REPO_URL" ]; then
  export REPO_URL=https://github.com/arnonym/ha-plugins
fi

export NEXT_REPO_URL=https://github.com/arnonym/ha-plugins-next
export NEXT_REPO_SSH=git@github.com:arnonym/ha-plugins-next.git

if [ -z "$DOCKER_HUB_PASSWORD" ]
  then
    echo "\$DOCKER_HUB_PASSWORD must be set"
    exit 1
fi

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)

case "$1" in
    update-next-repo)
        echo "Updating next repo..."
        rm -rf $TMP_URL
        git clone -b next $REPO_URL $TMP_URL
        # Change repo
        REPO_JSON=$TMP_URL/repository.json
        contents="$(jq --indent 4 '.name = "Home Assistant addons by Arne Gellhaus (next version)"' $REPO_JSON)" && echo -E "${contents}" > $REPO_JSON
        contents="$(jq --indent 4 '.url = env.NEXT_REPO_URL' $REPO_JSON)" && echo -E "${contents}" > $REPO_JSON
        # Change config
        CONFIG_JSON=$TMP_URL/ha-sip/config.json
        contents="$(jq --indent 4 '.name = "ha-sip-next"' $CONFIG_JSON)" && echo -E "${contents}" > $CONFIG_JSON
        contents="$(jq --indent 4 '.slug = "ha-sip-next"' $CONFIG_JSON)" && echo -E "${contents}" > $CONFIG_JSON
        contents="$(jq --indent 4 '.url = env.NEXT_REPO_URL' $CONFIG_JSON)" && echo -E "${contents}" > $CONFIG_JSON
        contents="$(jq --indent 4 '.description = "Home-Assistant SIP Gateway (next version)"' $CONFIG_JSON)" && echo -E "${contents}" > $CONFIG_JSON
        contents="$(jq --indent 4 '.image = "agellhaus/{arch}-ha-sip-next"' $CONFIG_JSON)" && echo -E "${contents}" > $CONFIG_JSON
        # Change readme
        README=$TMP_URL/README.md
        sed -i -e 's/ha-plugins/ha-plugins-next/g' $README
        sed -i -e 's/c7744bff_ha-sip/8cd50eef_ha-sip-next/g' $README
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
        ;;
    build-amd64)
        echo "Building prod (all archs)..."
        docker run \
            --rm --privileged -v /var/run/docker.sock:/var/run/docker.sock:ro \
            homeassistant/amd64-builder:dev \
            --no-cache --amd64 \
            -t ha-sip -r $REPO_URL -b next \
            --docker-user agellhaus --docker-password "$DOCKER_HUB_PASSWORD"
        ;;
    build-i386)
        echo "Building prod (all archs)..."
        docker run \
            --rm --privileged -v /var/run/docker.sock:/var/run/docker.sock:ro \
            homeassistant/amd64-builder:dev \
            --no-cache --i386 \
            -t ha-sip -r $REPO_URL -b next \
            --docker-user agellhaus --docker-password "$DOCKER_HUB_PASSWORD"
        ;;
    build-aarch64)
        echo "Building prod (all archs)..."
        docker run \
            --rm --privileged -v /var/run/docker.sock:/var/run/docker.sock:ro \
            homeassistant/aarch64-builder:dev \
            --no-cache --aarch64 \
            -t ha-sip -r $REPO_URL -b next \
            --docker-user agellhaus --docker-password "$DOCKER_HUB_PASSWORD"
        ;;
    build-armv7)
        echo "Building prod (all archs)..."
        docker run \
            --rm --privileged -v /var/run/docker.sock:/var/run/docker.sock:ro \
            homeassistant/aarch64-builder:dev \
            --no-cache --armv7 \
            -t ha-sip -r $REPO_URL -b next \
            --docker-user agellhaus --docker-password "$DOCKER_HUB_PASSWORD"
        ;;
    build-armhf)
        echo "Building prod (all archs)..."
        docker run \
            --rm --privileged -v /var/run/docker.sock:/var/run/docker.sock:ro \
            homeassistant/aarch64-builder:dev \
            --no-cache --armhf \
            -t ha-sip -r $REPO_URL -b next \
            --docker-user agellhaus --docker-password "$DOCKER_HUB_PASSWORD"
        ;;
    update)
        echo "Updating builder..."
        docker pull homeassistant/amd64-builder:dev
        ;;
    test)
        echo "Running unit tests..."
        export LD_LIBRARY_PATH="$SCRIPT_DIR"/venv/lib:$LD_LIBRARY_PATH
        source "$SCRIPT_DIR"/venv/bin/activate
        python3 -m unittest discover -s "$SCRIPT_DIR"/ha-sip/src
        echo "Running type-check..."
        pyright ha-sip
        ;;
    run-local)
        export LD_LIBRARY_PATH="$SCRIPT_DIR"/venv/lib:$LD_LIBRARY_PATH
        source "$SCRIPT_DIR"/venv/bin/activate
        "$SCRIPT_DIR"/ha-sip/src/main.py
        ;;
    help)
        export LD_LIBRARY_PATH="$SCRIPT_DIR"/venv/lib:$LD_LIBRARY_PATH
        source "$SCRIPT_DIR"/venv/bin/activate
        "$SCRIPT_DIR"/ha-sip/src/main.py --help
        ;;
    create-venv)
        rm -rf "$SCRIPT_DIR"/venv "$SCRIPT_DIR"/deps
        python3 -m venv "$SCRIPT_DIR"/venv
        source "$SCRIPT_DIR"/venv/bin/activate
        pip3 install pydub requests PyYAML typing_extensions pyright python-dotenv paho-mqtt setuptools audioop-lts
        mkdir "$SCRIPT_DIR"/deps
        cd "$SCRIPT_DIR"/deps || exit
        git clone --depth 1 --branch 2.15.1 https://github.com/pjsip/pjproject.git
        cd pjproject || exit
        ./configure CFLAGS="-O3 -DNDEBUG -fPIC" --enable-shared --disable-libwebrtc --with-ssl --prefix "$SCRIPT_DIR"/venv
        make
        make dep
        make install
        cd pjsip-apps/src/swig || exit
        make python
        cd python || exit
        python setup.py install
        ;;
    *)
        echo "Supply one of 'update-next-repo', 'build-next', 'build-amd64', 'build-arm', 'test', 'update', 'run-local' or 'create-venv'"
        exit 1
        ;;
esac
