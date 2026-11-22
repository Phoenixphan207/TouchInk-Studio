"""Device-independent geometry, undoable vector strokes, sticky notes, images, and export."""
from dataclasses import dataclass, field
from xml.sax.saxutils import escape
import base64
import io
import math

PAGE_W, PAGE_H = 1240, 1754
SHAPES = ('line', 'arrow', 'rectangle', 'ellipse', 'triangle')
PAPER_TYPES = ('ruled', 'grid', 'blank')


def clamp(v, lo=0, hi=1):
    return max(lo, min(hi, v))


def point_to_page(u, v, origin, zoom, pad_ratio, *, page=(PAGE_W, PAGE_H), footprint=0.60):
    """Map raw absolute touchpad fractions to document pixels; preserve physical X:Y."""
    span_x = page[0] * footprint / max(0.25, float(zoom))
    span_y = span_x / max(0.3, float(pad_ratio))
    return origin[0] + u * span_x, origin[1] + v * span_y


def default_origin(zoom=2, page=(PAGE_W, PAGE_H)):
    return [page[0] * 0.09, page[1] * 0.10]


def window_span(zoom, pad_ratio, page=(PAGE_W, PAGE_H), footprint=0.60):
    x = page[0] * footprint / max(0.25, float(zoom))
    return x, x / max(0.3, float(pad_ratio))


def advance_origin(origin, zoom, pad_ratio, direction='right', overlap=0.16, page=(PAGE_W, PAGE_H)):
    w, h = window_span(zoom, pad_ratio, page)
    overlap = clamp(overlap, .05, .5)
    x, y = origin
    if direction == 'right':
        x += w * (1 - overlap)
    elif direction == 'left':
        x -= w * (1 - overlap)
    elif direction == 'newline':
        x = page[0] * .09
        y += h * .82
    elif direction == 'up':
        x = page[0] * .09
        y -= h * .82
    else:
        raise ValueError('Unknown direction')
    return [clamp(x, 0, max(0, page[0] - w)), clamp(y, 0, max(0, page[1] - h))]


def shape_path(shape, points, segments=36):
    """Canonical polygon/polyline vertices for both canvas and SVG/raster export."""
    if len(points) < 2:
        return list(points)
    (x1, y1), (x2, y2) = points[0], points[-1]
    if shape in ('line', 'arrow'):
        return [(x1, y1), (x2, y2)]
    if shape == 'rectangle':
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
    if shape == 'triangle':
        return [((x1 + x2) / 2, y1), (x2, y2), (x1, y2), ((x1 + x2) / 2, y1)]
    if shape == 'ellipse':
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        rx, ry = abs(x2 - x1) / 2, abs(y2 - y1) / 2
        return [(cx + rx * math.cos(i * 2 * math.pi / segments), cy + ry * math.sin(i * 2 * math.pi / segments))
                for i in range(segments + 1)]
    raise ValueError('Invalid shape: ' + str(shape))


def arrow_wings(a, b, size):
    x1, y1 = a
    x2, y2 = b
    ang = math.atan2(y2 - y1, x2 - x1)
    return [(x2 - size * math.cos(ang - .52), y2 - size * math.sin(ang - .52)),
            (x2 - size * math.cos(ang + .52), y2 - size * math.sin(ang + .52))]


@dataclass
class Stroke:
    color: str
    width: float
    erase: bool = False
    points: list = field(default_factory=list)
    kind: str = 'pen'
    shape: str = ''
    text: str = ''
    font_size: float = 28.0
    box_w: float = 0.0
    box_h: float = 0.0
    image_b64: str = ''


