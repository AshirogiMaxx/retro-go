#!/usr/bin/env python3
"""Prepare JLCPCB assembly CSVs and paste Gerber; verify against native CAD."""
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'manufacturing/assembly'
SOURCE = OUT/'source/easyeda-native-pickplace.tsv'
DNP = {'R15', 'R16'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mm(value):
    assert value.endswith('mm'), 'Native placement export must use millimeters'
    return float(value[:-2])


native = list(csv.DictReader(io.StringIO(SOURCE.read_text(encoding='utf-16')), delimiter='\t'))
assert len(native) == 34 and len({r['Designator'] for r in native}) == 34
components = {}
references = {}
for line in (ROOT/'easyeda/controller.epcb').read_text().splitlines():
    a, b = line.rstrip('|').split('||')
    h, v = json.loads(a), json.loads(b)
    if h['type'] == 'COMPONENT':
        components[h['id']] = v
    elif h['type'] == 'ATTR' and v['key'] == 'Designator':
        references[v['value']] = v['parentId']
assert {r['Designator'] for r in native} == set(references)

# Native export centroids and CCW angles must match the actual manufacturing CAD.
for row in native:
    c = components[references[row['Designator']]]
    assert c['layerId'] == 1 and row['Layer'] == 'T'
    assert math.isclose(mm(row['Mid X']), c['x']*.0254, abs_tol=0.001)
    assert math.isclose(mm(row['Mid Y']), c['y']*.0254, abs_tol=0.001)
    assert int(row['Rotation']) % 360 == round(c['angle']) % 360
    assert 0 < mm(row['Mid X']) < 100 and -70 < mm(row['Mid Y']) < 0

rows = [r for r in native if r['Designator'] not in DNP]
assert len(rows) == 32
CPL = OUT/'JLCPCB-NM-CYD-C5-RevA-R4-CPL.csv'
with CPL.open('w', encoding='ascii', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
    for r in rows:
        writer.writerow([r['Designator'], f"{mm(r['Mid X']):.3f}mm", f"{mm(r['Mid Y']):.3f}mm", 'Top', int(r['Rotation']) % 360])

# Use expanded reference lists: JLCPCB should not need to interpret ranges.
groups = [
    ('PCA9555D,112', ['U1'], 'SO-24_L15.6-W7.6-P1.27-LS10.6-BL', 'C1542498', 'PCA9555D,112'),
    ('B3F-1000 6x6mm tactile switch', [f'SW{i}' for i in range(1,15)], 'KEY-TH_4P-L6.2-W6.2-P4.50-LS6.5', 'C93157', 'B3F-1000'),
    ('10k 1% 0603', [f'R{i}' for i in range(1,15)], 'R0603', 'C25804', '0603WAF1002T5E'),
    ('100nF 50V X7R 0603', ['C1','C2'], 'C0603', 'C14663', 'CC0603KRX7R9BB104'),
    ('PZ254V-11-04P 1x4 header', ['J1'], 'HDR-TH_4P-P2.54-V-M', 'C2691448', 'PZ254V-11-04P'),
]
byref = {r['Designator']:r for r in rows}
BOM = OUT/'JLCPCB-NM-CYD-C5-RevA-R4-BOM.csv'
with BOM.open('w', encoding='ascii', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #', 'Quantity'])
    for comment, refs, footprint, lcsc, device in groups:
        for ref in refs:
            assert byref[ref]['Device'] == device and byref[ref]['Footprint'] == footprint
        writer.writerow([comment, ','.join(refs), footprint, lcsc, len(refs)])

# Re-read exactly what the customer will upload; match reference sets and quantities.
with CPL.open(newline='') as f:
    uploaded_cpl = list(csv.DictReader(f))
with BOM.open(newline='') as f:
    uploaded_bom = list(csv.DictReader(f))
cpl_refs = {r['Designator'] for r in uploaded_cpl}
bom_refs = [ref for r in uploaded_bom for ref in r['Designator'].split(',')]
assert len(bom_refs) == len(set(bom_refs)) == len(uploaded_cpl) == 32
assert cpl_refs == set(bom_refs) and not cpl_refs.intersection(DNP)
assert sum(int(r['Quantity']) for r in uploaded_bom) == 32
for row in uploaded_bom:
    assert int(row['Quantity']) == len(row['Designator'].split(','))

# Pin 1 is checked against the actual pad positions, not inferred from the footprint's name.
reported = {c['ref']:c for c in json.loads((ROOT/'reports/pcb-components.json').read_text())}
for ref in ['U1','J1']:
    r = byref[ref]
    pin1 = next(p for p in reported[ref]['pins'] if p['num'] == '1')
    assert math.isclose(mm(r['Pad X']), pin1['x']*.0254, abs_tol=.002)
    assert math.isclose(mm(r['Pad Y']), pin1['y']*.0254, abs_tol=.002)
u1pin1 = next(p for p in reported['U1']['pins'] if p['num'] == '1')
assert u1pin1['x']*.0254 < 50 and u1pin1['y']*.0254 > -36
assert byref['U1']['Rotation'] == '270'

# Keep the original paste shapes and remove only the four DNP pad openings.
# Native custom resistor paste polygons are slightly offset from copper-pad
# centers; associate them to the nearest unique pad within 0.1 mm.
PASTE_SOURCE = OUT/'source/easyeda-native-top-paste.GTP'
paste_source = PASTE_SOURCE.read_text()
assert '%FSLAX45Y45*%' in paste_source and '%MOMM*%' in paste_source
smt_pads = {
    (r['Designator'], p['num']): (p['x']*.0254, p['y']*.0254)
    for r in native if r['SMD'] == 'Yes'
    for p in reported[r['Designator']]['pins']
}
assert len(smt_pads) == 60


def paste_openings(source):
    openings = []
    pattern = r'G36\*.*?G37\*|G01X(-?\d+)Y(-?\d+)D03\*'
    for match in re.finditer(pattern, source, re.S):
        if match.group(1) is not None:
            center = tuple(int(match.group(i))/1e5 for i in (1, 2))
        else:
            points = [(int(x)/1e5, int(y)/1e5) for x, y in re.findall(
                r'X(-?\d+)Y(-?\d+)D0[12]\*', match.group())]
            assert points and points[0] == points[-1]
            xs, ys = zip(*points)
            center = ((min(xs)+max(xs))/2, (min(ys)+max(ys))/2)
        pad = min(smt_pads, key=lambda key: math.dist(center, smt_pads[key]))
        offset = math.dist(center, smt_pads[pad])
        assert offset < .1, f'Unmatched paste opening at {center}'
        openings.append((match.start(), match.end(), pad, offset))
    assert len(openings) == source.count('G36*') + source.count('D03*')
    assert len({pad for _, _, pad, _ in openings}) == len(openings)
    return openings


original_openings = paste_openings(paste_source)
assert {pad for _, _, pad, _ in original_openings} == set(smt_pads)
filtered_paste = paste_source
removed = []
for start, end, pad, _ in reversed(original_openings):
    if pad[0] in DNP:
        filtered_paste = filtered_paste[:start] + filtered_paste[end:]
        removed.append(pad)
assert set(removed) == {(ref, pin) for ref in DNP for pin in ('1', '2')}
filtered_paste = filtered_paste.replace('G04 Layer: TopPasteMaskLayer*',
    'G04 Layer: TopPasteMaskLayer*\nG04 Assembly variant: R15 and R16 DNP; paste openings omitted*')
fitted_openings = paste_openings(filtered_paste)
assert len(fitted_openings) == 56
assert {pad for _, _, pad, _ in fitted_openings} == {p for p in smt_pads if p[0] not in DNP}

# All nine bare-board layers remain byte-identical, including the R4 outline.
BARE_GERBERS = ROOT/'manufacturing/JLCPCB-NM-CYD-C5-Gamepad-RevA-R4.zip'
PCBA_GERBERS = OUT/'JLCPCB-NM-CYD-C5-RevA-R4-PCBA-Gerbers.zip'
with zipfile.ZipFile(BARE_GERBERS) as bare, zipfile.ZipFile(PCBA_GERBERS, 'w', zipfile.ZIP_DEFLATED) as assembly:
    assert len(bare.namelist()) == 9 and not any(n.endswith('.GTP') for n in bare.namelist())
    for info in bare.infolist():
        assembly.writestr(info, bare.read(info.filename))
    info = zipfile.ZipInfo('Gerber_TopPasteMaskLayer.GTP', date_time=(2026, 10, 30, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    assembly.writestr(info, filtered_paste.encode('ascii'))
with zipfile.ZipFile(BARE_GERBERS) as bare, zipfile.ZipFile(PCBA_GERBERS) as assembly:
    assert len(assembly.namelist()) == 10
    assert all(bare.read(n) == assembly.read(n) for n in bare.namelist())
    assert assembly.read('Gerber_TopPasteMaskLayer.GTP') == filtered_paste.encode('ascii')

report = {
    'date': '2026-10-30', 'source': str(SOURCE.relative_to(ROOT)),
    'native_centroids_and_rotations_match_cad': True,
    'cpl_and_bom_reference_sets_match': True,
    'populated_components': 32, 'unique_part_types': 5,
    'smt_components': sum(r['SMD']=='Yes' for r in rows),
    'through_hole_components': sum(r['SMD']=='No' for r in rows),
    'excluded_dnp': sorted(DNP), 'assembly_side': 'Top',
    'coordinate_frame': 'Same as Gerbers: origin at upper left, X right, Y up; board Y spans -70 to 0 mm',
    'rotation_convention': 'Native EasyEDA footprint angle, positive counterclockwise',
    'u1_rotation_deg': 270, 'u1_pin1_mm': [mm(byref['U1']['Pad X']), mm(byref['U1']['Pad Y'])],
    'u1_expected_orientation': 'Notch toward cable header; pin 1 at upper-left in top view',
    'assembly_gerber_zip': str(PCBA_GERBERS.relative_to(ROOT)),
    'bare_board_layers_byte_identical': True,
    'paste_openings': 56, 'native_paste_openings': 60,
    'dnp_paste_openings_removed': ['R15.1', 'R15.2', 'R16.1', 'R16.2'],
    'paste_openings_match_fitted_smt_pads': True,
    'maximum_native_paste_center_to_pad_offset_mm': round(max(o[3] for o in original_openings), 6),
    'jlcpcb_placement_preview_reviewed': False,
    'parts_stock_reserved': False,
    'sha256': {str(p.relative_to(ROOT)):sha(p) for p in [SOURCE,PASTE_SOURCE,CPL,BOM,BARE_GERBERS,PCBA_GERBERS]},
}
(ROOT/'reports/pcba-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
