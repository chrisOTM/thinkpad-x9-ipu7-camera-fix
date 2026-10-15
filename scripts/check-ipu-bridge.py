#!/usr/bin/python3 -I
"""List the sensor table of an ipu-bridge module and report duplicate ACPI HIDs.

A duplicate HID makes ipu_bridge register the same software node twice, which
fails with -EEXIST and aborts the intel-ipu7 probe.

Usage: check-ipu-bridge.py [MODULE]   (.ko or .ko.zst, default: modinfo -n ipu_bridge)
Exit status: 0 = no duplicates, 1 = duplicates found, 2 = error.
"""
import collections
import os
import re
import struct
import subprocess
import sys
import tempfile

ENTRY_SIZE = 40  # struct ipu_sensor_config: hid pointer, nr_link_freqs, 3 x u64 link_freqs
ENV = {'LC_ALL': 'C', 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'}


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True, env=ENV).stdout


def load_module(path):
    if path.endswith('.zst'):
        data = subprocess.run(['zstdcat', path], capture_output=True, check=True).stdout
        tmp = tempfile.NamedTemporaryFile(suffix='.ko', delete=False)
        tmp.write(data)
        tmp.close()
        return tmp.name, True
    return path, False


def sections(ko):
    result = {}
    for line in run('readelf', '-SW', ko).splitlines():
        m = re.match(r'\s*\[\s*(\d+)\]\s+(\S+)\s+\S+\s+[0-9a-f]+\s+([0-9a-f]+)', line)
        if m:
            result[int(m[1])] = (m[2], int(m[3], 16))
    return result


def table_entries(ko):
    secs = sections(ko)
    for line in run('readelf', '-sW', ko).splitlines():
        parts = line.split()
        if parts and parts[-1] == 'ipu_supported_sensors':
            value, size, ndx = int(parts[1], 16), int(parts[2]), int(parts[6])
            break
    else:
        sys.exit('ipu_supported_sensors not found in module')

    table_sec = secs[ndx][0]
    data = open(ko, 'rb').read()
    names = {name: off for name, off in secs.values()}

    # Each entry's hid pointer is resolved through a relocation in .rela<section>.
    hids = {}
    current = None
    for line in run('readelf', '-rW', ko).splitlines():
        if line.startswith('Relocation section'):
            current = line.split("'")[1]
            continue
        if current != '.rela' + table_sec:
            continue
        parts = line.split()
        if len(parts) < 7 or not re.fullmatch(r'[0-9a-f]+', parts[0]):
            continue
        off = int(parts[0], 16) - value
        if not 0 <= off < size or off % ENTRY_SIZE:
            continue
        target = names.get(parts[4])
        addend = int(parts[-1], 16) if '+' in line else 0
        if target is not None:
            start = target + addend
            hids[off // ENTRY_SIZE] = data[start:data.index(b'\0', start)].decode()

    base = secs[ndx][1] + value
    for i in range(size // ENTRY_SIZE):
        raw = data[base + i * ENTRY_SIZE:base + (i + 1) * ENTRY_SIZE]
        nr = raw[8]
        freqs = struct.unpack('<3Q', raw[16:40])[:nr]
        if i in hids:
            yield i, hids[i], freqs


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else run('modinfo', '-n', 'ipu_bridge').strip()
    ko, is_tmp = load_module(path)
    try:
        entries = list(table_entries(ko))
    finally:
        if is_tmp:
            os.unlink(ko)

    print(f'{path}: {len(entries)} sensor entries')
    for i, hid, freqs in entries:
        print(f'  {i:2d} {hid:<10} {", ".join(str(f) for f in freqs) or "-"}')

    dups = [hid for hid, n in collections.Counter(h for _, h, _ in entries).items() if n > 1]
    if dups:
        print('DUPLICATES: ' + ', '.join(dups))
        return 1
    print('no duplicates')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        print(f'error: {e}', file=sys.stderr)
        sys.exit(2)