class Drawing:
    def __init__(self):
        self.strokes = []
        self.redo = []
        self.active = None
        self._actions = []
        self._erase_before = None

    def _record(self, action):
        self._actions.append(action)
        self.redo.clear()

    def start_eraser(self):
        """Begin one undoable brush gesture; never add a white paint stroke."""
        self.end()
        if self._erase_before is not None:
            self.finish_eraser()
        self._erase_before = list(self.strokes)

    def erase_to(self, a, b, radius):
        from ink_edit import erase_segment
        after, changed = erase_segment(self.strokes, a, b, radius)
        if changed:
            self.strokes = after
        return changed

    def finish_eraser(self):
        if self._erase_before is None:
            return False
        before = self._erase_before
        self._erase_before = None
        if len(before) == len(self.strokes) and all(a is b for a, b in zip(before, self.strokes)):
            return False
        self._record(('replace_all', before, list(self.strokes)))
        return True

    def delete_strokes(self, selected):
        """Delete selected objects as one atomic Undo/Redo action."""
        self.end()
        selected_ids = {id(s) for s in selected}
        before = list(self.strokes)
        self.strokes = [s for s in self.strokes if id(s) not in selected_ids]
        if len(before) != len(self.strokes):
            self._record(('replace_all', before, list(self.strokes)))
            return len(before) - len(self.strokes)
        return 0

    def begin(self, x, y, color='#12263e', width=3, erase=False, kind='pen', shape=''):
        self.end()
        if kind == 'shape' and shape not in SHAPES:
            raise ValueError('Unknown drawing shape')
        self.active = Stroke(color, width, erase, [(float(x), float(y))], kind, shape)
        self.strokes.append(self.active)

    def move(self, x, y, min_distance=.65):
        if not self.active:
            return False
        point = (float(x), float(y))
        if self.active.kind == 'shape':
            if len(self.active.points) == 1:
                self.active.points.append(point)
            else:
                self.active.points[-1] = point
            return True
        if math.dist(point, self.active.points[-1]) >= min_distance:
            self.active.points.append(point)
            return True
        return False

    def end(self):
        if self.active:
            self._record(('add', self.active))
            self.active = None

    def add_text(self, x, y, text, color='#111827', font_size=28):
        self.end()
        s = Stroke(color, 1, False, [(float(x), float(y))], 'text', '', str(text), float(font_size))
        self.strokes.append(s)
        self._record(('add', s))
        return s

    def add_sticky(self, x, y, text, color='#fef08a', box_w=240.0, box_h=200.0, font_size=22.0):
        self.end()
        s = Stroke(color, 1, False, [(float(x), float(y))], 'sticky', '', str(text),
                   float(font_size), float(box_w), float(box_h))
        self.strokes.append(s)
        self._record(('add', s))
        return s

    def add_image(self, x, y, image_b64, box_w, box_h):
        self.end()
        s = Stroke('#ffffff', 1, False, [(float(x), float(y))], 'image', '', '',
                   20.0, float(box_w), float(box_h), str(image_b64))
        self.strokes.append(s)
        self._record(('add', s))
        return s

    def move_stroke(self, stroke, dx, dy, record=True):
        if stroke not in self.strokes:
            return
        old = list(stroke.points)
        stroke.points = [(x + dx, y + dy) for x, y in old]
        if record and (dx or dy):
            self._record(('move', stroke, old, list(stroke.points)))

    def delete_stroke(self, stroke):
        self.end()
        if stroke in self.strokes:
            idx = self.strokes.index(stroke)
            self.strokes.pop(idx)
            self._record(('delete', stroke, idx))

    def undo(self):
        self.end()
        self.finish_eraser()
        if not self._actions:
            return
        action = self._actions.pop()
        typ = action[0]
        if typ == 'replace_all':
            self.strokes = list(action[1])
            self.redo.append(action)
            return
        _, stroke, *rest = action
        if typ == 'add':
            if stroke in self.strokes:
                self.strokes.remove(stroke)
        elif typ == 'delete':
            self.strokes.insert(min(rest[0], len(self.strokes)), stroke)
        elif typ == 'move':
            stroke.points = list(rest[0])
        self.redo.append(action)

    def redo_one(self):
        self.end()
        self.finish_eraser()
        if not self.redo:
            return
        action = self.redo.pop()
        typ = action[0]
        if typ == 'replace_all':
            self.strokes = list(action[2])
            self._actions.append(action)
            return
        _, stroke, *rest = action
        if typ == 'add':
            self.strokes.append(stroke)
        elif typ == 'delete':
            if stroke in self.strokes:
                self.strokes.remove(stroke)
        elif typ == 'move':
            stroke.points = list(rest[1])
        self._actions.append(action)

    def clear(self):
        self.end()
        self.delete_strokes(list(self.strokes))

    def restore_undo_for_loaded_page(self):
        self._actions = [('add', s) for s in self.strokes]
        self.redo.clear()


