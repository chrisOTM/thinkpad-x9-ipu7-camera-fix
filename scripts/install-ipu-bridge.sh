#!/bin/sh
# Install the module built by build-ipu-bridge.sh into updates/, which
# takes precedence over the distribution module. Run as root.
# Usage: sudo install-ipu-bridge.sh [KERNEL_VERSION]   (default: running kernel)
# Undo:  sudo rm /lib/modules/<version>/updates/ipu-bridge.ko
#        sudo depmod -a <version> && sudo update-initramfs -u -k <version>
set -eu

KVER=${1:-$(uname -r)}
REPO=$(cd "$(dirname "$0")/.." && pwd)
KO=$REPO/build/$KVER/ipu-bridge.ko

if [ "$(id -u)" -ne 0 ]; then
	echo "run as root" >&2
	exit 1
fi
if [ ! -f "$KO" ]; then
	echo "$KO not found, run scripts/build-ipu-bridge.sh $KVER first" >&2
	exit 1
fi

install -D -m 644 "$KO" "/lib/modules/$KVER/updates/ipu-bridge.ko"
depmod -a "$KVER"
update-initramfs -u -k "$KVER"

echo
echo "installed, modinfo now resolves to:"
modinfo -k "$KVER" -n ipu_bridge
echo "reboot into $KVER to load it"
