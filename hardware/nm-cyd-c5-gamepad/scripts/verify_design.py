#!/usr/bin/env python3
"""Check actual exported CAD connections, manufacturing dimensions and optional firmware baseline."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--firmware-baseline', type=Path)
parser.add_argument('--report', type=Path)
args = parser.parse_args()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(source):
    result = []
    for line in source.splitlines():
        a, b = line.rstrip('|').split('||')
        result.append((json.loads(a), json.loads(b)))
    return result


buttons = ['UP', 'RIGHT', 'DOWN', 'LEFT', 'SELECT', 'START', 'MENU', 'OPTION', 'A', 'B', 'X', 'Y', 'L', 'R']
expected = defaultdict(set)
for i, name in enumerate(buttons):
    expected['BTN_' + name] = {f'U1-{i+4 if i < 8 else i+5}', f'SW{i+1}-1', f'SW{i+1}-2', f'R{i+1}-1'}
expected['GND'] = {'U1-2', 'U1-3', 'U1-12', 'U1-21', 'J1-4', 'C1-1', 'C2-1'}
expected['GND'].update(f'SW{i}-{n}' for i in range(1, 15) for n in [3, 4])
expected['+3V3'] = {'U1-24', 'J1-1', 'C1-2', 'C2-2'}
expected['+3V3'].update(f'R{i}-2' for i in range(1, 17))
expected['SDA'] = {'U1-23', 'J1-2', 'R15-1'}
expected['SCL'] = {'U1-22', 'J1-3', 'R16-1'}

netlist = (ROOT/'easyeda/controller.net').read_text()
actual = {}
for block in re.findall(r'\(\s*\n(.*?)\n\)', netlist, re.S):
    lines = block.strip().splitlines()
    actual[lines[0].strip()] = {line.split()[0] for line in lines[1:]}
assert actual == expected, 'Schematic connections differ from the datasheet/button map'
components = json.loads((ROOT/'reports/pcb-components.json').read_text())
pcb_nets = defaultdict(set)
for c in components:
    for pad in c['pins']:
        if pad['net']:
            pcb_nets[pad['net']].add(c['ref'] + '-' + pad['num'])
        else:
            assert c['ref'] == 'U1' and pad['num'] in ['1', '19', '20']
assert pcb_nets == expected, 'PCB pad assignments differ from schematic'
assert len(components) == 34
source = (ROOT/'easyeda/controller.epcb').read_text()
rows = records(source)
assert sum(h['type'] == 'COMPONENT' for h, _ in rows) == 34
tracks = [v for h, v in rows if h['type'] == 'LINE' and v.get('layerId') in [1, 2]]
assert len(tracks) > 0 and min(v['width'] for v in tracks) >= 10 - 1e-6
assert {v['netName'] for v in tracks} == set(expected)
assert sum(h['type'] == 'VIA' for h, _ in rows) == 18
assert sum(h['type'] == 'PAD' for h, _ in rows) == 4
outlines = [v for h, v in rows if h['type'] == 'POLY' and v.get('layerId') == 11]
assert len(outlines) == 1, 'Expected one closed board outline'
to_mm = lambda value: value * .0254   # board outline paths are stored in mil
# The outline is the SNES-style dog bone recorded by scripts/snes_outline.py: 100 x 70 mm,
# 7 mm corner radii, a 3 mm scoop across the top centre and a 8.2 mm scoop across the bottom.
shape = json.loads((ROOT/'reports/snes-outline-path.json').read_text())
snes_path = shape['path']
def same_path(path):
    return len(path) == len(snes_path) and all(
        a == b if isinstance(b, str) else math.isclose(a, b, abs_tol=1e-3)
        for a, b in zip(path, snes_path))
assert same_path(outlines[0]['path']), 'Expected the recorded SNES-style dog-bone outline'
assert shape['corner_radius_mm'] == 7 and shape['top_scoop_mm'] == 3 and shape['bottom_scoop_mm'] == 8.2

drc = json.loads((ROOT/'reports/easyeda-drc.json').read_text())
assert drc['passed'] is True and drc['errors'] == [], 'EasyEDA DRC failed'

# Check the self-contained archive against the sources actually inspected.
project = ROOT/'easyeda/NM-CYD-C5-Gamepad-RevA.epro2'
with zipfile.ZipFile(project) as z:
    epru = next(n for n in z.namelist() if n.endswith('.epru'))
    archived = records(z.read(epru).decode())
    documents = [v for h, v in archived if h['type'] == 'DOCHEAD']
    assert sum(v['docType'] == 'PCB' for v in documents) == 1
    assert sum(v['docType'] == 'FOOTPRINT' for v in documents) >= 5
    assert sum(v['docType'] == 'SCH_PAGE' for v in documents) >= 1
    doc = None
    board = []
    for h, v in archived:
        if h['type'] == 'DOCHEAD':
            doc = v['uuid']
        if doc == '7f423eabe62144d5':
            board.append((h, v))
    assert sum(h['type'] == 'COMPONENT' for h, _ in board) == 34
    assert {h['id'] for h, v in board if h['type'] == 'COMPONENT'} == {c['id'] for c in components}
    archived_outline = [v for h, v in board if h['type'] == 'POLY' and v.get('layerId') == 11]
    assert len(archived_outline) == 1 and same_path(archived_outline[0]['path'])


def drills(text):
    tools = {}
    hits = Counter()
    current = None
    for line in text.splitlines():
        m = re.fullmatch(r'(T\d+)C([\d.]+)', line)
        if m:
            tools[m[1]] = float(m[2])
        elif re.fullmatch(r'T\d+', line):
            current = line
        elif line.startswith('X'):
            hits[round(tools[current], 3)] += 1
    return dict(hits)


gerber = ROOT/'manufacturing/NM-CYD-C5-Gamepad-RevA-Gerbers.zip'
with zipfile.ZipFile(gerber) as z:
    outline = z.read('Gerber_BoardOutlineLayer.GKO').decode()
    assert '%MOMM*%' in outline and '%FSLAX45Y45*%' in outline
    operations = []
    for g, x, y, i, j, d in re.findall(
            r'(G0[123])X(-?\d+)Y(-?\d+)(?:I(-?\d+)J(-?\d+))?D0([12])\*', outline):
        operations.append((g, int(x)/1e5, int(y)/1e5,
                           int(i)/1e5 if i else None, int(j)/1e5 if j else None, int(d)))
    # The Gerber boundary must walk the same vertices, in the same order, as the board outline.
    path_points = [(to_mm(snes_path[0]), to_mm(snes_path[1]))]
    index = 2
    while index < len(snes_path):
        token = snes_path[index]
        step = 3 if token == 'L' else 4
        path_points.append((to_mm(snes_path[index + step - 2]), to_mm(snes_path[index + step - 1])))
        index += step
    gerber_points = [(operations[0][1], operations[0][2])] + [(o[1], o[2]) for o in operations[1:]]
    assert len(gerber_points) == len(path_points), 'Gerber outline vertex count differs from the board outline'
    assert all(math.isclose(a[0], b[0], abs_tol=2e-3) and math.isclose(a[1], b[1], abs_tol=2e-3)
               for a, b in zip(gerber_points, path_points)), 'Gerber outline vertices differ from the board outline'
    radii = sorted(round(math.hypot(o[3], o[4]), 2) for o in operations if o[0] != 'G01')
    assert radii == [7.0] * 4 + [18.18] * 4 + [24.83] * 4, f'Unexpected outline arc radii: {radii}'
    assert sum(o[0] != 'G01' for o in operations) == 12, 'Expected 12 arcs (4 corners + 8 shoulder arcs)'
    pth = drills(z.read('Drill_PTH_Through.DRL').decode())
    npth = drills(z.read('Drill_NPTH_Through.DRL').decode())
    assert pth == {0.305: 18, 1.1: 60}, pth
    assert npth == {3.2: 4}, npth
    mounting_holes = {(float(x), float(y)) for x, y in re.findall(
        r'^X([\d.]+)Y(-?[\d.]+)$', z.read('Drill_NPTH_Through.DRL').decode(), re.M)}
    assert mounting_holes == {(4, -4), (96, -4), (4, -66), (96, -66)}
    assert 'Drill_PTH_Through_Via.DRL' not in z.namelist()

firmware = {'checked': False}
if args.firmware_baseline:
    baseline = json.loads(args.firmware_baseline.read_text())
    repo = ROOT.parents[1]
    for name, digest in baseline.items():
        file = repo/name
        assert file.is_file() and sha(file) == digest, 'Changed outside hardware: ' + name
    current = set(subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=repo).decode().strip('\0').split('\0'))
    current = {s for s in current if not s.startswith('hardware/nm-cyd-c5-gamepad/')}
    assert current == set(baseline), 'Files added or removed outside hardware folder'
    image = repo/'retro-go_1.46-8-g4ced1-dirty_nm-cyd-c5.img'
    assert sha(image) == '4d8a3d6e491618d61533c28c0ab257caa6dffa9781f7c33ef849ed64d2dc27c1'
    firmware = {'checked': True, 'unchanged_files': len(baseline), 'flash_image_sha256': sha(image), 'flashed_during_pcb_design': False}

report = {
    'date': drc['date'], 'cad_tool': 'EasyEDA 3.2.209', 'strict_drc_passed': True,
    'drc_errors': 0, 'nets': len(expected), 'connected_pins': sum(map(len, expected.values())),
    'components_including_dnp': len(components), 'populated_components': 32,
    'copper_track_segments': len(tracks), 'min_track_width_mm': round(min(v['width'] for v in tracks)*.0254, 4),
    'vias': 18, 'outline_mm': [100, 70], 'corner_radius_mm': shape['corner_radius_mm'],
    'outline_style': 'SNES-style dog bone with scooped waist',
    'top_scoop_depth_mm': shape['top_scoop_mm'], 'bottom_scoop_depth_mm': shape['bottom_scoop_mm'],
    'min_copper_edge_clearance_mm': shape['min_copper_edge_clearance_mm'],
    'min_mounting_hole_edge_clearance_mm': 1.16, 'pth_drills_by_diameter_mm': pth,
    'npth_drills_by_diameter_mm': npth, 'schematic_and_pcb_match': True,
    'archive_contains_footprints_and_symbols': True,
    'hardware_tested': False, 'host_connector_mechanical_fit_verified': False,
    'firmware': firmware,
    'sha256': {str(project.relative_to(ROOT)): sha(project), str(gerber.relative_to(ROOT)): sha(gerber)},
}
if args.report:
    args.report.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
