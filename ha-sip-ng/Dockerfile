# syntax=docker/dockerfile:1
#
# Multi-stage build:
#   1. pjsip-bindings: builds pjproject 2.17 from source + its Java SWIG module
#      (org.pjsip.pjsua2 classes + libpjsua2.so JNI native lib). Validated in the
#      Phase 0 feasibility spike (see /spike at the repo root).
#   2. app-build: builds the Kotlin app (Gradle) against those bindings, producing
#      a runnable shadow/fat jar.
#   3. final stage (FROM $BUILD_FROM, the HA add-on base image for the target
#      arch): a minimal JRE + runtime libs image with just the built artifacts.
#
# `docker build --target pjsip-bindings` is also used by
# scripts/extract-pjsua2-bindings.sh to pull the bindings out for local
# (non-Docker) Gradle development.

ARG PJPROJECT_VERSION=2.17
ARG BUILD_FROM

# openjdk-25-jdk isn't available on bookworm (Debian 12 defaults to JDK 17) --
# trixie (Debian 13) ships it in the main repo, and
# matches the runtime stage below (ghcr.io/hassio-addons/debian-base is also
# trixie-based), so build and runtime stages now share the same Debian release.
FROM debian:trixie AS pjsip-bindings
ENV LANG=C.UTF-8

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    build-essential git swig openjdk-25-jdk libssl-dev libopus-dev pkg-config ca-certificates

# Debian's openjdk-25-jdk package path differs per architecture (e.g.
# java-25-openjdk-amd64 vs java-25-openjdk-arm64); resolve it dynamically instead
# of hardcoding one arch.
RUN ln -sfn "$(dirname "$(dirname "$(readlink -f "$(which javac)")")")" /opt/jdk
ENV JAVA_HOME=/opt/jdk

ARG PJPROJECT_VERSION
RUN git clone --depth 1 --branch ${PJPROJECT_VERSION} https://github.com/pjsip/pjproject.git /tmp/pjproject

WORKDIR /tmp/pjproject
RUN set -xe \
    && ./configure CFLAGS="-O3 -DNDEBUG -fPIC" --enable-shared --disable-libwebrtc --with-ssl --with-opus=/usr \
    && make \
    && make dep \
    && make install \
    && ldconfig

WORKDIR /tmp/pjproject/pjsip-apps/src/swig
RUN make java

# NOTE: the JNI wrapper built just above (java/output/libpjsua2.so, containing the
# Java_org_pjsip_pjsua2_* entry points) and pjproject's own C++ PJSUA2 shared
# library (/usr/local/lib/libpjsua2.so, installed by `make install` a few steps
# up) are BOTH named "libpjsua2.so" -- but they are two different files serving
# different purposes, and the JNI wrapper dynamically depends on the C++ one at
# runtime. They must NOT be collapsed into the same directory (the second copy
# would silently clobber the first). So:
#   /out/jni/libpjsua2.so  -- the JNI wrapper only, for `-Djava.library.path`
#                             (matches `System.loadLibrary("pjsua2")`'s search).
#   /out/lib/*.so*         -- every real pjproject runtime shared lib (including
#                             the C++ libpjsua2.so.2 the JNI wrapper needs), for
#                             installing into a normal system lib directory +
#                             `ldconfig` so the OS's dynamic linker (not the JVM)
#                             can resolve the JNI wrapper's own dependencies.
RUN set -xe \
    && mkdir -p /out/classes /out/lib /out/jni \
    && cp -r java/output/org /out/classes/ \
    && find /out/classes -name "*.java" -delete \
    && cp java/output/libpjsua2.so /out/jni/libpjsua2.so \
    && cp -P /usr/local/lib/*.so* /out/lib/ \
    && cd /out/classes \
    && jar --create --file /out/pjsua2.jar org


FROM eclipse-temurin:25-jdk AS app-build
WORKDIR /build

COPY settings.gradle.kts build.gradle.kts gradlew ./
COPY gradle ./gradle
COPY core ./core
COPY app ./app
COPY integration-test/build.gradle.kts ./integration-test/build.gradle.kts
COPY --from=pjsip-bindings /out/pjsua2.jar ./app/libs/pjsua2.jar

RUN ./gradlew :app:shadowJar --no-daemon --console=plain


FROM $BUILD_FROM
ENV LANG=C.UTF-8

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    openjdk-25-jre-headless ffmpeg libssl3 libopus0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=pjsip-bindings /out/lib/ /usr/lib/
COPY --from=pjsip-bindings /out/jni/ /usr/lib/pjsip-jni/
RUN ldconfig

COPY --from=app-build /build/app/build/libs/ha-sip.jar /ha-sip/ha-sip.jar

COPY run.sh run-in-ha.sh run-standalone.sh /
RUN chmod a+x /run.sh /run-in-ha.sh /run-standalone.sh

WORKDIR /

CMD [ "/run.sh" ]
