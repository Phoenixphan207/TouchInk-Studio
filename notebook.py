"""Version 1 backward-compatible .touchink storage with atomic writes."""
import json, os, tempfile, time
from engine import Drawing, Stroke, PAPER_TYPES, SHAPES

SCHEMA = 1
TOOLS = ('pen', 'fountain', 'highlighter', 'eraser', 'shape', 'text', 'sticky', 'image')


def new_page():
    return {
        'id': f'p{time.time_ns()}',
        'name': 'Untitled page',
        'paper': 'ruled',
        'orientation': 'portrait',
        'strokes': [],
        'origin': [100., 170.]
    }


def new_book(title='My Notebook'):
    return {'schema': SCHEMA, 'title': title, 'page_index': 0, 'pages': [new_page()]}


def validate(book):
    if not isinstance(book, dict) or book.get('schema') != SCHEMA:
        raise ValueError('Unsupported notebook version')
    pages = book.get('pages')
    if not isinstance(pages, list) or not pages or len(pages) > 500:
        raise ValueError('Invalid page count')
    for page in pages:
        if (not isinstance(page, dict)
                or page.get('paper', 'ruled') not in PAPER_TYPES
                or page.get('orientation', 'portrait') not in ('portrait', 'landscape')
                or not isinstance(page.get('strokes'), list)):
            raise ValueError('Invalid page')
        if len(page['strokes']) > 100000:
            raise ValueError('Too many strokes')
        for s in page['strokes']:
            if not isinstance(s, dict) or s.get('kind', 'pen') not in TOOLS:
                raise ValueError('Invalid tool')
            if s.get('kind') == 'shape' and s.get('shape', '') not in SHAPES:
                raise ValueError('Invalid shape')
            if not isinstance(s.get('points'), list) or len(s['points']) > 100000:
                raise ValueError('Invalid points')
    return book


def save_book(book, path):
    validate(book)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.touchink-', suffix='.tmp', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(book, f, ensure_ascii=False, separators=(',', ':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_book(path):
    with open(path, encoding='utf-8') as f:
        book = json.load(f)
    validate(book)
    book['page_index'] = max(0, min(len(book['pages']) - 1, int(book.get('page_index', 0))))
    return book


def drawing_from_page(page):
    d = Drawing()
    from ink_edit import erase_segment
    for obj in page.get('strokes', []):
        kind = obj.get('kind', 'pen')
        s = Stroke(
            color=obj.get('color', '#111827'),
            width=float(obj.get('width', 3)),
            erase=(kind == 'eraser'),
            points=[(float(x), float(y)) for x, y in obj['points']],
            kind=kind,
            shape=obj.get('shape', ''),
            text=obj.get('text', ''),
            font_size=float(obj.get('font_size', 28)),
            box_w=float(obj.get('box_w', 0.0)),
            box_h=float(obj.get('box_h', 0.0)),
            image_b64=obj.get('image_b64', '')
        )
        if kind == 'eraser':
            for a, b in zip(s.points, s.points[1:]):
                d.strokes, _ = erase_segment(d.strokes, a, b, s.width / 2)
            if len(s.points) == 1:
                d.strokes, _ = erase_segment(d.strokes, s.points[0], s.points[0], s.width / 2)
        else:
            d.strokes.append(s)
    d.restore_undo_for_loaded_page()
    return d


def sync_page(page, drawing, origin):
    page['origin'] = list(origin)
    out = []
    for s in drawing.strokes:
        rec = dict(
            color=s.color, width=s.width, kind=s.kind, shape=s.shape,
            text=s.text, font_size=s.font_size, points=s.points
        )
        if s.box_w:
            rec['box_w'] = s.box_w
        if s.box_h:
            rec['box_h'] = s.box_h
        if s.image_b64:
            rec['image_b64'] = s.image_b64
        out.append(rec)
    page['strokes'] = out
