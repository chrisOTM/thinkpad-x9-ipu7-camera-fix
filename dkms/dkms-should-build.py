#!/usr/bin/python3 -I
"""Decide whether DKMS should build the fixed ipu-bridge for a kernel.

Usage: dkms-should-build.py KERNEL_VERSION
Exit status: 0 = build, 1 = skip (reason on stdout).

Build only if the distribution module for that kernel lists a sensor HID more
than once AND its table without the duplicates matches ipu-bridge.c in this
directory exactly. Otherwise the distribution either fixed the bug or changed
the table, and installing this module would replace a newer one.
"""
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SENSOR_RE = re.compile(r'IPU_SENSOR_CONFIG\("([^"]+)",\s*(\d+)((?:\s*,\s*\d+)*)\s*\)')


def load_checker():
    spec = importlib.util.spec_from_file_location(
        'check_ipu_bridge', os.path.join(HERE, 'check-ipu-bridge.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def source_table(path):
    entries = []
    for hid, nr, rest in SENSOR_RE.findall(open(path).read()):
        freqs = tuple(int(f) for f in re.findall(r'\d+', rest))
        if len(freqs) != int(nr):
            sys.exit(f'{path}: {hid} declares {nr} link frequencies, has {len(freqs)}')
        entries.append((hid, freqs))
    return entries


def distro_module(kver):
    base = f'/lib/modules/{kver}/kernel/drivers/media/pci/intel/ipu-bridge.ko'
    for candidate in (base + '.zst', base + '.xz', base):
        if os.path.exists(candidate):
            return candidate
    return None


def decide(kver):
    module = distro_module(kver)
    if module is None:
        return False, f'no distribution ipu-bridge module for {kver}'
    if module.endswith('.xz'):
        return False, f'{module}: xz-compressed modules are not supported'

    checker = load_checker()
    path, is_tmp = checker.load_module(module)
    try:
        distro = [(hid, tuple(freqs)) for _, hid, freqs in checker.table_entries(path)]
    finally:
        if is_tmp:
            os.unlink(path)

    ours = source_table(os.path.join(HERE, 'ipu-bridge.c'))
    if len(set(distro)) == len(distro):
        return False, f'{module}: no duplicate sensor entries, distribution module is fine'
    if set(distro) != set(ours) or len(ours) != len(set(ours)):
        return False, (f'{module}: sensor table differs from ipu-bridge.c beyond the '
                       'duplicate, update the source before building')
    dups = sorted({hid for hid, _ in distro if [h for h, _ in distro].count(hid) > 1})
    return True, f'{module}: duplicate {", ".join(dups)}, building fixed module'


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip().splitlines()[2])
    try:
        build, reason = decide(sys.argv[1])
    except Exception as e:  # never let a check failure break kernel installs
        build, reason = False, f'check failed: {e}'
    print(reason)
    sys.exit(0 if build else 1)
