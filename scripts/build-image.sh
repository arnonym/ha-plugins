#!/usr/bin/env bash
# Builds one app's container image locally, for this machine's architecture, the same
# way CI does: the base image comes from the app's build.json, the tag from its
# config.json. Nothing is pushed.
#
# Usage: scripts/build-image.sh <ha-sip|ha-sip-kt>
set -euo pipefail

app="${1:?usage: $0 <app directory, e.g. ha-sip or ha-sip-kt>}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_dir="$repo_root/$app"
[ -f "$app_dir/config.json" ] || { echo "error: $app_dir/config.json not found" >&2; exit 1; }

container_cli="$(command -v podman || command -v docker || true)"
[ -n "$container_cli" ] || { echo "error: neither podman nor docker found" >&2; exit 1; }

case "$(uname -m)" in
    x86_64|amd64) arch=amd64 ;;
    aarch64|arm64) arch=aarch64 ;;
    *) echo "error: unsupported architecture $(uname -m)" >&2; exit 1 ;;
esac

build_from="$(jq -r ".build_from.$arch" "$app_dir/build.json")"
version="$(jq -r '.version' "$app_dir/config.json")"
image="$(jq -r '.image' "$app_dir/config.json" | sed "s/{arch}/$arch/")"

echo "Building $image:$version from $build_from..."
"$container_cli" build \
    --build-arg "BUILD_FROM=$build_from" \
    -t "$image:$version" \
    "$app_dir"
