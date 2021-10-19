ARG BUILD_FROM
FROM $BUILD_FROM
ENV LANG C.UTF-8

RUN apt-get update
RUN apt-get install -y build-essential git swig python3 python3-dev python3-pip ffmpeg

RUN pip3 install pydub requests

RUN set -xe \
    && git clone https://github.com/pjsip/pjproject.git \
    && cd pjproject \
    && git reset --hard 4dc183bf373535a9cb37ed6f2cc6b510bdb3901b \
    && ./configure --enable-shared \
    && make \
    && make dep \
    && make install \
    && cd pjsip-apps/src/swig \
    && make python \
    && make -C python install \
    && ldconfig

COPY run.sh /
RUN chmod a+x /run.sh

COPY src/ /ha-sip/

CMD [ "/run.sh" ]
