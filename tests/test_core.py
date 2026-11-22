"""Non-destructive unit checks; no webcam/Windows HID needed."""
import tempfile
import unittest
from pathlib import Path

from engine import Drawing, point_to_page, window_span
from ink_edit import strokes_in_lasso
from notebook import new_book, new_page, save_book, load_book, sync_page, drawing_from_page


class TouchInkCoreTests(unittest.TestCase):
    def test_absolute_mapping_is_deterministic(self):
        a = point_to_page(.5, .5, [100, 150], 2, 1.62)
        self.assertEqual(a, point_to_page(.5, .5, [100, 150], 2, 1.62))

    def test_mapping_zoom_reduces_footprint(self):
        w1, _ = window_span(1, 1.62)
        w2, _ = window_span(2, 1.62)
        self.assertAlmostEqual(w1 / 2, w2)

    def test_stroke_undo_redo(self):
        d = Drawing()
        d.begin(10, 10, kind='pen')
        d.move(90, 90)
        d.end()
        self.assertEqual(len(d.strokes), 1)
        d.undo()
        self.assertFalse(d.strokes)
        d.redo_one()
        self.assertEqual(len(d.strokes), 1)

    def test_eraser_preserves_other_ink(self):
        d = Drawing()
        d.begin(10, 10); d.move(90, 10); d.end()
        d.begin(10, 90); d.move(90, 90); d.end()
        d.start_eraser()
        self.assertTrue(d.erase_to((50, 5), (50, 15), 8))
        d.finish_eraser()
        self.assertTrue(any(any(y == 90 for _x, y in s.points) for s in d.strokes))

    def test_lasso_selects_inside(self):
        d = Drawing()
        d.begin(5, 5); d.move(20, 15); d.end()
        d.begin(100, 100); d.move(150, 150); d.end()
        selected = strokes_in_lasso(d.strokes, [(0,0), (50,0), (50,50), (0,50)])
        self.assertEqual(len(selected), 1)

    def test_pages_and_formats_round_trip(self):
        b = new_book('Test Notebook')
        b['pages'].append(new_page())
        b['pages'][1]['paper'] = 'grid'
        b['pages'][1]['orientation'] = 'landscape'
        d = Drawing()
        d.begin(8, 12, kind='pen'); d.move(42, 50); d.end()
        sync_page(b['pages'][1], d, [100,170])
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td)/'book.touchink')
            save_book(b, path)
            out = load_book(path)
        self.assertEqual(out['pages'][1]['paper'], 'grid')
        self.assertEqual(out['pages'][1]['orientation'], 'landscape')
        self.assertEqual(len(drawing_from_page(out['pages'][1]).strokes), 1)


if __name__ == '__main__':
    unittest.main()