def _points(s):
    return shape_path(s.shape, s.points) if s.kind == 'shape' else s.points


def _visible_strokes(drawing):
    """Resolve legacy white-cover erasers into true ink removal for exports."""
    from ink_edit import erase_segment
    current = []
    for s in drawing.strokes:
        if s.kind == 'eraser' or s.erase:
            pts = s.points
            for a, b in zip(pts, pts[1:]):
                current, _ = erase_segment(current, a, b, s.width / 2)
            if len(pts) == 1:
                current, _ = erase_segment(current, pts[0], pts[0], s.width / 2)
        else:
            current.append(s)
    return current


def make_svg(drawing, width=PAGE_W, height=PAGE_H, paper='blank'):
    r = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
         f'<rect width="{width}" height="{height}" fill="white"/>']
    if paper == 'ruled':
        for y in range(138, height, 67):
            r.append(f'<line x1="38" y1="{y}" x2="{width - 30}" y2="{y}" stroke="#d6e7fb"/>')
        r.append(f'<line x1="74" y1="34" x2="74" y2="{height - 25}" stroke="#e8a2b8"/>')
    elif paper == 'grid':
        for x in range(0, width, 48):
            r.append(f'<path d="M{x} 0 V{height}" stroke="#edf1f9"/>')
        for y in range(0, height, 48):
            r.append(f'<path d="M0 {y} H{width}" stroke="#edf1f9"/>')
    for s in _visible_strokes(drawing):
        pts = _points(s)
        if not pts:
            continue
        color = '#ffffff' if s.erase or s.kind == 'eraser' else escape(s.color)
        opacity = ' opacity="0.35"' if s.kind == 'highlighter' else ''
        if s.kind == 'image' and s.image_b64:
            x, y = s.points[0]
            r.append(f'<image x="{x:.2f}" y="{y:.2f}" width="{s.box_w:.2f}" height="{s.box_h:.2f}" href="data:image/png;base64,{s.image_b64}"/>')
        elif s.kind == 'sticky':
            x, y = s.points[0]
            w = s.box_w or 240
            h = s.box_h or 200
            r.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="12" fill="{color}" stroke="#d4d4d8"/>')
            for idx, line in enumerate(s.text.splitlines()[:8]):
                r.append(f'<text x="{x + 16:.2f}" y="{y + 38 + idx * 26:.2f}" font-family="Segoe UI, Arial, sans-serif" font-size="{s.font_size:.2f}" fill="#1e293b">{escape(line)}</text>')
        elif s.kind == 'text':
            x, y = s.points[0]
            txt = escape(s.text)
            r.append(f'<text x="{x:.2f}" y="{y:.2f}" font-family="Segoe UI, Arial, sans-serif" font-size="{s.font_size:.2f}" fill="{color}">{txt}</text>')
        elif len(pts) == 1:
            x, y = pts[0]
            r.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{s.width / 2:.2f}" fill="{color}"{opacity}/>')
        else:
            sp = ' '.join(f'{x:.2f},{y:.2f}' for x, y in pts)
            r.append(f'<polyline points="{sp}" stroke="{color}" stroke-width="{s.width:.2f}" fill="none" stroke-linejoin="round" stroke-linecap="round"{opacity}/>')
            if s.kind == 'shape' and s.shape == 'arrow':
                wings = arrow_wings(pts[0], pts[-1], max(12, s.width * 4))
                for wing in wings:
                    r.append(f'<line x1="{pts[-1][0]:.2f}" y1="{pts[-1][1]:.2f}" x2="{wing[0]:.2f}" y2="{wing[1]:.2f}" stroke="{color}" stroke-width="{s.width:.2f}"/>')
    r.append('</svg>')
    return '\n'.join(r)


