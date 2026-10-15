#!/bin/sh
# Register the fixed ipu-bridge with DKMS so it is rebuilt for every new
# 7.0.x kernel, then build and install it for the given kernel. Run as root.
# Replaces a module installed earlier by install-ipu-bridge.sh.
# Usage: sudo install-dkms.sh [KERNEL_VERSION]   (default: running kernel)
# Undo:  sudo scripts/uninstall-dkms.sh
set -eu

NAME=ipu-bridge-dedup
VERSION=1.0
KVER=${1:-$(uname -r)}
REPO=$(cd "$(dirname "$0")/.." && pwd)
SRC=/usr/src/$NAME-$VERSION

if [ "$(id -u)" -ne 0 ]; then
	echo "run as root" >&2
	exit 1
fi
if ! command -v dkms >/dev/null; then
	echo "dkms not found, install it with: sudo apt install dkms" >&2
	exit 1
fi

if dkms status -m "$NAME" -v "$VERSION" | grep -q .; then
	dkms remove "$NAME/$VERSION" --all
fi
rm -rf "$SRC"
install -d "$SRC"
install -m 644 "$REPO/dkms/dkms.conf" "$REPO/ipu-bridge/ipu-bridge.c" "$REPO/ipu-bridge/Kbuild" "$SRC/"
install -m 755 "$REPO/dkms/dkms-should-build.py" "$REPO/scripts/check-ipu-bridge.py" "$SRC/"

# A manually installed module would compete with the DKMS one in updates/.
if [ -f "/lib/modules/$KVER/updates/ipu-bridge.ko" ]; then
	echo "removing manually installed /lib/modules/$KVER/updates/ipu-bridge.ko"
	rm "/lib/modules/$KVER/updates/ipu-bridge.ko"
fi

echo "check for $KVER: $("$SRC/dkms-should-build.py" "$KVER" || true)"

dkms add "$NAME/$VERSION"
status=0
dkms install "$NAME/$VERSION" -k "$KVER" || status=$?
if [ "$status" -eq 77 ]; then
	echo "skipped for $KVER (not needed or not matching, see check above)"
elif [ "$status" -ne 0 ]; then
	exit "$status"
fi

depmod -a "$KVER"
update-initramfs -u -k "$KVER"

echo
dkms status -m "$NAME"
echo "ipu_bridge for $KVER resolves to: $(modinfo -k "$KVER" -n ipu_bridge)"
