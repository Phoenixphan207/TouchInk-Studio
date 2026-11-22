"""Ink-only erasing and freehand-lasso geometry (no UI / OS dependencies).

Paper backgrounds are never ink objects. All destructive changes operate on
Stroke objects, not on the rendered canvas or pixels of the page template.
"""
import math
from dataclasses import replace


def sq_distance_to_segment(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    denom = vx * vx + vy * vy
    t = min(1., max(0., ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / denom)) if denom else 0.
    px, py = a[0] + t * vx, a[1] + t * vy
    return (p[0] - px) ** 2 + (p[1] - py) ** 2


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(a, b, c, d):
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    eps = 1.e-9
    if o1 * o2 < -eps and o3 * o4 < -eps:
        return True
    if abs(o1) < eps and sq_distance_to_segment(c, a, b) < eps:
        return True
    if abs(o2) < eps and sq_distance_to_segment(d, a, b) < eps:
        return True
    if abs(o3) < eps and sq_distance_to_segment(a, c, d) < eps:
        return True
    if abs(o4) < eps and sq_distance_to_segment(b, c, d) < eps:
        return True
    return False


def segment_distance2(a, b, c, d):
    if segments_intersect(a, b, c, d):
        return 0.
    return min(sq_distance_to_segment(p, aa, bb) for p, aa, bb in ((a, c, d), (b, c, d), (c, a, b), (d, a, b)))


def _box_polygon(stroke):
    x, y = stroke.points[0]
    if stroke.kind == 'text':
        w = max(1., len(stroke.text) * stroke.font_size * .63)
        return [(x, y - stroke.font_size), (x + w, y - stroke.font_size), (x + w, y), (x, y), (x, y - stroke.font_size)]
    w = stroke.box_w or 240.0
    h = stroke.box_h or 200.0
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]


def stroke_polyline(stroke):
    from engine import shape_path, arrow_wings
    if stroke.kind in ('text', 'sticky', 'image'):
        return _box_polygon(stroke)
    if stroke.kind == 'shape':
        path = shape_path(stroke.shape, stroke.points, segments=48)
        if stroke.shape == 'arrow' and len(path) >= 2:
            a, b = path[0], path[-1]
            wings = arrow_wings(a, b, max(12, stroke.width * 4))
            return path + [wings[0], b, wings[1]]
        return path
    return stroke.points


def _stroke_near_capsule(stroke, a, b, radius):
    """Broad-phase bbox + exact segment proximity. radius includes half ink width."""
    if not stroke.points:
        return False
    r = radius + max(0., stroke.width) * .5
    pts = stroke_polyline(stroke)
    if not pts:
        return False
    xmin = min(p[0] for p in pts)
    xmax = max(p[0] for p in pts)
    ymin = min(p[1] for p in pts)
    ymax = max(p[1] for p in pts)
    if xmax < min(a[0], b[0]) - r or xmin > max(a[0], b[0]) + r:
        return False
    if ymax < min(a[1], b[1]) - r or ymin > max(a[1], b[1]) + r:
        return False
    if len(pts) == 1:
        return sq_distance_to_segment(pts[0], a, b) <= r * r
    return any(segment_distance2(p, q, a, b) <= r * r for p, q in zip(pts, pts[1:]))


def erase_segment(strokes, a, b, radius):
    """Erase only ink intersecting the swept circular brush (capsule)."""
    radius = max(.5, float(radius))
    out = []
    changed = False
    for stroke in strokes:
        # Sticky notes & embedded images are protected from accidental pen erasing; delete via Select/Lasso
        if stroke.kind in ('sticky', 'image'):
            out.append(stroke)
            continue
        if not _stroke_near_capsule(stroke, a, b, radius):
            out.append(stroke)
            continue
        changed = True
        if stroke.kind in ('shape', 'text'):
            continue
        pts = stroke.points
        if len(pts) == 1:
            continue
        rr = radius + max(0., stroke.width) * .5
        rr2 = rr * rr
        segments = []
        run = []

        def outside(p):
            return sq_distance_to_segment(p, a, b) > rr2

        def finish():
            nonlocal run
            if run:
                clean = [run[0]]
                for p in run[1:]:
                    if math.dist(clean[-1], p) > 1.e-5:
                        clean.append(p)
                if clean:
                    segments.append(clean)
                run = []

        def boundary(p, q, is_outside):
            l, r = 0., 1.
            for _ in range(11):
                m = (l + r) / 2
                z = (p[0] + (q[0] - p[0]) * m, p[1] + (q[1] - p[1]) * m)
                if outside(z) == is_outside:
                    l = m
                else:
                    r = m
            m = (l + r) / 2
            return (p[0] + (q[0] - p[0]) * m, p[1] + (q[1] - p[1]) * m)

        for p, q in zip(pts, pts[1:]):
            d = math.dist(p, q)
            if segment_distance2(p, q, a, b) > rr2:
                if not run:
                    run = [p]
                run.append(q)
                continue
            steps = max(2, min(1500, math.ceil(d / max(1., rr * .28))))
            last = p
            last_out = outside(p)
            if last_out and not run:
                run = [p]
            if not last_out:
                finish()
            for i in range(1, steps + 1):
                t = i / steps
                cur = (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
                curr_out = outside(cur)
                if curr_out != last_out:
                    edge = boundary(last, cur, last_out)
                    if last_out:
                        if not run:
                            run = [last]
                        run.append(edge)
                        finish()
                    else:
                        run = [edge]
                if curr_out:
                    if not run:
                        run = [cur]
                    run.append(cur)
                last, last_out = cur, curr_out
        finish()
        for part in segments:
            out.append(replace(stroke, points=part))
    return out, changed


def _inside_polygon(point, poly):
    x, y = point
    inside = False
    for a, b in zip(poly, poly[1:] + poly[:1]):
        if sq_distance_to_segment(point, a, b) < 1.e-8:
            return True
        if (a[1] > y) != (b[1] > y):
            cross = (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]
            if x < cross:
                inside = not inside
    return inside


def polygon_area(poly):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))) * .5


def strokes_in_lasso(strokes, polygon):
    """Select objects enclosed by OR intersecting the freeform lasso outline."""
    poly = list(polygon)
    if len(poly) < 3 or polygon_area(poly) < 12:
        return []
    if math.dist(poly[0], poly[-1]) > 1.e-8:
        poly.append(poly[0])
    minx, maxx = min(p[0] for p in poly), max(p[0] for p in poly)
    miny, maxy = min(p[1] for p in poly), max(p[1] for p in poly)
    selected = []
    for stroke in strokes:
        points = stroke_polyline(stroke)
        if not points:
            continue
        sx0 = min(p[0] for p in points)
        sx1 = max(p[0] for p in points)
        sy0 = min(p[1] for p in points)
        sy1 = max(p[1] for p in points)
        if sx1 < minx or sx0 > maxx or sy1 < miny or sy0 > maxy:
            continue
        if any(_inside_polygon(p, poly) for p in points):
            selected.append(stroke)
            continue
        closed_object = (stroke.kind == 'shape' and stroke.shape in ('rectangle', 'ellipse', 'triangle')) or stroke.kind in ('text', 'sticky', 'image')
        if closed_object and any(_inside_polygon(p, points) for p in poly):
            selected.append(stroke)
            continue
        polyedges = list(zip(poly, poly[1:]))
        if any(segments_intersect(a, b, c, d) for a, b in zip(points, points[1:]) for c, d in polyedges):
            selected.append(stroke)
    return selected
