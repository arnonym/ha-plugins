#!/usr/bin/env bash
# Native (no Docker/Podman) equivalent of scripts/extract-pjsua2-bindings.sh --
# the Kotlin/JVM counterpart of the Python project's `build.sh create-venv`.
#
# Builds pjproject + its Java SWIG module directly on this machine (into
# deps/kt/pjproject, isolated from the system via --prefix) and copies the
# resulting jar/native libs straight into ha-sip-kt/app/{libs,native}, exactly
# like the Docker-based script does. Once run, `./gradlew build`/`run` work
# fully offline with no container involved ever again (until you want to
# rebuild against a different pjproject version).
#
# Requires locally installed: git, build-essential (gcc/g++/make), swig,
# a JDK (with jni.h), libssl-dev, libopus-dev/opus headers, pkg-config.
set -euo pipefail

PJPROJECT_VERSION="${PJPROJECT_VERSION:-2.17}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ha_sip_dir="$repo_root/ha-sip-kt"
# deps/kt, not deps: deps/pjproject is the Python app's own checkout (build.sh create-venv).
deps_dir="$repo_root/deps/kt"
prefix="$deps_dir/install"

command -v git >/dev/null || { echo "error: git not found" >&2; exit 1; }
command -v swig >/dev/null || { echo "error: swig not found (install swig)" >&2; exit 1; }
command -v gcc >/dev/null || { echo "error: gcc not found (install build tools)" >&2; exit 1; }

if [ -z "${JAVA_HOME:-}" ]; then
    echo "error: JAVA_HOME must be set to a JDK (not just a JRE) that has jni.h" >&2
    exit 1
fi
if [ ! -f "$JAVA_HOME/include/jni.h" ]; then
    echo "error: $JAVA_HOME/include/jni.h not found -- JAVA_HOME must point at a full JDK" >&2
    exit 1
fi

arch="$(uname -m)"
case "$arch" in
    x86_64|amd64) out_arch=amd64 ;;
    aarch64|arm64) out_arch=aarch64 ;;
    *) out_arch="$arch" ;;
esac

echo "==> Cloning pjproject $PJPROJECT_VERSION into $deps_dir/pjproject..."
rm -rf "$deps_dir/pjproject" "$prefix"
mkdir -p "$deps_dir"
git clone --depth 1 --branch "$PJPROJECT_VERSION" https://github.com/pjsip/pjproject.git "$deps_dir/pjproject"

echo "==> Building pjproject (installed to $prefix, not touching system paths)..."
(
    cd "$deps_dir/pjproject"
    ./configure CFLAGS="-O3 -DNDEBUG -fPIC" --enable-shared --disable-libwebrtc --with-ssl --with-opus=/usr --prefix "$prefix"
    make
    make dep
    make install
)

echo "==> Building the Java SWIG module..."
(
    cd "$deps_dir/pjproject/pjsip-apps/src/swig"
    make java
)

echo "==> Collecting artifacts into ha-sip-kt/app/{libs,native/$out_arch}..."
swig_java_out="$deps_dir/pjproject/pjsip-apps/src/swig/java/output"
classes_dir="$deps_dir/classes"
native_dir="$ha_sip_dir/app/native/$out_arch"

rm -rf "$classes_dir"
mkdir -p "$classes_dir" "$ha_sip_dir/app/libs" "$native_dir/jni" "$native_dir/runtime"

cp -r "$swig_java_out/org" "$classes_dir/"
find "$classes_dir" -name "*.java" -delete
"$JAVA_HOME/bin/jar" --create --file "$ha_sip_dir/app/libs/pjsua2.jar" -C "$classes_dir" org

# Same naming-collision caveat as the Docker path (see ha-sip-kt/Dockerfile): the
# JNI wrapper and pjproject's own C++ libpjsua2.so are two different files that
# are both conventionally named "libpjsua2.so" -- keep them in separate dirs.
cp "$swig_java_out/libpjsua2.so" "$native_dir/jni/libpjsua2.so"
cp -P "$prefix"/lib/*.so* "$native_dir/runtime/"

echo "==> Done. Built entirely locally, no Docker/Podman involved."
echo "    ha-sip-kt/app/libs/pjsua2.jar"
echo "    $native_dir/jni/libpjsua2.so       (point -Djava.library.path here)"
echo "    $native_dir/runtime/*.so*          (point LD_LIBRARY_PATH here)"
echo ""
echo "Example run:"
echo "  LD_LIBRARY_PATH=$native_dir/runtime java -Djava.library.path=$native_dir/jni -jar app/build/libs/ha-sip.jar"
