# ThinkPad X9-14 Gen 1 webcam fix for Ubuntu 26.04 (IPU7 + IMX471)

Gets the built-in camera of the Lenovo ThinkPad X9-14 Gen 1 (Intel Lunar Lake
IPU7, Sony IMX471 sensor) working on Ubuntu 26.04 with the stock
`7.0.0-38-generic` kernel. Applications see it as `/dev/video0`
("Intel MIPI Camera") at 1920x1080, 30 fps.

Two independent bugs break the camera. Fixing both is enough. No firmware
swap, out-of-tree IPU7 driver or self-built camera HAL is needed.

| | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | No `/dev/media0`, call trace in `ipu7_pci_probe`, `imx471 ... failed to check hwcfg: -517` | Ubuntu's `ipu-bridge` lists `SONY471A` twice in its sensor table | Rebuilt `ipu-bridge` without the duplicate |
| 2 | `/dev/video0` exists but shows a black or green image | The privacy shutter switch reports "covered" while the camera is on, so libcamhal substitutes a dummy image | libcamhal config copy without the shutter check |

## Tested setup

- ThinkPad X9-14 Gen 1 (machine type 21QA), BIOS N4DET41W (1.24)
- Ubuntu 26.04, kernel `7.0.0-38-generic`
- Ubuntu packages `libcamhal-ipu7x`, `gstreamer1.0-icamera`, `v4l2-relayd`,
  `linux-modules-ipu7-generic-hwe-26.04` (from the OEM/"Additional Drivers"
  selection `libcamhal-ipu7x`; `intel-ipu7-dkms` is *not* installed)
- IPU7 firmware 1.1.9 as shipped

Other kernels, models or sensors are untested. Run `scripts/check-ipu-bridge.py`
first to see whether bug 1 applies to you.

## Bug 1: duplicate sensor in `ipu-bridge`

### Symptom

```
intel-ipu7 0000:00:05.0: Found supported sensor SONY471A:00
sysfs: cannot create duplicate filename '/kernel/software_nodes/SONY471A-0'
...
 ipu_bridge_connect_sensor+0x10a/0x2b0 [ipu_bridge]
 ipu_bridge_init+0x1c7/0x250 [ipu_bridge]
 ipu7_pci_probe.cold+0x538/0xa7b [intel_ipu7]
...
intel-ipu7 0000:00:05.0: error -EEXIST: IPU bridge init failed
intel-ipu7 0000:00:05.0: probe with driver intel-ipu7 failed with error -17
imx471 i2c-SONY471A:00: failed to check hwcfg: -517
```

There is no `isys`/`psys`, no `/dev/media*`, and libcamhal reports "failed to
open PCI device". The `-517` (`-EPROBE_DEFER`) from `imx471` is only a
consequence: the sensor never gets its fwnode endpoint.

### Cause

