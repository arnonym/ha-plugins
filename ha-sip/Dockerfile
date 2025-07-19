ARG BUILD_FROM
FROM $BUILD_FROM
ENV LANG=C.UTF-8

RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install -y build-essential git swig python3 python3-dev python3-pip ffmpeg binutils

RUN pip3 install pydub requests PyYAML typing_extensions python-dotenv paho-mqtt setuptools --break-system-packages

RUN git clone --depth 1 --branch 2.15.1 https://github.com/pjsip/pjproject.git /tmp/pjproject

WORKDIR /tmp/pjproject

RUN set -xe \
    && ./configure CFLAGS="-O3 -DNDEBUG -fPIC" --enable-shared --disable-libwebrtc \
    && make \
    && make dep \
    && make install \
    && cd pjsip-apps/src/swig \
    && make python \
    && make -C python install \
    && cd / \
    && rm -rf /tmp/pjproject \
    && ldconfig

COPY run.sh run-in-ha.sh run-standalone.sh /
RUN chmod a+x /run.sh /run-in-ha.sh /run-standalone.sh

COPY src/ /ha-sip/

WORKDIR /

CMD [ "/run.sh" ]
