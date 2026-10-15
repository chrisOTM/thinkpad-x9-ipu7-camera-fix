#!/usr/bin/python3 -I
"""Create a copy of the libcamhal IPU7 config without the privacy shutter check.

Usage: make-hal-config.py [SRC] [DST]
       defaults: /etc/camera/ipu7x  /etc/camera/ipu7x-noshutter

Removes "privacyShutterEventType" and "privacyShutterEventCode" from
sensors/imx471-uf.json and drops the comma the removal leaves dangling.
The source directory is not modified. Point libcamhal at the copy with
CAMERA_CFG_PATH=<DST>/ (see config/v4l2-relayd-camcfg.conf).
"""
import os
import re
import shutil
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else '/etc/camera/ipu7x'
DST = sys.argv[2] if len(sys.argv) > 2 else '/etc/camera/ipu7x-noshutter'
SENSOR = 'sensors/imx471-uf.json'
KEY = re.compile(r'^\s*"privacyShutterEvent(Type|Code)"\s*:')

if os.path.exists(DST):
    sys.exit(f'{DST} already exists, remove it first')

shutil.copytree(SRC, DST, symlinks=True)
path = os.path.join(DST, SENSOR)
lines = open(path).read().splitlines(keepends=True)
kept = [line for line in lines if not KEY.match(line)]
removed = len(lines) - len(kept)

# The removed keys were the last members of their object; strip the comma
# that now precedes the closing brace.
for i, line in enumerate(kept):
    if line.strip().startswith('}'):
        j = i - 1
        while j >= 0 and not kept[j].strip():
            j -= 1
        if j >= 0 and kept[j].rstrip().endswith(','):
            body = kept[j].rstrip()
            if not body.lstrip().startswith('//'):
                kept[j] = body[:-1] + kept[j][len(body):]

with open(path, 'w') as f:
    f.writelines(kept)
print(f'{DST}: removed {removed} privacy shutter key(s) from {SENSOR}')
