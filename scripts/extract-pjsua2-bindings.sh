#!/usr/bin/env bash
# Builds the `pjsip-bindings` stage of ha-sip-ng/Dockerfile (pjproject 2.17 + Java SWIG
# module) and extracts the generated org.pjsip.pjsua2 classes (as
# ha-sip-ng/app/libs/pjsua2.jar) plus:
#   ha-sip-ng/app/native/<arch>/jni/libpjsua2.so   -- the JNI wrapper only; point
#     `-Djava.library.path` at this *directory* (not the .so file itself).
#   ha-sip-ng/app/native/<arch>/runtime/*.so*      -- every real pjproject runtime
#     shared lib the JNI wrapper depends on; point `LD_LIBRARY_PATH` at this
#     directory (this is resolved by the OS's dynamic linker, not the JVM, so it
#     is a *different* mechanism than `-Djava.library.path`).
# See the comment above the `pjsip-bindings` stage in ha-sip-ng/Dockerfile for why
# these two are deliberately kept apart (both are conventionally named
# "libpjsua2.so", but are two different files).
#
# Requires: podman or docker.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ha_sip_dir="$repo_root/ha-sip-ng"
image_tag="ha-sip-pjsip-bindings:local"

if command -v podman >/dev/null 2>&1; then
    container_cli=podman
elif command -v docker >/dev/null 2>&1; then
    container_cli=docker
else
    echo "error: neither podman nor docker found in PATH" >&2
    exit 1
fi

arch="$(uname -m)"
case "$arch" in
    x86_64|amd64) out_arch=amd64 ;;
    aarch64|arm64) out_arch=aarch64 ;;
    *) out_arch="$arch" ;;
esac

echo "==> Building PJSIP Java SWIG bindings ($container_cli, target=pjsip-bindings) for $out_arch..."
"$container_cli" build --target pjsip-bindings -t "$image_tag" -f "$ha_sip_dir/Dockerfile" "$ha_sip_dir"

echo "==> Extracting artifacts..."
native_dir="$ha_sip_dir/app/native/$out_arch"
mkdir -p "$ha_sip_dir/app/libs" "$native_dir/jni" "$native_dir/runtime"

cid="$("$container_cli" create "$image_tag")"
trap '"$container_cli" rm -f "$cid" >/dev/null' EXIT

"$container_cli" cp "$cid:/out/pjsua2.jar" "$ha_sip_dir/app/libs/pjsua2.jar"
"$container_cli" cp "$cid:/out/jni/." "$native_dir/jni/"
"$container_cli" cp "$cid:/out/lib/." "$native_dir/runtime/"

echo "==> Done."
echo "    ha-sip-ng/app/libs/pjsua2.jar"
echo "    $native_dir/jni/libpjsua2.so       (point -Djava.library.path here)"
echo "    $native_dir/runtime/*.so*          (point LD_LIBRARY_PATH here)"
echo ""
echo "Example run:"
echo "  LD_LIBRARY_PATH=$native_dir/runtime java -Djava.library.path=$native_dir/jni -jar app/build/libs/ha-sip.jar"
