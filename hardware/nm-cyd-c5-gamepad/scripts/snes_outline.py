#!/usr/bin/env python3
"""Generate a SNES-style dog-bone board outline for the NM-CYD-C5 button controller.

Works in millimetres with y growing DOWN from the top edge (EasyEDA stores it negated).
Emits an EasyEDA polygon path (L / ARC segments only, mil units) and verifies that every
piece of copper and every mounting hole stays on the board with margin.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIL = 39.37007874015748

# ---- board envelope (documented 100 x 70 mm) --------------------------------
W, H = 100.0, 70.0
R_CORNER = 7.0          # limited by the 3.2 mm mounting holes 4 mm from each corner
TOP_START, TOP_END = 28.0, 72.0     # top scoop x range
TOP_DEPTH = 3.0                     # J1 pads start at y = 4.15 mm
BOT_START, BOT_END = 22.0, 78.0     # bottom scoop x range
BOT_DEPTH = 8.2                     # waist bottom 61.8 mm; SW5/SW6 pads end at 61.15 mm


def s_curve(x0, y0, x1, y1):
    """Two tangent arcs forming an S between two horizontal lines.

    Returns [(centre, start, end), (centre, start, end)] with y growing down.
    """
    dx, dy = x1 - x0, y1 - y0
    w, d = abs(dx), abs(dy)
    theta = 2.0 * math.atan(d / w)
    r = d / (2.0 * (1.0 - math.cos(theta)))
    s = 1.0 if dx > 0 else -1.0          # direction of travel along x
    v = 1.0 if dy > 0 else -1.0          # scoop direction (down = +)
    mid = (x0 + s * r * math.sin(theta), y0 + v * r * (1.0 - math.cos(theta)))
    c1 = (x0, y0 + v * r)
    c2 = (x1, y1 - v * r)
    return [(c1, (x0, y0), mid), (c2, mid, (x1, y1))]


def build():
    segs = []          # ('L', p) or ('A', centre, start, end)

    def line(p):
        segs.append(('L', p))

    def arc(centre, start, end):
        segs.append(('A', centre, start, end))

    # clockwise from the top-left corner tangent point
    start = (R_CORNER, 0.0)
    line((TOP_START, 0.0))
    for c, s0, s1 in s_curve(TOP_START, 0.0, 45.0, TOP_DEPTH):
        arc(c, s0, s1)
    line((55.0, TOP_DEPTH))
    for c, s0, s1 in s_curve(55.0, TOP_DEPTH, TOP_END, 0.0):
        arc(c, s0, s1)
    line((W - R_CORNER, 0.0))
    arc((W - R_CORNER, R_CORNER), (W - R_CORNER, 0.0), (W, R_CORNER))
    line((W, H - R_CORNER))
    arc((W - R_CORNER, H - R_CORNER), (W, H - R_CORNER), (W - R_CORNER, H))
    line((BOT_END, H))
    for c, s0, s1 in s_curve(BOT_END, H, 55.0, H - BOT_DEPTH):
        arc(c, s0, s1)
    line((45.0, H - BOT_DEPTH))
    for c, s0, s1 in s_curve(45.0, H - BOT_DEPTH, BOT_START, H):
        arc(c, s0, s1)
    line((R_CORNER, H))
    arc((R_CORNER, H - R_CORNER), (R_CORNER, H), (0.0, H - R_CORNER))
    line((0.0, R_CORNER))
    arc((R_CORNER, R_CORNER), (0.0, R_CORNER), start)
    return start, segs


def flatten(start, segs, step_deg=2.0):
    pts = [start]
    cur = start
    for seg in segs:
        if seg[0] == 'L':
            cur = seg[1]
            pts.append(cur)
        else:
            _, c, s0, s1 = seg
            a0 = math.atan2(s0[1] - c[1], s0[0] - c[0])
            a1 = math.atan2(s1[1] - c[1], s1[0] - c[0])
            r = math.hypot(s0[0] - c[0], s0[1] - c[1])
            d = a1 - a0
            while d > math.pi:
                d -= 2 * math.pi
            while d < -math.pi:
                d += 2 * math.pi
            n = max(6, int(abs(math.degrees(d)) / step_deg) + 1)
            for k in range(1, n + 1):
                a = a0 + d * k / n
                pts.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
            cur = s1
    return pts


def to_easyeda(start, segs):
    """Emit the EasyEDA path array (mil, y negated)."""
    out = [round(start[0] * MIL, 4), round(-start[1] * MIL, 4)]
    for seg in segs:
        if seg[0] == 'L':
            out += ['L', round(seg[1][0] * MIL, 4), round(-seg[1][1] * MIL, 4)]
        else:
            _, c, s0, s1 = seg
            a0 = math.atan2(s0[1] - c[1], s0[0] - c[0])
            a1 = math.atan2(s1[1] - c[1], s1[0] - c[0])
            d = a1 - a0
            while d > math.pi:
                d -= 2 * math.pi
            while d < -math.pi:
                d += 2 * math.pi
            # EasyEDA: negative angle = clockwise on screen; screen y is negated
            out += ['ARC', round(math.degrees(-d), 4),
                    round(s1[0] * MIL, 4), round(-s1[1] * MIL, 4)]
    return out


# ---- clearance checks -------------------------------------------------------
def inside(pts, x, y):
    c = False
    n = len(pts)
    for j in range(n):
        x1, y1 = pts[j]
        x2, y2 = pts[(j + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                c = not c
    return c


def dist_to_boundary(pts, x, y):
    best = 1e9
    n = len(pts)
    for j in range(n):
        x1, y1 = pts[j]
        x2, y2 = pts[(j + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
        px, py = x1 + t * dx, y1 + t * dy
        best = min(best, math.hypot(x - px, y - py))
    return best


def copper_points():
    """(x_mm, y_mm_from_top, half_extent_mm, label) for every conductive feature."""
    rows = []
    for line in (ROOT / 'easyeda/controller.epcb').read_text().splitlines():
        line = line.strip()
        if not line or '||' not in line:
            continue
        a, _, b = line.partition('||')
        try:
            rows.append((json.loads(a), json.loads(b.rstrip('|'))))
        except Exception:
            pass
    out = []
    for h, v in rows:
        if h['type'] == 'LINE' and v['layerId'] in (1, 2):
            for x, y in ((v['startX'], v['startY']), (v['endX'], v['endY'])):
                out.append((x * 0.0254, -y * 0.0254, v['width'] * 0.0254 / 2, 'track ' + v.get('netName', '')))
        if h['type'] == 'VIA':
            out.append((v['centerX'] * 0.0254, -v['centerY'] * 0.0254,
                        v['viaDiameter'] * 0.0254 / 2, 'via'))
    for c in json.loads((ROOT / 'reports/pcb-components.json').read_text()):
        for p in c['pins']:
            w, hh = p['pad'][1], p['pad'][2]
            out.append((p['x'] * 0.0254, -p['y'] * 0.0254, max(w, hh) * 0.0254 / 2,
                        f"{c['ref']}-{p['num']}"))
    return out


def main():
    start, segs = build()
    pts = flatten(start, segs)
    path = to_easyeda(start, segs)

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    print(f'outline bbox {max(xs)-min(xs):.3f} x {max(ys)-min(ys):.3f} mm '
          f'(x {min(xs):.2f}..{max(xs):.2f}, y {min(ys):.2f}..{max(ys):.2f})')
    print(f'segments: {sum(1 for s in segs if s[0]=="L")} lines, '
          f'{sum(1 for s in segs if s[0]=="A")} arcs')

    worst = []
    outside = []
    for x, y, r, label in copper_points():
        edges = [(x + r * math.cos(a), y + r * math.sin(a))
                 for a in [k * math.pi / 8 for k in range(16)]]
        for ex, ey in edges:
            if not inside(pts, ex, ey):
                outside.append((label, x, y, r))
                break
        d = dist_to_boundary(pts, x, y) - r
        worst.append((d, label, x, y))
    worst.sort()
    print('\nclosest copper to the new edge:')
    for d, label, x, y in worst[:8]:
        print(f'  {d:6.2f} mm  {label:10s} at ({x:6.2f}, {y:6.2f})')
    print('copper outside outline:', len(outside), sorted({o[0] for o in outside})[:10])

    print('\nmounting holes:')
    for hx, hy in ((4, 4), (96, 4), (4, 66), (96, 66)):
        d = dist_to_boundary(pts, hx, hy) - 1.6
        print(f'  ({hx:>3},{hy:>3}) edge clearance {d:.2f} mm  inside={inside(pts, hx, hy)}')

    (ROOT / 'reports/snes-outline-path.json').write_text(json.dumps({
        'units': 'mil', 'y_note': 'negated (EasyEDA canvas)',
        'bbox_mm': [round(max(xs) - min(xs), 4), round(max(ys) - min(ys), 4)],
        'corner_radius_mm': R_CORNER, 'top_scoop_mm': TOP_DEPTH, 'bottom_scoop_mm': BOT_DEPTH,
        'min_copper_edge_clearance_mm': round(worst[0][0], 3),
        'path': path}, indent=1))

    # ascii preview
    Wc, Hc = 110, 34
    grid = [[' '] * Wc for _ in range(Hc)]
    for gy in range(Hc):
        y = H * gy / (Hc - 1)
        for gx in range(Wc):
            x = W * gx / (Wc - 1)
            grid[gy][gx] = '.' if inside(pts, x, y) else ' '
    for x, y, r, label in copper_points():
        gx = int(round(x / W * (Wc - 1)))
        gy = int(round(y / H * (Hc - 1)))
        if 0 <= gx < Wc and 0 <= gy < Hc:
            grid[gy][gx] = '*' if inside(pts, x, y) else 'X'
    for hx, hy in ((4, 4), (96, 4), (4, 66), (96, 66)):
        grid[int(round(hy / H * (Hc - 1)))][int(round(hx / W * (Wc - 1)))] = 'O'
    print('\npreview (O mounting hole, * copper, X copper outside board):')
    for row in grid:
        print(''.join(row))
    print('\npath written to reports/snes-outline-path.json')


if __name__ == '__main__':
    main()
