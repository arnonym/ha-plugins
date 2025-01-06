ARG BUILD_FROM
FROM $BUILD_FROM
ENV LANG C.UTF-8

COPY user.mak /tmp/
WORKDIR /tmp/pjproject

RUN apk update \
    && apk upgrade \
    && apk add --no-cache build-base openssl-dev alsa-lib-dev gsm-dev opus-dev speex-dev speexdsp-dev portaudio-dev libsrtp-dev libsamplerate-dev linux-headers python3-dev swig ffmpeg git \
    && rm /var/cache/apk/* \
    && pip3 install --no-cache-dir pydub requests PyYAML typing_extensions python-dotenv paho-mqtt \
    && git clone --depth 1 --branch 2.14.1 https://github.com/pjsip/pjproject.git /tmp/pjproject \
    && cp /tmp/user.mak /tmp/pjproject \
    && set -xe \
    && ./configure --enable-shared --disable-libwebrtc \
    && make \
    && make dep \
    && make install \
    && cd pjsip-apps/src/swig \
    && make python \
    && make -C python install \
    && make -C python clean \
    && cd / \
    && rm -rf /tmp/pjproject \
    && rm /tmp/user.mak \
    && apk --purge del build-base openssl-dev alsa-lib-dev gsm-dev opus-dev speex-dev speexdsp-dev portaudio-dev libsrtp-dev libsamplerate-dev linux-headers python3-dev git

COPY run.sh /
RUN chmod a+x /run.sh

COPY src/ /ha-sip/

CMD [ "/run.sh" ]
