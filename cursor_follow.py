"""Non-invasive Windows cursor follower for RAW ABSOLUTE ink.

We do not install a mouse hook, change drivers, or suppress normal mouse input.
All OS movement is foreground-only and restricted to the visible writing canvas.
"""
import sys


def page_canvas_to_global(canvas, canvas_x, canvas_y):
    """Tk canvas-world coordinates -> physical screen location.

    Includes canvas scrolling; this prevents pointer/ink mismatch at page zoom.
    """
    x=canvas_x-canvas.canvasx(0)
    y=canvas_y-canvas.canvasy(0)
    return x,y,canvas.winfo_rootx()+x,canvas.winfo_rooty()+y


class CursorFollower:
    def __init__(self, api=None, enabled=None):
        self.enabled=(sys.platform=='win32') if enabled is None else enabled
        self.api=api
        if self.enabled and self.api is None:
            import ctypes
            from ctypes import wintypes
            self.api=ctypes.WinDLL('user32',use_last_error=True)
            self.api.SetCursorPos.argtypes=[ctypes.c_int,ctypes.c_int]
            self.api.SetCursorPos.restype=wintypes.BOOL
            self.api.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
            self.api.GetAncestor.restype=wintypes.HWND
            self.api.GetForegroundWindow.restype=wintypes.HWND

    def foreground(self, root):
        """True only if the main application window is currently active."""
        if not self.enabled or self.api is None:return True
        try:
            toplevel=self.api.GetAncestor(root.winfo_id(),2)
            return bool(toplevel) and self.api.GetForegroundWindow()==toplevel
        except (OSError,ValueError,AttributeError,TypeError):
            return False

    def follow(self, root, canvas, canvas_pos):
        if not self.enabled or self.api is None:
            return False
        try:
            # Guard against changing the cursor while a dialog or another application
            # is active. 2=GA_ROOT in Win32.
            if not self.foreground(root):return False
            x,y,screenx,screeny=page_canvas_to_global(canvas,*canvas_pos)
            # Never move the cursor outside the canvas (toolbar / Windows desktop).
            if not (4<=x<canvas.winfo_width()-4 and 4<=y<canvas.winfo_height()-4):
                return False
            return bool(self.api.SetCursorPos(round(screenx),round(screeny)))
        except (OSError,ValueError,AttributeError,TypeError):
            return False
