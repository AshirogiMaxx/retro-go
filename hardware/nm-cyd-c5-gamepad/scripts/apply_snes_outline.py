#!/usr/bin/env python3
"""Apply the SNES dog-bone outline to the EasyEDA artifacts, touching the board edge only.

Sources of truth:
  * easyeda/controller.epcb                    - exported PCB document (L / ARC text format)
  * easyeda/NM-CYD-C5-Gamepad-RevA.epro2       - self-contained project archive (.epru inside)
  * manufacturing/*.zip                        - Gerbers, board outline layer only

Each artifact keeps its existing copper, silkscreen, mask, drills and component data; only the
board-outline polygon (layer 11) and the Gerber_BoardOutlineLayer.GKO contour are replaced.
"""
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_SOURCE = Path('/Users/rubenponcemartinez/.hermes/cache/scratch/nmcyd/controller_new.epcb')
NEW_GKO = Path('/Users/rubenponcemartinez/.hermes/cache/scratch/nmcyd/outline_x/Gerber_BoardOutlineLayer.GKO')

DOC_UUID = '7f423eabe62144d5'


def poly_body(text):
    """Return the JSON body of the single layer-11 POLY record."""
    for line in text.splitlines():
        line = line.strip()
        if not line or '||' not in line:
            continue
        head, _, body = line.partition('||')
        if '"POLY"' not in head:
            continue
        obj = json.loads(body.rstrip('|'))
        if obj.get('layerId') == 11:
            return body.rstrip('|')
    raise SystemExit('no board-outline POLY found')


def replace_poly(text, new_body, expect_uuid=None):
    """Swap the layer-11 POLY body in a document source."""
    lines = text.split('\n')
    done = 0
    doc = None
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or '||' not in s:
            continue
        head, _, body = s.partition('||')
        if '"DOCHEAD"' in head:
            doc = json.loads(body.rstrip('|')).get('uuid')
        if '"POLY"' not in head:
            continue
        if expect_uuid and doc != expect_uuid:
            continue
        obj = json.loads(body.rstrip('|'))
        if obj.get('layerId') != 11:
            continue
        lines[i] = head + '||' + new_body + '|'
        done += 1
    if done != 1:
        raise SystemExit(f'expected exactly one outline replacement, made {done}')
    return '\n'.join(lines)


def gko_contour(text):
    """Everything between the G54D10* aperture select and M02*."""
    m = re.search(r'G54D10\*\s*\n(.*?)\nM02\*', text, re.S)
    if not m:
        raise SystemExit('cannot locate contour block in gerber')
    return m.group(1).strip('\n')


def main(apply=False):
    new_body = poly_body(NEW_SOURCE.read_text())
    new_contour = gko_contour(NEW_GKO.read_text())

    # 1. exported PCB document
    epcb = ROOT / 'easyeda/controller.epcb'
    src = epcb.read_text()
    updated = replace_poly(src, new_body)
    print(f'controller.epcb: {"unchanged" if updated == src else "outline replaced"}')

    # 2. self-contained project archive
    epro2 = ROOT / 'easyeda/NM-CYD-C5-Gamepad-RevA.epro2'
    with zipfile.ZipFile(epro2) as z:
        entries = [(i, z.read(i.filename)) for i in z.infolist()]
    epru_name = next(i.filename for i, _ in entries if i.filename.endswith('.epru'))
    new_entries = []
    for info, data in entries:
        if info.filename == epru_name:
            text = data.decode()
            replaced = replace_poly(text, new_body, expect_uuid=DOC_UUID)
            print(f'{epru_name}: {"unchanged" if replaced == text else "outline replaced"}')
            data = replaced.encode()
        new_entries.append((info, data))

    # 3. gerber archives - outline layer only
    zips = [
        ROOT / 'manufacturing/NM-CYD-C5-Gamepad-RevA-Gerbers.zip',
        ROOT / 'manufacturing/JLCPCB-NM-CYD-C5-Gamepad-RevA-R4.zip',
        ROOT / 'manufacturing/assembly/JLCPCB-NM-CYD-C5-RevA-R4-PCBA-Gerbers.zip',
    ]

    if not apply:
        print('\ndry run; rerun with --apply to write')
        return

    if updated != src:
        shutil.copy2(epcb, epcb.with_suffix('.epcb.prev'))
        epcb.write_text(updated)

    tmp = epro2.with_suffix('.epro2.tmp')
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for info, data in new_entries:
            z.writestr(info, data)
    tmp.replace(epro2)

    for path in zips:
        with zipfile.ZipFile(path) as z:
            items = [(i, z.read(i.filename)) for i in z.infolist()]
        out = []
        hit = 0
        for info, data in items:
            if info.filename == 'Gerber_BoardOutlineLayer.GKO':
                text = data.decode()
                before = gko_contour(text)
                text = text.replace(before, new_contour)
                data = text.encode()
                hit += 1
            out.append((info, data))
        if hit != 1:
            raise SystemExit(f'{path.name}: outline layer not found')
        tmp = path.with_suffix('.zip.tmp')
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
            for info, data in out:
                z.writestr(info, data)
        tmp.replace(path)
        print(f'{path.name}: outline layer updated')

    print('\nwritten')


if __name__ == '__main__':
    main(apply='--apply' in sys.argv)
