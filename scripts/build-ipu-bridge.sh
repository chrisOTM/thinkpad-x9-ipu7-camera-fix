#!/bin/sh
# Build the fixed ipu-bridge module out of tree.
# Usage: build-ipu-bridge.sh [KERNEL_VERSION]   (default: running kernel)
# Needs linux-headers-<version>, gcc, make. Output: build/<version>/ipu-bridge.ko
set -eu

KVER=${1:-$(uname -r)}
REPO=$(cd "$(dirname "$0")/.." && pwd)
KDIR=/lib/modules/$KVER/build
OUT=$REPO/build/$KVER

if [ ! -f "$KDIR/Makefile" ]; then
	echo "kernel headers for $KVER not found at $KDIR" >&2
	exit 1
fi

mkdir -p "$OUT"
cp "$REPO/ipu-bridge/ipu-bridge.c" "$REPO/ipu-bridge/Kbuild" "$OUT/"
make -C "$KDIR" M="$OUT" modules

echo
echo "built: $OUT/ipu-bridge.ko"
modinfo -F vermagic "$OUT/ipu-bridge.ko"
