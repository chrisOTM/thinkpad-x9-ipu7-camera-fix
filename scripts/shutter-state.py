#!/usr/bin/python3 -I
"""Print the camera privacy shutter state as reported by thinkpad_acpi.

The libcamhal sensor config for the IMX471 watches EV_SW / SW_CAMERA_LENS_COVER.
On the ThinkPad X9-14 Gen 1 the reported value is inverted: it reads 1 (covered)
while the camera is enabled. Needs read access to /dev/input/event* (group input).
"""
import array
import fcntl
import glob
import sys

SW_CAMERA_LENS_COVER = 9
EVIOCGSW = (2 << 30) | (8 << 16) | (ord('E') << 8) | 0x1b

found = False
for ev in sorted(glob.glob('/sys/class/input/event*')):
    with open(f'{ev}/device/name') as f:
        if f.read().strip() != 'ThinkPad Extra Buttons':
            continue
    found = True
    dev = '/dev/input/' + ev.rsplit('/', 1)[1]
    buf = array.array('B', [0] * 8)
    with open(dev, 'rb') as f:
        fcntl.ioctl(f, EVIOCGSW, buf, True)
    covered = (int.from_bytes(bytes(buf), 'little') >> SW_CAMERA_LENS_COVER) & 1
    print(f'{dev}: SW_CAMERA_LENS_COVER = {covered} ({"covered" if covered else "open"})')

if not found:
    sys.exit('no "ThinkPad Extra Buttons" input device found')
