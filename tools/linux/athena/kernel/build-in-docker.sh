#!/bin/bash
# Build on Linux inside Docker, including on Apple silicon Macs. Does not access a device.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../.." && pwd)
IMAGE=techo5-athena-kbuild:ubuntu24.04
VOLUME=techo5-athena-kbuild
OUT=${OUT:-$ROOT/build/athena-kernel}

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
docker build --platform linux/arm64 -t "$IMAGE" -f "$HERE/Dockerfile.build" "$HERE"
docker volume create "$VOLUME" >/dev/null
docker run --rm --platform linux/arm64 --name techo5-athena-kbuild \
    --mount "type=bind,src=$ROOT,dst=/repo,readonly" \
    --mount "type=volume,src=$VOLUME,dst=/work" \
    --mount "type=bind,src=$OUT,dst=/out" \
    -e WORK=/work -e OUT=/out -e JOBS="${JOBS:-4}" \
    "$IMAGE" bash /repo/tools/linux/athena/kernel/build.sh
