#!/bin/sh
# Remove the DKMS module for all kernels and restore the distribution
# ipu-bridge. Run as root.
set -eu

NAME=ipu-bridge-dedup
VERSION=1.0

if [ "$(id -u)" -ne 0 ]; then
	echo "run as root" >&2
	exit 1
fi

kernels=$(dkms status -m "$NAME" -v "$VERSION" | sed -n 's/^[^,]*, \([^,]*\),.*installed.*/\1/p')
if dkms status -m "$NAME" -v "$VERSION" | grep -q .; then
	dkms remove "$NAME/$VERSION" --all
fi
rm -rf "/usr/src/$NAME-$VERSION"

for k in $kernels; do
	depmod -a "$k"
	update-initramfs -u -k "$k"
done
echo "removed; reboot to load the distribution ipu-bridge again"
