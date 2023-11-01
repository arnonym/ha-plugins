ARG BUILD_FROM
FROM $BUILD_FROM
ENV LANG C.UTF-8

RUN apk update
RUN apk upgrade
RUN apk add build-base openssl-dev alsa-lib-dev gsm-dev opus-dev speex-dev speexdsp-dev portaudio-dev libsrtp-dev libsamplerate-dev linux-headers python3-dev swig ffmpeg git

RUN pip3 install pydub requests PyYAML typing_extensions

WORKDIR /tmp
RUN set -xe \
    && git clone --depth 1 --branch 2.14 https://github.com/pjsip/pjproject.git \
    && cd pjproject \
    && ./configure --enable-shared --disable-libwebrtc \
    && make \
    && make dep \
    && make install \
    && cd pjsip-apps/src/swig \
    && make python \
    && make -C python install \
    && rm -rf /tmp/pjproject

COPY run.sh /
RUN chmod a+x /run.sh

COPY src/ /ha-sip/

CMD [ "/run.sh" ]
