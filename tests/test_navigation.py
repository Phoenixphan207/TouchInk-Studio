"""Regression tests for cursor mapping and free two-dimensional writing-area navigation."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import window_span
from navigation import move_window, window_from_map, edge_turn
from cursor_follow import CursorFollower, page_canvas_to_global

PAGE = (1754,1240)
ZOOM = 2.5
RATIO = 1.62


class NavigationTests(unittest.TestCase):
    def test_vertical_movement_preserves_x(self):
        a=[550,520]
        above=move_window(a,'up',ZOOM,RATIO,PAGE)
        below=move_window(a,'down',ZOOM,RATIO,PAGE)
        self.assertEqual(a[0],above[0])
        self.assertEqual(a[0],below[0])
        self.assertLess(above[1],a[1])
        self.assertGreater(below[1],a[1])

    def test_horizontal_movement_preserves_y(self):
        a=[650,420]
        b=move_window(a,'left',ZOOM,RATIO,PAGE)
        c=move_window(a,'right',ZOOM,RATIO,PAGE)
        self.assertEqual(a[1],b[1])
        self.assertEqual(a[1],c[1])
        self.assertLess(b[0],a[0]);self.assertGreater(c[0],a[0])

    def test_backtrack_up_down(self):
        a=[450,390]
        down=move_window(a,'down',ZOOM,RATIO,PAGE)
        up=move_window(down,'up',ZOOM,RATIO,PAGE)
        for aa,bb in zip(a,up):self.assertAlmostEqual(aa,bb,places=4)

    def test_newline_returns_to_margin(self):
        nextline=move_window([800,350],'newline',ZOOM,RATIO,PAGE)
        self.assertAlmostEqual(nextline[0],PAGE[0]*.09)
        self.assertGreater(nextline[1],350)

    def test_clamp_at_edges(self):
        for start in ([0,0],[1700,1100]):
            for direction in ['left','right','up','down','newline']:
                x,y=move_window(start,direction,ZOOM,RATIO,PAGE)
                w,h=window_span(ZOOM,RATIO,page=PAGE)
                self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
                self.assertLessEqual(x,PAGE[0]-w);self.assertLessEqual(y,PAGE[1]-h)

    def test_map_centers_and_clamps(self):
        w,h=window_span(ZOOM,RATIO,page=PAGE)
        x,y=window_from_map(.5,.5,ZOOM,RATIO,PAGE)
        self.assertAlmostEqual(x+w/2,PAGE[0]/2)
        self.assertAlmostEqual(y+h/2,PAGE[1]/2)
        self.assertEqual(window_from_map(-1,-1,ZOOM,RATIO,PAGE),[0,0])

    def test_auto_pan_all_four_edges(self):
        tests=[('right',.4,.5,.99,.55),('left',.5,.5,.01,.49),
               ('down',.5,.4,.52,.99),('up',.5,.55,.51,.01)]
        for expected, su, sv,lu,lv in tests:
            self.assertEqual(edge_turn(su,sv,lu,lv,9),expected)
        self.assertIsNone(edge_turn(.5,.5,.99,.5,2))
        self.assertIsNone(edge_turn(.5,.5,.6,.6,8))
        self.assertIsNone(edge_turn(.97,.4,.98,.4,10))


class FakeCanvas:
    def canvasx(self,x):return x+90
    def canvasy(self,y):return y+35
    def winfo_rootx(self):return 250
    def winfo_rooty(self):return 140
    def winfo_width(self):return 800
    def winfo_height(self):return 600

class FakeRoot:
    def winfo_id(self):return 44

class FakeUser32:
    def __init__(self):self.foreground=88;self.moves=[]
    def GetAncestor(self,hwnd,code):return 88
    def GetForegroundWindow(self):return self.foreground
    def SetCursorPos(self,x,y):self.moves.append((x,y));return True

class CursorTests(unittest.TestCase):
    def test_scroll_is_subtracted(self):
        x,y,sx,sy=page_canvas_to_global(FakeCanvas(),390,235)
        self.assertEqual((x,y,sx,sy),(300,200,550,340))

    def test_foreground_and_canvas_bounds(self):
        win=FakeUser32()
        follower=CursorFollower(api=win,enabled=True)
        r=FakeRoot();c=FakeCanvas()
        self.assertTrue(follower.follow(r,c,(390,235)))
        self.assertEqual(win.moves[-1],(550,340))
        self.assertFalse(follower.follow(r,c,(0,0)))
        self.assertEqual(len(win.moves),1)
        win.foreground=100
        self.assertFalse(follower.follow(r,c,(391,236)))
        self.assertEqual(len(win.moves),1)

    def test_non_windows_no_mouse_api(self):
        follower=CursorFollower(enabled=False)
        self.assertFalse(follower.follow(FakeRoot(),FakeCanvas(),(390,235)))


if __name__=='__main__':unittest.main()