Upstream Linux v7.0 lists `SONY471A` in `ipu_supported_sensors` in
`drivers/media/pci/intel/ipu-bridge.c`. Ubuntu's kernel carries its own patch
that adds the same entry, so the 7.0.0-38 module has it twice (28 entries; the
6.17 OEM kernel, where only Ubuntu's entry exists, has 27). `ipu_bridge_init()` walks the table per HID, finds
the same ACPI device on the second pass and registers the software node
`SONY471A-0` again, which fails with `-EEXIST`.

`scripts/check-ipu-bridge.py` decodes the table from the binary module:

```
$ scripts/check-ipu-bridge.py /lib/modules/7.0.0-38-generic/kernel/drivers/media/pci/intel/ipu-bridge.ko.zst
... 28 sensor entries
  ...
  24 SONY471A   200000000
  25 XMCC0003   321468000
  26 SONY471A   200000000
  27 TBE20A0    200000000
DUPLICATES: SONY471A
```

### Fix

[`ipu-bridge/ipu-bridge.c`](ipu-bridge/ipu-bridge.c) is upstream `v7.0` plus
the extra entries Ubuntu ships, minus the duplicate. The Ubuntu entries were
recovered from the binary module because the Ubuntu kernel git was unreachable:
`INT346D` (848 MHz), `TBE20A0` (200 MHz) and a second link frequency for
`OVTI05C1` (900 MHz). The diff against upstream is in
[`ipu-bridge/ubuntu-7.0-sensor-table.patch`](ipu-bridge/ubuntu-7.0-sensor-table.patch).

The rebuilt module has the same vermagic and exported symbol CRCs as Ubuntu's,
so the stock `intel_ipu7` loads it unchanged. It is installed to `updates/`,
which `depmod` prefers over the distribution module. Nothing in `kernel/` is
modified.

```sh
sudo apt install linux-headers-$(uname -r) build-essential
scripts/build-ipu-bridge.sh
scripts/check-ipu-bridge.py build/$(uname -r)/ipu-bridge.ko   # expect "no duplicates"
sudo scripts/install-ipu-bridge.sh
sudo reboot
```

After the reboot:

```
intel-ipu7 0000:00:05.0: Found supported sensor SONY471A:00
intel-ipu7 0000:00:05.0: Connected 1 cameras
imx471 i2c-SONY471A:00: imx471 probe successfully
intel_ipu7_isys.isys intel_ipu7.isys.40: bind imx471 0-0010 nlanes is 4 port is 0
intel_ipu7_psys.psys intel_ipu7.psys.40: IPU psys probe done.
```

## Bug 2: inverted privacy shutter state

### Symptom

The kernel side works, `v4l2-relayd` runs, but `/dev/video0` delivers a black
image. Running `icamerasrc` directly gives uniformly green frames and:

```
CamHAL[ERR] FileSource: Cannot open frame file:/etc/camera/ipu7x/dummy_1280x720.nv12
CamHAL[WAR] AiqUnit: run3A: AIQ is not started: 4
```

### Cause

`/etc/camera/ipu7x/sensors/imx471-uf.json` contains

```json
"privacyShutterEventType": 5,
"privacyShutterEventCode": 9
```

i.e. libcamhal watches `EV_SW` / `SW_CAMERA_LENS_COVER`. On this machine that
switch comes from the `thinkpad_acpi` input device "ThinkPad Extra Buttons",
and its value is inverted:

| Camera key LED | Camera | `SW_CAMERA_LENS_COVER` |
|---|---|---|
| off | enabled | 1 (covered) |
| on | disabled | 0 (open) |

With the camera enabled, libcamhal therefore believes the lens is covered and
streams its dummy image source. That source would show a placeholder file,
but the file is not shipped, so the result is an all-zero NV12 buffer (green,
black after conversion). `scripts/shutter-state.py` prints the current value.

The camera key also cuts the sensor off in hardware: with the LED on, the
sensor reports "Start streaming" but the ISYS receives no frames. Ignoring
the reported switch state therefore keeps the privacy key working.

### Fix

libcamhal reads its configuration directory from `CAMERA_CFG_PATH`. Create a
copy without the two keys and point `v4l2-relayd` at it.
`/etc/camera/ipu7x` stays untouched.

```sh
sudo scripts/make-hal-config.py          # creates /etc/camera/ipu7x-noshutter
sudo install -D -m 644 config/v4l2-relayd-camcfg.conf \
    /etc/systemd/system/v4l2-relayd@default.service.d/camcfg.conf
sudo systemctl daemon-reload
sudo systemctl restart v4l2-relayd@default
```

To test without the relay:

```sh
sudo systemctl stop v4l2-relayd@default
sudo env CAMERA_CFG_PATH=/etc/camera/ipu7x-noshutter/ \
    gst-launch-1.0 icamerasrc num-buffers=30 \
    ! video/x-raw,format=NV12,width=1280,height=720 \
    ! videoconvert ! jpegenc ! multifilesink location=/tmp/frame%02d.jpg
sudo systemctl start v4l2-relayd@default
```

## Optional: 1080p and 50 Hz anti-banding

Ubuntu's relay default is 1280x720. The HAL supports 1920x1080 NV12 at 30 fps
(the sensor runs 1928x1088), and 720p also shows a ~10 px grey strip at the
bottom edge that 1080p does not. In regions with a 50 Hz mains supply, fixed
50 Hz anti-banding avoids flicker under artificial light.

```sh
sudo cp /etc/v4l2-relayd.d/default.conf /etc/v4l2-relayd.d/default.conf.orig
sudo install -m 644 config/v4l2-relayd-default.conf /etc/v4l2-relayd.d/default.conf
sudo systemctl restart v4l2-relayd@default
```

Other `icamerasrc` properties can be appended to `VIDEOSRC` the same way:
`sharpness`, `saturation`, `contrast`, `brightness` (-128..127), `ev` (-3..3),
`wdr-level` (0..200, default 100), `awb-mode`. See `gst-inspect-1.0 icamerasrc`.
HDR scene modes, video stabilization and autofocus are not available for this
sensor according to its HAL config.

## Verify

```sh
scripts/check-ipu-bridge.py                      # loaded module: no duplicates
ls /dev/media0 /dev/ipu7-psys0
gst-launch-1.0 v4l2src device=/dev/video0 num-buffers=60 ! videoconvert ! autovideosink
```

## Rollback

```sh
# bug 1
sudo rm /lib/modules/$(uname -r)/updates/ipu-bridge.ko
sudo depmod -a && sudo update-initramfs -u
# bug 2
sudo rm -r /etc/systemd/system/v4l2-relayd@default.service.d /etc/camera/ipu7x-noshutter
sudo systemctl daemon-reload && sudo systemctl restart v4l2-relayd@default
# 1080p / 50 Hz
sudo mv /etc/v4l2-relayd.d/default.conf.orig /etc/v4l2-relayd.d/default.conf
sudo systemctl restart v4l2-relayd@default
```

## Maintenance

- **New kernel:** the module in `updates/` only applies to the version it was
  built for. On every kernel update, run `scripts/check-ipu-bridge.py` against
  the new kernel's module. If it still reports the duplicate, rebuild and
  install for that version (`build-ipu-bridge.sh <version>`,
  `install-ipu-bridge.sh <version>`). If Ubuntu changed other parts of
  `ipu-bridge.c`, compare before installing. A DKMS package is not provided.
- **libcamhal update:** `/etc/camera/ipu7x-noshutter` is a copy and does not
  follow package updates. Recreate it after `libcamhal-ipu7x` changes.
- **v4l2-relayd update:** the package may replace or ask about
  `/etc/v4l2-relayd.d/default.conf`.

## Repository layout

| Path | Purpose |
|---|---|
| `ipu-bridge/ipu-bridge.c` | Fixed module source (GPL-2.0, from Linux v7.0) |
| `ipu-bridge/ubuntu-7.0-sensor-table.patch` | Diff against upstream v7.0 |
| `scripts/build-ipu-bridge.sh` | Out-of-tree build against installed headers |
| `scripts/install-ipu-bridge.sh` | Install to `updates/`, depmod, initramfs |
| `scripts/check-ipu-bridge.py` | Decode a module's sensor table, report duplicates |
| `scripts/shutter-state.py` | Read `SW_CAMERA_LENS_COVER` |
| `scripts/make-hal-config.py` | Create the HAL config copy without the shutter check |
| `config/v4l2-relayd-camcfg.conf` | systemd drop-in setting `CAMERA_CFG_PATH` |
| `config/v4l2-relayd-default.conf` | Relay config: 1080p, 50 Hz anti-banding |

## References

- [intel/ipu7-drivers](https://github.com/intel/ipu7-drivers), issues
  [#63](https://github.com/intel/ipu7-drivers/issues/63) and
  [#65](https://github.com/intel/ipu7-drivers/issues/65)
- [intel/ipu7-camera-hal](https://github.com/intel/ipu7-camera-hal)
- [intel/icamerasrc](https://github.com/intel/icamerasrc/tree/icamerasrc_slim_api)

## Disclaimer and license

Unofficial and not affiliated with Lenovo, Intel or Canonical. You load a
self-built kernel module at your own risk. Keep a known-good kernel in the
GRUB menu.

Licensed under GPL-2.0 (see [LICENSE](LICENSE)). `ipu-bridge/ipu-bridge.c`
is derived from the Linux kernel and keeps its original copyright notice.