def render_png(drawing, path, page=(PAGE_W, PAGE_H), paper='blank'):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new('RGBA', page, 'white')
    if paper in PAPER_TYPES and paper != 'blank':
        lines = ImageDraw.Draw(im)
        if paper == 'ruled':
            for y in range(138, page[1], 67):
                lines.line([(38, y), (page[0] - 30, y)], fill='#d6e7fb', width=1)
            lines.line([(74, 34), (74, page[1] - 25)], fill='#e8a2b8', width=1)
        elif paper == 'grid':
            for x in range(0, page[0], 48):
                lines.line([(x, 0), (x, page[1])], fill='#edf1f9', width=1)
            for y in range(0, page[1], 48):
                lines.line([(0, y), (page[0], y)], fill='#edf1f9', width=1)
    for s in _visible_strokes(drawing):
        pts = [(int(round(x)), int(round(y))) for x, y in _points(s)]
        if not pts:
            continue
        if s.kind == 'image' and s.image_b64:
            try:
                raw = base64.b64decode(s.image_b64)
                pic = Image.open(io.BytesIO(raw)).convert('RGBA')
                pic = pic.resize((max(1, int(round(s.box_w))), max(1, int(round(s.box_h)))), Image.Resampling.LANCZOS)
                im.alpha_composite(pic, dest=pts[0])
            except Exception:
                pass
            continue
        if s.kind == 'sticky':
            layer = Image.new('RGBA', page, (0, 0, 0, 0))
            dr = ImageDraw.Draw(layer)
            x, y = pts[0]
            w = int(round(s.box_w or 240))
            h = int(round(s.box_h or 200))
            rgba = tuple(bytes.fromhex(s.color.removeprefix('#'))) + (255,)
            dr.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=rgba, outline=(203, 213, 225, 255), width=2)
            try:
                font = ImageFont.truetype('arial.ttf', max(10, int(s.font_size)))
            except OSError:
                font = ImageFont.load_default()
            dr.multiline_text((x + 16, y + 18), s.text, fill=(30, 41, 59, 255), font=font, spacing=6)
            im = Image.alpha_composite(im, layer)
            continue
        alpha = 90 if s.kind == 'highlighter' else 255
        color = '#ffffff' if s.erase or s.kind == 'eraser' else s.color
        rgba = tuple(bytes.fromhex(color.removeprefix('#'))) + (alpha,)
        layer = Image.new('RGBA', page, (0, 0, 0, 0))
        dr = ImageDraw.Draw(layer)
        w = max(1, int(round(s.width)))
        if s.kind == 'text':
            font = None
            try:
                font = ImageFont.truetype('arial.ttf', max(8, int(s.font_size)))
            except OSError:
                try:
                    font = ImageFont.truetype('DejaVuSans.ttf', max(8, int(s.font_size)))
                except OSError:
                    font = ImageFont.load_default()
            dr.text(pts[0], s.text, fill=rgba, font=font, anchor='ls')
        elif len(pts) > 1:
            dr.line(pts, fill=rgba, width=w, joint='curve')
            if s.kind == 'shape' and s.shape == 'arrow':
                for wing in arrow_wings(pts[0], pts[-1], max(12, s.width * 4)):
                    dr.line([pts[-1], wing], fill=rgba, width=w)
        if s.kind != 'text':
            rad = w / 2
            for x, y in (pts[0], pts[-1]):
                dr.ellipse((x - rad, y - rad, x + rad, y + rad), fill=rgba)
        im = Image.alpha_composite(im, layer)
    im.convert('RGB').save(path)


class OneEuro:
    def __init__(self, min_cutoff=2.8, beta=.07, derivative_cutoff=1):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.derivative_cutoff = derivative_cutoff
        self.prev = None
        self.deriv = 0.
        self.prev_time = None

    @staticmethod
    def alpha(cutoff, dt):
        return 1 / (1 + 1 / (2 * math.pi * max(.01, cutoff) * dt))

    def update(self, value, t):
        if self.prev is None:
            self.prev = value
            self.prev_time = t
            return value
        dt = max(.001, min(.1, t - self.prev_time))
        vel = (value - self.prev) / dt
        a = self.alpha(self.derivative_cutoff, dt)
        self.deriv = a * vel + (1 - a) * self.deriv
        a = self.alpha(self.min_cutoff + self.beta * abs(self.deriv), dt)
        self.prev = a * value + (1 - a) * self.prev
        self.prev_time = t
        return self.prev
