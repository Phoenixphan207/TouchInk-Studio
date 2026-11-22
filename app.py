"""TouchInk Studio 0.8 — Miro + Scrble Ink + OneNote Edition.

Features:
- Visual Popover selectors for Stroke Width & Geometric Shapes (Scrble Ink / GoodNotes style)
- Smooth animated Viewport & Writing-Box Panning (60fps ease-out interpolation)
- Miro-style Sticky Notes & Embedded Images (insert via toolbar, Ctrl+V clipboard, or drag-and-drop)
- Draggable floating pen palette, OneNote drag-to-reorder pages, and read-only RAW HID touchpad support.
"""
import base64
import datetime
import io
import json
import math
import os
import shutil
import sys
import time
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog

try:
    from PIL import Image, ImageTk, ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from engine import (Drawing, OneEuro, PAGE_W, PAGE_H, SHAPES, PAPER_TYPES,
                    advance_origin, arrow_wings, default_origin, make_svg,
                    point_to_page, render_png, shape_path, window_span, clamp)
from ink_edit import strokes_in_lasso
from cursor_follow import CursorFollower
from navigation import move_window, window_from_map, edge_turn
from notebook import new_book, new_page, save_book, load_book, drawing_from_page, sync_page
from raw_touchpad import RawTouchpad
from ui_icons import create_app_icon, draw_icon

DOCS = os.path.join(os.path.expanduser('~'), 'Documents', 'TouchInk Studio')
DEFAULT_BOOK = os.path.join(DOCS, 'My Notebook.touchink')
SETTINGS = os.path.join(DOCS, 'settings.json')

# Modern daylight studio palette
BG = '#f5f6fc'
WHITE = '#ffffff'
TOP = '#ffffff'
SUBTLE = '#f7f8fd'
SHADOW = '#e4e7f2'
BDR = '#e2e6f0'
TEXT = '#1e2436'
MUTED = '#687287'
FAINT = '#9ea7ba'
PURPLE = '#6750e8'
PURPLE_HOVER = '#543bd3'
LAV = '#f0edff'
LAV2 = '#e2d9ff'
DARK = '#161b26'
RED = '#ef4456'
BLUE = '#2f7cf6'
GREEN = '#16b36c'
YELLOW = '#facc15'
CYAN = '#06b6d4'
VIOLET = '#8b5cf6'
LINE = '#d4e6fc'
DOT = '#d4dceb'

COLORS = [DARK, RED, BLUE, GREEN, YELLOW, CYAN, VIOLET]
STICKY_COLORS = [
    ('#fef08a', '#eab308', 'Sunny Yellow'),
    ('#fbcfe8', '#ec4899', 'Blossom Pink'),
    ('#bae6fd', '#0284c7', 'Sky Cyan'),
    ('#bbf7d0', '#16a34a', 'Mint Green'),
    ('#ddd6fe', '#7c3aed', 'Soft Lavender'),
]

TOOL_INFO = {
    'pen': ('pen', 'Pen (1)'),
    'fountain': ('fountain', 'Fountain Pen (2)'),
    'highlighter': ('highlighter', 'Highlighter (3)'),
    'eraser': ('eraser', 'Vector Eraser (4)'),
    'hand': ('hand', 'Pan Canvas (8)'),
    'select': ('select', 'Select & Move (5)'),
    'lasso': ('lasso', 'Freehand Lasso (9)'),
    'shape': ('shape', 'Shapes (6)'),
    'text': ('text', 'Insert Text (7)'),
    'sticky': ('sticky', 'Add Sticky Note (S)'),
    'image': ('image', 'Insert Image (I)'),
}


def rounded(canvas, x1, y1, x2, y2, r, **kwargs):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    coords = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1
    ]
    return canvas.create_polygon(coords, smooth=True, splinesteps=18, **kwargs)


class HoverTooltip:
    """Lightweight floating tooltip for icon buttons."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        self._after_id = None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress-1>', self._hide, add='+')

    def _schedule(self, _e=None):
        self._cancel()
        self._after_id = self.widget.after(420, self._show)

    def _cancel(self):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        if self.tip or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes('-topmost', True)
        lbl = tk.Label(
            tw, text=self.text, bg='#1e2436', fg='#ffffff',
            font=('Segoe UI', 9), padx=9, pady=4
        )
        lbl.pack()
        tw.update_idletasks()
        tw.wm_geometry(f'+{max(8, x - tw.winfo_width() // 2)}+{y}')

    def _hide(self, _e=None):
        self._cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None


class SoftButton(tk.Canvas):
    """Modern pill button with optional vector icon, hover animation, and live ink accent."""
    def __init__(self, parent, text='', command=None, width=92, height=36,
                 kind='plain', font_size=10, icon=None, icon_size=18,
                 accent=PURPLE, radius=11, tooltip=None, **kwargs):
        self.panel_bg = kwargs.pop('panel_bg', WHITE)
        super().__init__(parent, width=width, height=height, bg=self.panel_bg,
                         highlightthickness=0, bd=0, relief='flat', cursor='hand2', **kwargs)
        self.label = text
        self.command = command
        self.kind = kind
        self.hover = False
        self.chosen = False
        self.font_size = font_size
        self.w = width
        self.h = height
        self.icon = icon
        self.icon_size = icon_size
        self.accent = accent
        self.radius = radius
        self.bind('<Button-1>', self._fire)
        self.bind('<Enter>', self._enter)
        self.bind('<Leave>', self._leave)
        if tooltip:
            HoverTooltip(self, tooltip)
        self.render()

    def _fire(self, _event=None):
        if self.command:
            self.command()

    def _enter(self, _event):
        self.hover = True
        self.render()

    def _leave(self, _event):
        self.hover = False
        self.render()

    def set(self, text=None, selected=None, kind=None, accent=None, icon=None):
        if text is not None:
            self.label = text
        if selected is not None:
            self.chosen = bool(selected)
        if kind is not None:
            self.kind = kind
        if accent is not None:
            self.accent = accent
        if icon is not None:
            self.icon = icon
        self.render()

    def render(self):
        self.delete('all')
        if self.kind == 'primary':
            bg = PURPLE if not self.hover else PURPLE_HOVER
            fg = WHITE
            edge = bg
        elif self.kind == 'on' or self.chosen:
            bg = LAV if not self.hover else LAV2
            fg = PURPLE
            edge = LAV2
        elif self.kind == 'danger':
            bg = '#fff1f2' if not self.hover else '#ffe4e6'
            fg = '#be123c'
            edge = '#fecdd3'
        elif self.kind == 'outline':
            bg = WHITE if not self.hover else SUBTLE
            fg = TEXT
            edge = BDR if not self.hover else '#cfd6e8'
        else:
            bg = self.panel_bg if not self.hover else '#f1f3fa'
            fg = TEXT
            edge = bg

        rounded(self, 1, 1, self.w - 1, self.h - 1, self.radius, fill=bg, outline=edge, width=1)

        if self.icon and self.label:
            ix = 18
            draw_icon(self, self.icon, ix, self.h / 2, size=self.icon_size,
                      color=fg, accent=self.accent, active=self.chosen)
            self.create_text(ix + self.icon_size * 0.72 + 4, self.h / 2, text=self.label,
                             anchor='w', fill=fg,
                             font=('Segoe UI', self.font_size,
                                   'bold' if self.kind in ('primary', 'on') or self.chosen else 'normal'))
        elif self.icon:
            draw_icon(self, self.icon, self.w / 2, self.h / 2, size=self.icon_size,
                      color=fg, accent=self.accent, active=self.chosen)
        else:
            self.create_text(self.w / 2, self.h / 2, text=self.label, fill=fg,
                             font=('Segoe UI', self.font_size,
                                   'bold' if self.kind in ('primary', 'on') or self.chosen else 'normal'))


class StrokeWidthButton(tk.Canvas):
    """Visual stroke thickness pill displaying an actual proportional ink dot."""
    def __init__(self, parent, width_val, color, command, panel_bg=WHITE):
        super().__init__(parent, width=74, height=36, bg=panel_bg,
                         highlightthickness=0, bd=0, cursor='hand2')
        self.panel_bg = panel_bg
        self.width_val = width_val
        self.color = color
        self.command = command
        self.hover = False
        self.bind('<Button-1>', lambda _e: self.command())
        self.bind('<Enter>', lambda _e: self._set_hover(True))
        self.bind('<Leave>', lambda _e: self._set_hover(False))
        HoverTooltip(self, 'Stroke thickness (Visual Popover)')
        self.render()

    def _set_hover(self, h):
        self.hover = h
        self.render()

    def update_state(self, width_val=None, color=None):
        if width_val is not None:
            self.width_val = width_val
        if color is not None:
            self.color = color
        self.render()

    def render(self):
        self.delete('all')
        bg = '#f4f6fc' if not self.hover else '#ebeef8'
        rounded(self, 1, 1, 73, 35, 11, fill=bg, outline=BDR, width=1)
        r = clamp(self.width_val * 0.85, 2.0, 9.5)
        self.create_oval(19 - r, 18 - r, 19 + r, 18 + r, fill=self.color, outline='')
        self.create_text(34, 18, text=f'{self.width_val:.1f}', anchor='w', fill=TEXT,
                         font=('Segoe UI', 9, 'bold'))


class ColorDot(tk.Canvas):
    """Friendly color swatch with hover ring and active outer halo."""
    def __init__(self, parent, color, callback):
        super().__init__(parent, width=30, height=32, bg=WHITE, highlightthickness=0, cursor='hand2')
        self.color = color
        self.active = False
        self.hover = False
        self.callback = callback
        self.bind('<Button-1>', lambda _e: callback(self.color))
        self.bind('<Enter>', lambda _e: self._set_hover(True))
        self.bind('<Leave>', lambda _e: self._set_hover(False))
        self.render()

    def _set_hover(self, h):
        self.hover = h
        self.render()

    def render(self):
        self.delete('all')
        if self.active:
            self.create_oval(2, 3, 28, 29, outline=self.color if self.color != YELLOW else '#eab308', width=2)
        elif self.hover:
            self.create_oval(3, 4, 27, 28, outline='#cbd5e1', width=1.5)
        pad = 6 if (self.active or self.hover) else 7
        self.create_oval(pad, pad + 1, 30 - pad, 31 - pad, fill=self.color,
                         outline='#e2e8f0' if self.color == YELLOW else '')


class VisualPopover(tk.Toplevel):
    """Rounded floating popover card (Scrble Ink / GoodNotes style) that auto-dismisses."""
    def __init__(self, anchor_widget, width, height, offset_x=0, offset_y=8):
        super().__init__(anchor_widget)
        self.wm_overrideredirect(True)
        self.wm_attributes('-topmost', True)
        self.configure(bg=BDR)
        self.card = tk.Frame(self, bg=WHITE, highlightbackground=BDR, highlightthickness=1)
        self.card.pack(fill='both', expand=True, padx=1, pady=1)

        anchor_widget.update_idletasks()
        ax = anchor_widget.winfo_rootx() + anchor_widget.winfo_width() // 2 - width // 2 + offset_x
        ay = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + offset_y
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        ax = max(12, min(sw - width - 12, ax))
        if ay + height > sh - 24:
            ay = max(12, anchor_widget.winfo_rooty() - height - offset_y)
        self.wm_geometry(f'{width}x{height}+{ax}+{ay}')

        self.bind('<Escape>', lambda _e: self.destroy())
        self.bind('<FocusOut>', self._on_focus_out)
        self.after(20, self.focus_force)

    def _on_focus_out(self, _e=None):
        self.after(60, self._check_focus)

    def _check_focus(self):
        if not self.winfo_exists():
            return
        focused = self.focus_get()
        if focused is None or str(focused).split('.')[1] != self.winfo_name():
            self.destroy()


class StickyNoteDialog(tk.Toplevel):
    """Miro-inspired rounded Sticky Note editor with live pastel color picker."""
    def __init__(self, parent, initial_text='', initial_color='#fef08a'):
        super().__init__(parent)
        self.title('Sticky Note')
        self.configure(bg=WHITE)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.chosen_color = initial_color

        w, h = 340, 290
        px = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f'{w}x{h}+{max(20, px)}+{max(20, py)}')

        hdr = tk.Frame(self, bg=WHITE)
        hdr.pack(fill='x', padx=16, pady=(14, 8))
        tk.Label(hdr, text='Sticky Note', font=('Segoe UI', 12, 'bold'), fg=TEXT, bg=WHITE).pack(side='left')

        swatch_row = tk.Frame(hdr, bg=WHITE)
        swatch_row.pack(side='right')
        self.swatches = {}
        for fill_col, border_col, _name in STICKY_COLORS:
            cv = tk.Canvas(swatch_row, width=24, height=24, bg=WHITE, highlightthickness=0, cursor='hand2')
            cv.pack(side='left', padx=2)
            cv.bind('<Button-1>', lambda _e, c=fill_col: self._pick_color(c))
            self.swatches[fill_col] = (cv, border_col)

        self.note_frame = tk.Frame(self, bg=self.chosen_color, highlightbackground='#d4d4d8', highlightthickness=1)
        self.note_frame.pack(fill='both', expand=True, padx=16, pady=4)
        self.txt = tk.Text(
            self.note_frame, bg=self.chosen_color, fg='#1e293b', font=('Segoe UI', 11),
            relief='flat', bd=0, wrap='word', padx=12, pady=10, insertbackground='#1e293b'
        )
        self.txt.pack(fill='both', expand=True)
        if initial_text:
            self.txt.insert('1.0', initial_text)

        foot = tk.Frame(self, bg=WHITE)
        foot.pack(fill='x', padx=16, pady=(10, 14))
        SoftButton(foot, 'Cancel', self.destroy, width=78, height=32, kind='outline').pack(side='right')
        SoftButton(foot, 'Save Note', self._submit, width=96, height=32, kind='primary').pack(side='right', padx=(0, 8))

        self._refresh_swatches()
        self.txt.focus_set()
        self.bind('<Control-Return>', lambda _e: self._submit())
        self.bind('<Escape>', lambda _e: self.destroy())

    def _pick_color(self, color):
        self.chosen_color = color
        self.note_frame.configure(bg=color)
        self.txt.configure(bg=color)
        self._refresh_swatches()

    def _refresh_swatches(self):
        for col, (cv, bdr) in self.swatches.items():
            cv.delete('all')
            if col == self.chosen_color:
                cv.create_oval(2, 2, 22, 22, fill=col, outline=bdr, width=2.2)
            else:
                cv.create_oval(4, 4, 20, 20, fill=col, outline='#cbd5e1', width=1)

    def _submit(self):
        content = self.txt.get('1.0', 'end-1c').strip()
        if content:
            self.result = (content, self.chosen_color)
        self.destroy()


class Studio:
    def __init__(self, root):
        self.root = root
        root.title('TouchInk Studio')
        root.configure(bg=BG)
        root.geometry('1520x910')
        root.minsize(1180, 740)
        if sys.platform == 'win32':
            # Make the central writing page as large as possible on laptops.
            try:
                root.state('zoomed')
            except tk.TclError:
                pass

        self._app_icon = create_app_icon(64)
        if self._app_icon:
            try:
                root.iconphoto(True, self._app_icon)
            except tk.TclError:
                pass

        self.raw = RawTouchpad()
        self.cursor_follower = CursorFollower()

        self.book = new_book()
        self.book['pages'][0]['orientation'] = 'landscape'
        self.book_path = DEFAULT_BOOK
        self.drawing = Drawing()
        self.origin = default_origin()
        self.raw_mode = False
        self.ink_enabled = True         # Tab toggles Ink / Navigate; NEVER blocks Windows mouse input.
        self.area_drag = None         # Freehand mouse drag target for the writing window.
        self.last_v = None
        self.start_v = None
        self.path_v = []
        self.mapping_zoom = 2.0
        self.pad_ratio = 1.62
        self.view_zoom = 1.15
        self.width = 3.5
        self.tool = 'pen'
        self.shape = 'rectangle'
        self.color = DARK
        self.sticky_color = '#fef08a'
        self.auto_pan = True
        self.show_writing_guides = True
        self.smooth = True
        self.paper = 'ruled'
        self.mouse_test = False
        self.hand_pan = False
        self.selected = None
        self.selected_many = []
        self.lasso_points = []
        self.eraser_last = None
        self._last_erase_paint = 0
        self.drag_old = None
        self.drag_start = None
        self.is_down = False
        self.active_source = None
        self.last_seen = 0
        self.last_u = None
        self.start_u = None
        self.path_u = []
        self.pending_text = None
        self.pending_sticky = None
        self.block_raw_until_up = False
        self.block_time = 0
        self.current_cursor = None
        self.active_ids = []
        self.fx = None
        self.fy = None
        self.history = []
        self.dirty = False
        self.saved_at = ''
        self._last_device_status = ''
        self.side_visible = True
        self.side_tab = 'pages'
        self.focus_mode = False
        self.page_query = tk.StringVar(value='')
        self.page_query.trace_add('write', lambda *_: self._filter_pages())
        self.canvas_page_title = tk.StringVar(value='Untitled page')
        self.canvas_page_info = tk.StringVar(value='Ruled  ·  Landscape')
        self._closing = False
        self._canvas_scale = 1.0
        self.ox = 0
        self.oy = 78

        # Image PhotoImage cache keyed by (id(stroke), scaled_w, scaled_h)
        self._img_pil_cache = {}
        self._img_tk_cache = {}

        # Smooth viewport & writing-box animation state
        self._origin_anim_id = None
        self._view_anim_id = None

        # Draggable floating ink palette state (Scrble Ink style)
        self._palette_pos = None
        self._palette_drag_origin = None

        # Drag-and-drop page reordering state (OneNote style)
        self._page_drag_idx = None
        self._page_drag_start_y = 0
        self._page_dragging = False
        self._page_cards = []
        self._drop_line = None

        self._load_settings()
        self._load_initial_book()
        self._build()
        self._show_page(self.book.get('page_index', 0), sync=False)
        self._bind_keys()
        self._enable_os_file_drop()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(10, self.poll)
        root.after(2500, self.autosave)

    # -------------------------------- storage --------------------------------
    def _load_settings(self):
        try:
            with open(SETTINGS, encoding='utf-8') as f:
                s = json.load(f)
            self.mapping_zoom = clamp(float(s.get('mapping_zoom', 2)), 1, 4)
            self.pad_ratio = clamp(float(s.get('pad_ratio', 1.62)), .5, 3)
            self.view_zoom = clamp(float(s.get('canvas_zoom', 1.15)), .5, 3.5)
            self.auto_pan = bool(s.get('auto_pan', True))
            self.show_writing_guides = bool(s.get('show_writing_guides', True))
            self.book_path = s.get('last_book', DEFAULT_BOOK)
        except (OSError, ValueError, TypeError):
            pass

    def _load_initial_book(self):
        try:
            if self.book_path and os.path.isfile(self.book_path):
                self.book = load_book(self.book_path)
                backup = self.book_path + '.pre-v06.bak'
                if not os.path.isfile(backup):
                    try:
                        shutil.copy2(self.book_path, backup)
                    except OSError:
                        pass
        except Exception as exc:
            self.book = new_book()
            self.book['pages'][0]['orientation'] = 'landscape'
            self.book_path = DEFAULT_BOOK
            self._last_device_status = 'Previous notebook could not be opened: ' + str(exc)

    def _mark_dirty(self):
        self.dirty = True
        self.save_indicator.configure(text='● Unsaved', fg='#b45309', bg='#fef3c7')

    def _sync(self):
        sync_page(self.book['pages'][self.book['page_index']], self.drawing, self.origin)
        self.book['pages'][self.book['page_index']]['paper'] = self.paper

    def save(self):
        self._sync()
        if not self.book_path:
            return self.save_as()
        try:
            save_book(self.book, self.book_path)
            self.dirty = False
            self.saved_at = datetime.datetime.now().strftime('%H:%M')
            self.save_indicator.configure(text='● Saved', fg='#15803d', bg='#dcfce7')
            self.set_status('Notebook saved locally at ' + self.saved_at)
            return True
        except Exception as exc:
            self.save_indicator.configure(text='● Error', fg='#be123c', bg='#ffe4e6')
            messagebox.showerror('Save failed', str(exc), parent=self.root)
            return False

    def save_as(self):
        self._prepare_dialog()
        file = filedialog.asksaveasfilename(
            parent=self.root, initialdir=DOCS, initialfile='Notebook.touchink',
            defaultextension='.touchink', filetypes=[('TouchInk notebook', '*.touchink')]
        )
        if not file:
            return False
        self.book_path = file
        self._update_meta()
        return self.save()

    def autosave(self):
        if not self._closing:
            if self.dirty and self.book_path:
                self._sync()
                try:
                    save_book(self.book, self.book_path)
                    self.dirty = False
                    self.save_indicator.configure(text='● Saved', fg='#15803d', bg='#dcfce7')
                except Exception as exc:
                    self.save_indicator.configure(text='● Error', fg='#be123c', bg='#ffe4e6')
                    self.set_status('Autosave failed: ' + str(exc))
            self.root.after(2500, self.autosave)

    def new_notebook(self):
        if not self.save():
            return
        self._prepare_dialog()
        name = simpledialog.askstring('New notebook', 'Notebook name:', parent=self.root,
                                      initialvalue='Untitled notebook')
        if name is None:
            return
        self.book = new_book((name.strip() or 'Untitled notebook')[:100])
        self.book['pages'][0]['orientation'] = 'landscape'
        self.book_path = None
        self._show_page(0, sync=False)
        self._mark_dirty()
        self.save_as()

    def open_notebook(self):
        if not self.save():
            return
        self._prepare_dialog()
        file = filedialog.askopenfilename(parent=self.root, initialdir=DOCS,
                                          filetypes=[('TouchInk notebook', '*.touchink')])
        if not file:
            return
        try:
            book = load_book(file)
        except Exception as exc:
            messagebox.showerror('Cannot open notebook', str(exc), parent=self.root)
            return
        self.book = book
        self.book_path = file
        self._show_page(book['page_index'], sync=False)
        self.dirty = False
        self.save_indicator.configure(text='● Saved', fg='#15803d', bg='#dcfce7')
        self.set_status('Opened ' + os.path.basename(file))

    def export_page(self, kind='png'):
        self._prepare_dialog()
        ext = '.' + kind
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=ext,
            initialfile=self.book['pages'][self.book['page_index']]['name'] + ext,
            filetypes=[(kind.upper() + ' image', '*' + ext)]
        )
        if not path:
            return
        try:
            if kind == 'png':
                render_png(self.drawing, path, page=self.page_dims(), paper=self.paper)
            else:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(make_svg(self.drawing, width=self.page_dims()[0],
                                     height=self.page_dims()[1], paper=self.paper))
            self.set_status('Exported ' + os.path.basename(path))
        except Exception as exc:
            messagebox.showerror('Export failed', str(exc), parent=self.root)

    def _show_page(self, index, sync=True):
        self._release_active(commit=True)
        if sync:
            self._sync()
        self.block_raw_until_up = self.raw_mode
        self.block_time = time.perf_counter()
        index = max(0, min(index, len(self.book['pages']) - 1))
        self.book['page_index'] = index
        page = self.book['pages'][index]
        self.drawing = drawing_from_page(page)
        self.origin = list(page.get('origin', default_origin(page=self.page_dims())))
        self.paper = page.get('paper', 'ruled')
        self.history.clear()
        self.selected = None
        self.selected_many = []
        self.lasso_points = []
        self._selection_strip_update()
        if any(st.get('kind') == 'eraser' for st in page.get('strokes', [])):
            self._mark_dirty()
        self.page_counter.configure(text=f'{index + 1} / {len(self.book["pages"])}')
        self._update_meta()
        self._update_paper_pills()
        self._update_canvas_info()
        self.refresh_pages()
        self.repaint()

    def new_page(self, paper=None, orientation=None):
        self._release_active(commit=True)
        self._sync()
        p = new_page()
        p['name'] = f'Page {len(self.book["pages"]) + 1}'
        p['paper'] = paper if paper in PAPER_TYPES else self.paper
        p['orientation'] = (orientation if orientation in ('portrait', 'landscape') else
                            self.book['pages'][self.book['page_index']].get('orientation', 'portrait'))
        self.book['pages'].append(p)
        self._show_page(len(self.book['pages']) - 1, sync=False)
        self._mark_dirty()
        self.set_status('New page created · Ctrl+N')

    def select_page(self, index):
        if index == self.book['page_index']:
            return
        self._show_page(index)
        self._mark_dirty()

    def previous_page(self):
        self.select_page(max(0, self.book['page_index'] - 1))

    def next_page(self):
        self.select_page(min(len(self.book['pages']) - 1, self.book['page_index'] + 1))

    def rename_page(self, index=None):
        self._prepare_dialog()
        idx = self.book['page_index'] if index is None else index
        name = simpledialog.askstring('Rename page', 'Page title:',
                                      initialvalue=self.book['pages'][idx]['name'], parent=self.root)
        if name and name.strip():
            self.book['pages'][idx]['name'] = name.strip()[:90]
            self._mark_dirty()
            self.refresh_pages()
            self._update_canvas_info()
            self.repaint()

    def delete_page(self, index=None):
        self._prepare_dialog()
        if len(self.book['pages']) <= 1:
            messagebox.showinfo('TouchInk', 'A notebook must have at least one page.', parent=self.root)
            return
        idx = self.book['page_index'] if index is None else index
        if not messagebox.askyesno('Delete page', 'Delete this page and all its writing?', parent=self.root):
            return
        self._release_active(commit=True)
        self._sync()
        self.book['pages'].pop(idx)
        self._show_page(min(idx, len(self.book['pages']) - 1), sync=False)
        self._mark_dirty()

    def rename_notebook(self):
        self._prepare_dialog()
        name = simpledialog.askstring('Rename notebook', 'Notebook title:',
                                      initialvalue=self.book['title'], parent=self.root)
        if name and name.strip():
            self.book['title'] = name.strip()[:100]
            self._update_meta()
            self._mark_dirty()

    def page_dims(self):
        p = self.book['pages'][self.book['page_index']]
        return (PAGE_H, PAGE_W) if p.get('orientation', 'portrait') == 'landscape' else (PAGE_W, PAGE_H)

    # -------------------------------- UI Construction --------------------------------
    def _button(self, parent, text='', callback=None, width=90, height=36, kind='plain',
                panel_bg=WHITE, font_size=10, icon=None, icon_size=18, accent=PURPLE,
                radius=11, tooltip=None):
        return SoftButton(
            parent, text=text, command=callback, width=width, height=height, kind=kind,
            panel_bg=panel_bg, font_size=font_size, icon=icon, icon_size=icon_size,
            accent=accent, radius=radius, tooltip=tooltip
        )

    def _build(self):
        self._build_top()
        self._build_bottom()
        self._build_body()
        self._update_color_buttons()
        self._update_tool_buttons()
        self._update_zoom_labels()
        self._update_paper_pills()

    def _build_top(self):
        bar = tk.Frame(self.root, bg=TOP, height=58, highlightbackground=BDR, highlightthickness=1)
        bar.pack(side='top', fill='x')
        bar.pack_propagate(False)
        self.topbar = bar

        left = tk.Frame(bar, bg=TOP)
        left.pack(side='left', fill='y', padx=(12, 0))

        self._button(left, '', self.open_menu, width=36, height=36, icon='menu',
                     panel_bg=TOP, tooltip='Main Menu').pack(side='left', pady=11)

        logo_cv = tk.Canvas(left, width=32, height=32, bg=TOP, highlightthickness=0)
        logo_cv.pack(side='left', padx=(8, 6), pady=13)
        draw_icon(logo_cv, 'logo', 16, 16, size=28)

        tk.Label(left, text='TouchInk', font=('Segoe UI', 14, 'bold'), fg=TEXT, bg=TOP).pack(side='left')
        tk.Label(left, text='Studio', font=('Segoe UI', 13), fg=PURPLE, bg=TOP).pack(side='left', padx=(3, 0))

        tk.Frame(left, bg=BDR, width=1, height=24).pack(side='left', padx=14)

        nb_pill = tk.Frame(left, bg=SUBTLE, highlightbackground=BDR, highlightthickness=1)
        nb_pill.pack(side='left', pady=11)
        self.notebook_name = tk.Label(
            nb_pill, text='My Notebook', font=('Segoe UI', 10, 'bold'), fg=TEXT, bg=SUBTLE,
            cursor='hand2', padx=10, pady=5
        )
        self.notebook_name.pack(side='left')
        self.notebook_name.bind('<Button-1>', lambda _e: self.rename_notebook())
        HoverTooltip(self.notebook_name, 'Click to rename notebook')

        tk.Frame(left, bg=BDR, width=1, height=24).pack(side='left', padx=12)
        paper_box = tk.Frame(left, bg=SUBTLE, highlightbackground=BDR, highlightthickness=1)
        paper_box.pack(side='left', pady=11)
        self.paper_pills = {}
        for ptype, plabel in [('ruled', 'Ruled'), ('grid', 'Grid'), ('blank', 'Blank')]:
            b = self._button(
                paper_box, plabel, lambda t=ptype: self.set_paper(t),
                width=56, height=28, font_size=9, radius=8, panel_bg=SUBTLE,
                tooltip=f'Switch to {plabel} paper'
            )
            b.pack(side='left', padx=2, pady=2)
            self.paper_pills[ptype] = b

        actions = tk.Frame(bar, bg=TOP)
        actions.pack(side='right', fill='y', padx=(6, 14))

        self.save_indicator = tk.Label(
            actions, text='● Saved', fg='#15803d', bg='#dcfce7',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=5
        )
        self.save_indicator.pack(side='right', padx=(10, 0), pady=15)

        nav_pill = tk.Frame(actions, bg=SUBTLE, highlightbackground=BDR, highlightthickness=1)
        nav_pill.pack(side='right', padx=(8, 0), pady=11)
        self._button(nav_pill, '‹', self.previous_page, width=28, height=28, radius=7,
                     panel_bg=SUBTLE, tooltip='Previous page').pack(side='left', padx=2, pady=2)
        self.page_counter = tk.Label(nav_pill, text='1 / 1', fg=TEXT, bg=SUBTLE,
                                     font=('Segoe UI', 9, 'bold'), width=6)
        self.page_counter.pack(side='left')
        self._button(nav_pill, '›', self.next_page, width=28, height=28, radius=7,
                     panel_bg=SUBTLE, tooltip='Next page').pack(side='left', padx=2, pady=2)

        self._button(actions, '▾', self.new_page_gallery, width=34, height=34,
                     kind='outline', panel_bg=TOP, font_size=11,
                     tooltip='Choose a new page template').pack(side='right', padx=(2, 0), pady=12)
        self._button(actions, '+ New Page', self.new_page, width=106, height=34,
                     kind='primary', font_size=10, panel_bg=TOP,
                     tooltip='Quick add page (Ctrl+N)').pack(side='right', padx=(10, 0), pady=12)

        tk.Frame(actions, bg=BDR, width=1, height=24).pack(side='right', padx=10)

        self._button(actions, '', self.redo, width=34, height=34, icon='redo',
                     panel_bg=TOP, tooltip='Redo (Ctrl+Y)').pack(side='right', padx=2, pady=12)
        self._button(actions, '', self.undo, width=34, height=34, icon='undo',
                     panel_bg=TOP, tooltip='Undo (Ctrl+Z)').pack(side='right', padx=2, pady=12)

    def _build_bottom(self):
        outer = tk.Frame(self.root, bg=TOP, height=58, highlightbackground=BDR, highlightthickness=1)
        outer.pack(side='bottom', fill='x')
        outer.pack_propagate(False)

        row = tk.Frame(outer, bg=TOP)
        row.pack(fill='both', expand=True, padx=14)

        left = tk.Frame(row, bg=TOP)
        left.pack(side='left', fill='y')

        self._button(left, 'Connect RAW', self.start_raw, width=106, height=32,
                     kind='outline', font_size=9, panel_bg=TOP,
                     tooltip='Connect Windows Precision Touchpad RAW HID').pack(side='left', pady=12)

        self.raw_state = tk.Label(left, text='● Waiting for touchpad', fg=MUTED, bg=TOP,
                                  font=('Segoe UI', 9), width=21, anchor='w')
        self.raw_state.pack(side='left', padx=(8, 4))

        tk.Frame(left, bg=BDR, width=1, height=22).pack(side='left', padx=10, pady=17)

        self.mode_button = self._button(
            left, '✎  Ink Mode', self.toggle_ink_mode, width=118, height=32,
            kind='on', font_size=9, panel_bg=TOP,
            tooltip='Tab: switch between writing and normal mouse navigation. Hold Shift to pause ink.'
        )
        self.mode_button.pack(side='left', pady=12)
        tk.Label(left, text='Tab: Navigate', font=('Segoe UI', 8, 'bold'), fg=FAINT, bg=TOP).pack(side='left', padx=(6, 8))

        tk.Frame(left, bg=BDR, width=1, height=22).pack(side='left', padx=6, pady=17)

        win_pill = tk.Frame(left, bg=SUBTLE, highlightbackground=BDR, highlightthickness=1)
        win_pill.pack(side='left', padx=6, pady=11)
        tk.Label(win_pill, text='Pad Scale', fg=MUTED, bg=SUBTLE, font=('Segoe UI', 8, 'bold')).pack(side='left', padx=(8, 4))
        self._button(win_pill, '−', lambda: self.change_mapping(-.25), width=26, height=26,
                     radius=7, panel_bg=SUBTLE).pack(side='left', pady=2)
        self.mapping_label = tk.Label(win_pill, text='2.00×', bg=SUBTLE, fg=TEXT,
                                      font=('Segoe UI', 9, 'bold'), width=5)
        self.mapping_label.pack(side='left')
        self._button(win_pill, '+', lambda: self.change_mapping(.25), width=26, height=26,
                     radius=7, panel_bg=SUBTLE).pack(side='left', pady=2)

        # Writing-window movement lives in the floating canvas HUD below,
        # so the status bar can stay quiet and uncluttered.

        self.status_var = tk.StringVar(value='Tab: Ink / Navigate  ·  Shift: temporarily use normal mouse  ·  Arrow keys: move writing area')
        self.status_label = tk.Label(row, textvariable=self.status_var, fg=MUTED, bg=TOP,
                                     font=('Segoe UI', 9), anchor='e')
        self.status_label.pack(side='right', fill='x', expand=True, padx=(12, 4))

    def _build_body(self):
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='both', expand=True)
        self.body = body

        # 1. Right Sidebar (OneNote Page Organizer with Drag & Drop)
        self.side_wrap = tk.Frame(body, bg=BG, width=288)
        self.side_wrap.pack(side='right', fill='y', padx=(0, 12), pady=(12, 12))
        self.side_wrap.pack_propagate(False)
        self.side_border = tk.Frame(self.side_wrap, bg=WHITE, highlightbackground=BDR, highlightthickness=1)
        self.side_border.pack(fill='both', expand=True)
        self._build_sidebar()

        # 2. Workspace Canvas
        workspace = tk.Frame(body, bg=BG)
        workspace.pack(side='left', fill='both', expand=True, padx=(12, 10), pady=(12, 12))
        self.workspace = workspace

        # Canvas header: notebook context + high-priority reading/creation actions.
        canvas_header = tk.Frame(workspace, bg=BG, height=48)
        canvas_header.pack(side='top', fill='x', padx=(72, 4))
        canvas_header.pack_propagate(False)
        caption = tk.Frame(canvas_header, bg=BG)
        caption.pack(side='left', pady=(4, 0))
        tk.Label(caption, text='WORKSPACE  /', bg=BG, fg=FAINT,
                 font=('Segoe UI', 8, 'bold')).pack(side='left', padx=(0, 8))
        self.canvas_heading = tk.Label(caption, textvariable=self.canvas_page_title,
                                       bg=BG, fg=TEXT, font=('Segoe UI', 11, 'bold'), cursor='hand2')
        self.canvas_heading.pack(side='left')
        self.canvas_heading.bind('<Button-1>', lambda _e: self.rename_page())
        self.canvas_info_label = tk.Label(caption, textvariable=self.canvas_page_info,
                                          bg=BG, fg=MUTED, font=('Segoe UI', 9))
        self.canvas_info_label.pack(side='left', padx=(12, 0))
        tools = tk.Frame(canvas_header, bg=BG)
        tools.pack(side='right', pady=3)
        self.focus_btn = self._button(tools, 'Focus', self.toggle_focus_mode,
                                      width=74, height=30, kind='outline', panel_bg=BG,
                                      font_size=9, tooltip='Focus on the canvas (F11)')
        self.focus_btn.pack(side='right', padx=(7, 0))
        self.guide_btn = self._button(tools, 'Guides', self.toggle_writing_guides,
                                       width=74, height=30, kind='on', panel_bg=BG,
                                       font_size=9, tooltip='Show or hide touchpad writing window')
        self.guide_btn.pack(side='right', padx=(7, 0))
        self.guide_btn.set(selected=self.show_writing_guides)
        self._button(tools, 'Layout', self.orientation_menu,
                     width=78, height=30, kind='outline', panel_bg=BG,
                     font_size=9, tooltip='Current page orientation').pack(side='right')

        self.canvas = tk.Canvas(workspace, bg=BG, highlightthickness=0, cursor='crosshair',
                                xscrollincrement=1, yscrollincrement=1)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', self.canvas_resized)
        self.canvas.bind('<ButtonPress-1>', self.mouse_down)
        self.canvas.bind('<B1-Motion>', self.mouse_move)
        self.canvas.bind('<ButtonRelease-1>', self.mouse_up)
        self.canvas.bind('<Double-Button-1>', self.mouse_double_click)
        self.canvas.bind('<MouseWheel>', self.mouse_wheel)
        self.canvas.bind('<ButtonPress-2>', self.pan_start)
        self.canvas.bind('<B2-Motion>', self.pan_drag)
        self.canvas.bind('<ButtonPress-3>', self.pan_start)
        self.canvas.bind('<B3-Motion>', self.pan_drag)

        # 3. Miro-style Floating Left Tool Dock (Select, Lasso, Pan, Shapes, Text, Sticky, Image)
        rail_shadow = tk.Frame(workspace, bg=SHADOW)
        self.rail_shadow = rail_shadow
        rail_shadow.place(x=16, rely=0.5, anchor='w')
        rail = tk.Frame(rail_shadow, bg=WHITE, highlightbackground=BDR, highlightthickness=1)
        rail.pack(padx=(0, 2), pady=(0, 3))
        self.rail_buttons = {}
        for key in ('select', 'lasso', 'hand', 'shape', 'text', 'sticky', 'image'):
            icon_name, tip = TOOL_INFO[key]
            b = self._button(
                rail, text='', callback=lambda k=key: self.choose_tool(k),
                width=42, height=40, icon=icon_name, icon_size=20,
                radius=10, tooltip=tip
            )
            b.pack(padx=6, pady=(5, 0))
            self.rail_buttons[key] = b

        tk.Frame(rail, bg=BDR, height=1).pack(fill='x', padx=10, pady=7)
        self.sidebar_toggle_btn = self._button(
            rail, text='', callback=self.toggle_sidebar,
            width=42, height=38, icon='pages', icon_size=19,
            radius=10, tooltip='Toggle Pages Sidebar'
        )
        self.sidebar_toggle_btn.pack(padx=6, pady=(0, 6))

        # 4. Scrble Ink-style Floating & Draggable Top Pen Palette
        palette_shadow = tk.Frame(workspace, bg=SHADOW)
        palette_shadow.place(relx=0.50, y=61, anchor='n')
        self.palette_shadow = palette_shadow

        palette = tk.Frame(palette_shadow, bg=WHITE, highlightbackground=BDR, highlightthickness=1)
        palette.pack(padx=(0, 2), pady=(0, 3))
        self.palette = palette

        grip = tk.Canvas(palette, width=20, height=38, bg=WHITE, highlightthickness=0, cursor='fleur')
        grip.pack(side='left', padx=(6, 2), pady=5)
        draw_icon(grip, 'grip', 10, 19, size=18)
        HoverTooltip(grip, 'Drag to move toolbar anywhere')
        grip.bind('<ButtonPress-1>', self._start_palette_drag)
        grip.bind('<B1-Motion>', self._move_palette_drag)

        self.palette_buttons = {}
        pen_labels = {'pen': 'Pen', 'fountain': 'Fountain', 'highlighter': 'Marker', 'eraser': 'Eraser'}
        for key in ('pen', 'fountain', 'highlighter', 'eraser'):
            icon_name, tip = TOOL_INFO[key]
            w_btn = 82 if key not in ('highlighter', 'fountain') else 90
            b = self._button(
                palette, text=pen_labels[key], callback=lambda k=key: self.choose_tool(k),
                width=w_btn, height=38, icon=icon_name, icon_size=18,
                accent=self.color, radius=10, tooltip=tip
            )
            b.pack(side='left', padx=(2, 0), pady=5)
            self.palette_buttons[key] = b

        tk.Frame(palette, bg=BDR, width=1, height=26).pack(side='left', padx=8, pady=11)

        # Visual Stroke Thickness Selector -> opens Visual Popover
        self.width_button = StrokeWidthButton(palette, self.width, self.color, self.open_width_popover)
        self.width_button.pack(side='left', pady=6)

        tk.Frame(palette, bg=BDR, width=1, height=26).pack(side='left', padx=8, pady=11)

        self.color_dots = {}
        for color in COLORS:
            dot = ColorDot(palette, color, self.choose_color)
            dot.pack(side='left', padx=1, pady=8)
            self.color_dots[color] = dot

        self._button(palette, '+', self.pick_color, width=30, height=30, radius=15,
                     kind='outline', font_size=11, tooltip='Custom ink color').pack(side='left', padx=(5, 10), pady=9)

        # 5. Contextual Selection Action Pill
        selection_strip = tk.Frame(workspace, bg=WHITE, highlightbackground=LAV2, highlightthickness=1)
        self.selection_strip = selection_strip
        self.selection_count = tk.Label(selection_strip, text='0 selected', fg=PURPLE, bg=WHITE,
                                        font=('Segoe UI', 9, 'bold'), padx=12)
        self.selection_count.pack(side='left', pady=6)
        self._button(selection_strip, 'Delete', self.delete_selected, width=76, height=30,
                     kind='danger', font_size=9, radius=8).pack(side='left', padx=(0, 4), pady=4)
        self._button(selection_strip, 'Done', self.clear_selection, width=62, height=30,
                     font_size=9, radius=8).pack(side='left', padx=(0, 6), pady=4)
        self._selection_strip_update()

        # 6. Miro-style Floating Bottom-Right Viewport Zoom Pill
        zoom_shadow = tk.Frame(workspace, bg=SHADOW)
        zoom_shadow.place(relx=1.0, rely=1.0, x=-16, y=-16, anchor='se')
        zoom_pill = tk.Frame(zoom_shadow, bg=WHITE, highlightbackground=BDR, highlightthickness=1)
        zoom_pill.pack(padx=(0, 2), pady=(0, 2))
        self._button(zoom_pill, '−', lambda: self.change_view(1 / 1.2), width=30, height=30,
                     radius=8, tooltip='Zoom out (Ctrl+-)').pack(side='left', padx=(4, 0), pady=4)
        self.view_label = tk.Label(zoom_pill, text='115%', bg=WHITE, fg=TEXT,
                                   font=('Segoe UI', 9, 'bold'), width=5)
        self.view_label.pack(side='left')
        self._button(zoom_pill, '+', lambda: self.change_view(1.2), width=30, height=30,
                     radius=8, tooltip='Zoom in (Ctrl++)').pack(side='left', pady=4)
        tk.Frame(zoom_pill, bg=BDR, width=1, height=18).pack(side='left', padx=4)
        self._button(zoom_pill, 'Fit', self.fit_page, width=38, height=30, radius=8,
                     font_size=9, tooltip='Fit page to window').pack(side='left', padx=(0, 4), pady=4)

        # Two-dimensional writing-area navigation and clickable page overview.
        nav_shadow = tk.Frame(workspace, bg=SHADOW)
        nav_shadow.place(x=84, rely=1.0, y=-16, anchor='sw')
        self.nav_shadow = nav_shadow
        nav = tk.Frame(nav_shadow, bg=WHITE, highlightbackground=BDR, highlightthickness=1)
        nav.pack(padx=(0, 2), pady=(0, 3))
        left_nav=tk.Frame(nav,bg=WHITE)
        left_nav.pack(side='left',padx=(9,6),pady=6)
        tk.Label(left_nav,text='WRITING AREA  ·  2D NAV',bg=WHITE,fg=MUTED,
                 font=('Segoe UI',8,'bold')).grid(row=0,column=0,columnspan=4,pady=(0,3),sticky='w')
        self._button(left_nav,'↑',self.up_window,width=30,height=27,radius=8,
                     tooltip='Move writing area up (Up arrow)').grid(row=1,column=1,padx=2,pady=1)
        self._button(left_nav,'←',self.previous_window,width=30,height=27,radius=8,
                     tooltip='Move left (Left arrow)').grid(row=2,column=0,padx=2,pady=1)
        self._button(left_nav,'↓',self.down_window,width=30,height=27,radius=8,
                     tooltip='Move down (Down arrow)').grid(row=2,column=1,padx=2,pady=1)
        self._button(left_nav,'→',self.next_window,width=30,height=27,radius=8,
                     tooltip='Move right (Right arrow)').grid(row=2,column=2,padx=2,pady=1)
        self._button(left_nav,'↵  New line',self.next_line,width=97,height=27,radius=8,
                     tooltip='New line (Enter) — returns to left margin').grid(row=3,column=0,columnspan=3,pady=(5,0))
        right_nav=tk.Frame(nav,bg=WHITE)
        right_nav.pack(side='left',padx=(2,10),pady=7)
        self.area_mode_button=self._button(right_nav,'Move Area',self.toggle_area_move,
                width=102,height=28,radius=8,kind='outline',tooltip='Drag on paper to place writing window; Tab switches Ink/Navigate')
        self.area_mode_button.pack(pady=(1,5))
        self.nav_map=tk.Canvas(right_nav,width=118,height=85,bg=WHITE,highlightbackground=BDR,
                               highlightthickness=1,cursor='hand2')
        self.nav_map.pack()
        self.nav_map.bind('<Button-1>',self.on_nav_map_click)
        HoverTooltip(self.nav_map,'Click anywhere to center the writing area on that page location')
        self.root.after_idle(self._draw_nav_map)

    # ---------------- 1. Visual Popovers (Stroke Thickness & Shapes) ----------------
    def open_width_popover(self):
        self._prepare_dialog()
        pop = VisualPopover(self.width_button, width=292, height=106)
        tk.Label(pop.card, text='STROKE THICKNESS', fg=MUTED, bg=WHITE,
                 font=('Segoe UI', 8, 'bold')).pack(anchor='w', padx=14, pady=(10, 6))

        row = tk.Frame(pop.card, bg=WHITE)
        row.pack(fill='x', padx=10, pady=(0, 8))

        widths = [1.5, 2.5, 3.5, 5.0, 8.0, 12.0]
        for w in widths:
            selected = abs(self.width - w) < 0.05
            cell = tk.Canvas(row, width=42, height=56, bg=WHITE, highlightthickness=0, cursor='hand2')
            cell.pack(side='left', padx=2)
            bg = LAV if selected else WHITE
            bdr = PURPLE if selected else BDR
            rounded(cell, 2, 2, 40, 54, 10, fill=bg, outline=bdr, width=1.6 if selected else 1)
            r = clamp(w * 0.95, 2.0, 11.5)
            cell.create_oval(21 - r, 22 - r, 21 + r, 22 + r, fill=self.color, outline='')
            cell.create_text(21, 43, text=f'{w:g}px', fill=PURPLE if selected else MUTED,
                             font=('Segoe UI', 8, 'bold' if selected else 'normal'))
            cell.bind('<Button-1>', lambda _e, val=w, p=pop: (self.set_width(val), p.destroy()))

    def open_shape_popover(self):
        self.tool = 'shape'
        self._update_tool_buttons()
        self._prepare_dialog()
        anchor = self.rail_buttons['shape']
        pop = VisualPopover(anchor, width=264, height=106, offset_x=115, offset_y=-48)
        tk.Label(pop.card, text='GEOMETRIC SHAPES', fg=MUTED, bg=WHITE,
                 font=('Segoe UI', 8, 'bold')).pack(anchor='w', padx=14, pady=(10, 6))

        row = tk.Frame(pop.card, bg=WHITE)
        row.pack(fill='x', padx=10, pady=(0, 8))

        items = [
            ('line', 'Line'),
            ('arrow', 'Arrow'),
            ('rectangle', 'Rect'),
            ('ellipse', 'Oval'),
            ('triangle', 'Tri'),
        ]
        for stype, slabel in items:
            selected = (self.shape == stype)
            cell = tk.Canvas(row, width=44, height=56, bg=WHITE, highlightthickness=0, cursor='hand2')
            cell.pack(side='left', padx=2)
            bg = LAV if selected else WHITE
            bdr = PURPLE if selected else BDR
            rounded(cell, 2, 2, 42, 54, 10, fill=bg, outline=bdr, width=1.6 if selected else 1)
            draw_icon(cell, f'shape_{stype}', 22, 22, size=20,
                      color=PURPLE if selected else TEXT, accent=PURPLE, active=selected)
            cell.create_text(22, 43, text=slabel, fill=PURPLE if selected else MUTED,
                             font=('Segoe UI', 8, 'bold' if selected else 'normal'))
            cell.bind('<Button-1>', lambda _e, t=stype, p=pop: (self.set_shape(t), p.destroy()))

    # ---------------- 2. Smooth Viewport & Writing-Box Panning ----------------
    def _animate_origin_to(self, target_origin, steps=10, interval_ms=16):
        if self._origin_anim_id:
            self.root.after_cancel(self._origin_anim_id)
            self._origin_anim_id = None
        start_x, start_y = self.origin
        dx = target_origin[0] - start_x
        dy = target_origin[1] - start_y
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            self.origin = list(target_origin)
            self.repaint()
            self._draw_nav_map()
            self._keep_area_in_view()
            return

        def step(i):
            if i >= steps or self._closing:
                self.origin = list(target_origin)
                self._origin_anim_id = None
                self.repaint()
                self._draw_nav_map()
                self._keep_area_in_view()
                return
            t = i / float(steps)
            ease = 1.0 - (1.0 - t) ** 3  # cubic ease-out
            self.origin = [start_x + dx * ease, start_y + dy * ease]
            self.repaint()
            self._draw_nav_map()
            self._origin_anim_id = self.root.after(interval_ms, lambda: step(i + 1))

        step(1)

    def _smooth_scroll_to(self, target_fx, target_fy, steps=9, interval_ms=16):
        if self._view_anim_id:
            self.root.after_cancel(self._view_anim_id)
            self._view_anim_id = None
        c = self.canvas
        sx = c.xview()[0]
        sy = c.yview()[0]
        dfx = target_fx - sx
        dfy = target_fy - sy

        def step(i):
            if i >= steps or self._closing:
                c.xview_moveto(target_fx)
                c.yview_moveto(target_fy)
                self._view_anim_id = None
                return
            t = i / float(steps)
            ease = 1.0 - (1.0 - t) ** 3
            c.xview_moveto(sx + dfx * ease)
            c.yview_moveto(sy + dfy * ease)
            self._view_anim_id = self.root.after(interval_ms, lambda: step(i + 1))

        step(1)

    # ---------------- 3. Sticky Notes & Images (Insert, Clipboard, OS Drag&Drop) ----------------
    def open_sticky_dialog(self, location=None, edit_stroke=None):
        self._prepare_dialog()
        if edit_stroke is not None:
            dlg = StickyNoteDialog(self.root, initial_text=edit_stroke.text, initial_color=edit_stroke.color)
            self.root.wait_window(dlg)
            if dlg.result:
                edit_stroke.text, edit_stroke.color = dlg.result
                self._mark_dirty()
                self.repaint()
                self.refresh_pages()
            return

        if location is None:
            location = (self.origin[0] + 40, self.origin[1] + 40)
        dlg = StickyNoteDialog(self.root, initial_color=self.sticky_color)
        self.root.wait_window(dlg)
        if dlg.result:
            text, col = dlg.result
            self.sticky_color = col
            self.drawing.add_sticky(location[0], location[1], text, color=col)
            self._mark_dirty()
            self.repaint()
            self.refresh_pages()
            self.set_status('Sticky note added · Use Select (5) to drag or double-click to edit')

    def insert_image_dialog(self, location=None):
        self._prepare_dialog()
        if not HAS_PIL:
            messagebox.showinfo('TouchInk', 'Pillow is required to insert images.', parent=self.root)
            return
        path = filedialog.askopenfilename(
            parent=self.root, title='Insert image onto page',
            filetypes=[('Image files', '*.png *.jpg *.jpeg *.webp *.bmp *.gif')]
        )
        if path:
            self.insert_image_file(path, location=location)

    def insert_image_file(self, path, location=None):
        if not HAS_PIL:
            return
        try:
            pil_img = Image.open(path).convert('RGBA')
            self._place_pil_image(pil_img, location=location)
            self.set_status('Inserted image: ' + os.path.basename(path))
        except Exception as exc:
            messagebox.showerror('Image error', f'Could not load image:\n{exc}', parent=self.root)

    def paste_from_clipboard(self):
        if not HAS_PIL:
            return
        try:
            clip = ImageGrab.grabclipboard()
        except Exception:
            clip = None
        if isinstance(clip, list):
            for p in clip:
                if os.path.isfile(p) and p.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
                    self.insert_image_file(p)
                    return
        elif isinstance(clip, Image.Image):
            self._place_pil_image(clip.convert('RGBA'))
            self.set_status('Pasted image from clipboard')
            return
        try:
            txt = self.root.clipboard_get()
            if txt and txt.strip():
                self.drawing.add_sticky(self.origin[0] + 35, self.origin[1] + 35,
                                        txt.strip()[:500], color=self.sticky_color)
                self._mark_dirty()
                self.repaint()
                self.refresh_pages()
                self.set_status('Pasted clipboard text as Sticky Note')
        except tk.TclError:
            pass

    def _place_pil_image(self, pil_img, location=None):
        pw, ph = self.page_dims()
        max_w = pw * 0.48
        max_h = ph * 0.48
        w, h = pil_img.size
        if w > max_w or h > max_h:
            ratio = min(max_w / max(1, w), max_h / max(1, h))
            w = max(40, int(round(w * ratio)))
            h = max(40, int(round(h * ratio)))
            pil_img = pil_img.resize((w, h), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        pil_img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        if location is None:
            location = (self.origin[0] + 30, self.origin[1] + 30)
        self.drawing.add_image(location[0], location[1], b64, w, h)
        self._mark_dirty()
        self.repaint()
        self.refresh_pages()

    def _enable_os_file_drop(self):
        """Enable native Windows Explorer Drag-and-Drop onto the TouchInk window."""
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            from ctypes import wintypes
            shell32 = ctypes.windll.shell32
            user32 = ctypes.windll.user32
            GWL_WNDPROC = -4
            WM_DROPFILES = 0x0233

            u32_get_ancestor = user32.GetAncestor
            u32_get_ancestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            u32_get_ancestor.restype = ctypes.c_void_p
            hwnd = u32_get_ancestor(self.root.winfo_id(), 2)
            if not hwnd:
                return

            shell32.DragAcceptFiles.argtypes = [ctypes.c_void_p, wintypes.BOOL]
            shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
            shell32.DragQueryFileW.restype = wintypes.UINT
            shell32.DragFinish.argtypes = [ctypes.c_void_p]

            WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            set_ptr = user32.SetWindowLongPtrW if hasattr(user32, 'SetWindowLongPtrW') else user32.SetWindowLongW
            call_prev = user32.CallWindowProcW
            set_ptr.argtypes = [ctypes.c_void_p, ctypes.c_int, WNDPROC]
            set_ptr.restype = ctypes.c_void_p
            call_prev.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            call_prev.restype = ctypes.c_ssize_t

            old_proc = None

            def wnd_proc(h, msg, wp, lp):
                if msg == WM_DROPFILES:
                    try:
                        count = shell32.DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
                        for idx in range(count):
                            length = shell32.DragQueryFileW(wp, idx, None, 0) + 1
                            buf = ctypes.create_unicode_buffer(length)
                            shell32.DragQueryFileW(wp, idx, buf, length)
                            fpath = buf.value
                            if fpath.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')):
                                self.root.after(10, lambda p=fpath, k=idx: self.insert_image_file(
                                    p, location=(self.origin[0] + 30 + k * 28, self.origin[1] + 30 + k * 28)))
                    finally:
                        shell32.DragFinish(wp)
                    return 0
                return call_prev(old_proc, h, msg, wp, lp)

            self._drop_wndproc = WNDPROC(wnd_proc)
            old_proc = set_ptr(hwnd, GWL_WNDPROC, self._drop_wndproc)
            shell32.DragAcceptFiles(hwnd, True)
        except Exception:
            pass

    # ---------------- Draggable Floating Ink Palette ----------------
    def _start_palette_drag(self, event):
        self._palette_drag_origin = (
            event.x_root - self.palette_shadow.winfo_x(),
            event.y_root - self.palette_shadow.winfo_y()
        )

    def _move_palette_drag(self, event):
        if not self._palette_drag_origin:
            return
        max_x = max(10, self.workspace.winfo_width() - self.palette_shadow.winfo_width() - 10)
        max_y = max(10, self.workspace.winfo_height() - self.palette_shadow.winfo_height() - 10)
        nx = clamp(event.x_root - self._palette_drag_origin[0], 10, max_x)
        ny = clamp(event.y_root - self._palette_drag_origin[1], 10, max_y)
        self._palette_pos = (nx, ny)
        self.palette_shadow.place(x=nx, y=ny, relx=0.0, rely=0.0, anchor='nw')

    # ---------------- Right Sidebar & Drag-and-Drop Page Reorder ----------------
    def _build_sidebar(self):
        hdr = tk.Frame(self.side_border, bg=WHITE, height=52)
        hdr.pack(fill='x', padx=10)
        hdr.pack_propagate(False)
        self.pages_tab = self._button(hdr, 'Pages', lambda: self.set_sidebar('pages'),
                                      width=124, height=34, kind='on', radius=9)
        self.pages_tab.pack(side='left', pady=9)
        self.books_tab = self._button(hdr, 'Notebooks', lambda: self.set_sidebar('books'),
                                      width=134, height=34, radius=9)
        self.books_tab.pack(side='right', pady=9)
        tk.Frame(self.side_border, bg=BDR, height=1).pack(fill='x')

        self.side_body = tk.Frame(self.side_border, bg=WHITE)
        self.side_body.pack(fill='both', expand=True)

        self.meta = tk.Frame(self.side_body, bg=LAV, height=68)
        self.meta.pack(fill='x', padx=12, pady=(12, 6))
        self.meta.pack_propagate(False)
        meta_ic = tk.Canvas(self.meta, width=32, height=32, bg=LAV, highlightthickness=0)
        meta_ic.pack(side='left', padx=(12, 8), pady=18)
        draw_icon(meta_ic, 'pages', 16, 16, size=22, color=PURPLE, active=True)

        self.meta_name = tk.Label(
            self.meta, text='My Notebook', fg=TEXT, bg=LAV, font=('Segoe UI', 10, 'bold'),
            wraplength=190, justify='left', anchor='w'
        )
        self.meta_name.pack(anchor='w', pady=(14, 1))
        self.meta_count = tk.Label(self.meta, text='1 page · Drag cards to reorder',
                                   fg=MUTED, bg=LAV, font=('Segoe UI', 8))
        self.meta_count.pack(anchor='w')

        search = tk.Frame(self.side_body, bg=SUBTLE, highlightbackground=BDR, highlightthickness=1)
        search.pack(fill='x', padx=12, pady=(4, 7))
        tk.Label(search, text='⌕', fg=PURPLE, bg=SUBTLE, font=('Segoe UI', 15)).pack(side='left', padx=(10, 3))
        self.page_search_entry = tk.Entry(search, textvariable=self.page_query,
                                          bg=SUBTLE, fg=TEXT, insertbackground=PURPLE,
                                          relief='flat', bd=0, highlightthickness=0,
                                          font=('Segoe UI', 10))
        self.page_search_entry.pack(side='left', fill='x', expand=True, pady=9, padx=(0, 6))
        self.page_search_hint = tk.Label(search, text='Find page', fg=FAINT, bg=SUBTLE,
                                         font=('Segoe UI', 9), cursor='xterm')
        self.page_search_hint.place(x=40, y=9)
        self.page_search_hint.bind('<Button-1>', lambda _e: self.page_search_entry.focus_set())
        self.page_search_entry.bind('<FocusIn>', lambda _e: self.page_search_hint.place_forget())
        self.page_search_entry.bind('<FocusOut>', lambda _e: self._set_search_hint())
        self.page_search_entry.bind('<Return>', lambda _e: self._search_first_page())

        self.pages_view = tk.Frame(self.side_body, bg=WHITE)
        self.pages_view.pack(fill='both', expand=True)
        self.page_canvas = tk.Canvas(self.pages_view, bg=WHITE, highlightthickness=0, bd=0)
        self.page_canvas.pack(side='left', fill='both', expand=True)
        bar = tk.Scrollbar(self.pages_view, orient='vertical', command=self.page_canvas.yview, width=7)
        bar.pack(side='right', fill='y')
        self.page_canvas.configure(yscrollcommand=bar.set)
        self.page_inner = tk.Frame(self.page_canvas, bg=WHITE)
        self.page_window = self.page_canvas.create_window((0, 0), window=self.page_inner, anchor='nw')
        self.page_inner.bind('<Configure>', lambda _e: self.page_canvas.configure(
            scrollregion=self.page_canvas.bbox('all')))
        self.page_canvas.bind('<Configure>', lambda e: self.page_canvas.itemconfigure(
            self.page_window, width=e.width))
        self.page_canvas.bind('<MouseWheel>', lambda e: self.page_canvas.yview_scroll(
            -1 if e.delta > 0 else 1, 'units'))

        self.books_view = tk.Frame(self.side_body, bg=WHITE)
        self.book_summary = tk.Label(
            self.books_view, text='Notebooks are stored locally in Documents/TouchInk Studio.',
            bg=WHITE, fg=MUTED, font=('Segoe UI', 9), wraplength=235, justify='left'
        )
        self.book_summary.pack(fill='x', padx=16, pady=(18, 12))
        for text, cmd in [
            ('New Notebook', self.new_notebook),
            ('Open Notebook…', self.open_notebook),
            ('Save Notebook As…', self.save_as),
            ('Insert Image…', self.insert_image_dialog),
            ('Add Sticky Note…', self.open_sticky_dialog),
            ('Export Current Page (PNG)', lambda: self.export_page('png')),
            ('Export Current Page (SVG)', lambda: self.export_page('svg')),
        ]:
            self._button(self.books_view, text, cmd, width=240, height=36,
                         kind='outline', font_size=9).pack(pady=3)

        foot = tk.Frame(self.side_border, bg=WHITE)
        foot.pack(side='bottom', fill='x', padx=12, pady=12)
        self.page_add = self._button(foot, '+ Add New Page', self.new_page,
                                     width=260, height=38, kind='on')
        self.page_add.pack(fill='x')

    def _update_meta(self):
        self.notebook_name.configure(text=self.book['title'][:26])
        self.meta_name.configure(text=self.book['title'][:42])
        count = len(self.book['pages'])
        self.meta_count.configure(text=f'{count} page' + ('' if count == 1 else 's') + ' · Drag to reorder')
        self.page_counter.configure(text=f'{self.book["page_index"] + 1} / {count}')

    def _update_paper_pills(self):
        if not hasattr(self, 'paper_pills'):
            return
        for ptype, btn in self.paper_pills.items():
            btn.set(selected=(self.paper == ptype))

    def set_sidebar(self, tab):
        self.side_tab = tab
        if tab == 'pages':
            self.page_search_entry.master.pack(fill='x', padx=12, pady=(4, 7))
        else:
            self.page_search_entry.master.pack_forget()
        self.pages_tab.set(selected=(tab == 'pages'))
        self.books_tab.set(selected=(tab == 'books'))
        if tab == 'pages':
            self.books_view.pack_forget()
            self.pages_view.pack(fill='both', expand=True)
            self.page_add.set(text='+ Add New Page')
            self.page_add.command = self.new_page
        else:
            self.pages_view.pack_forget()
            self.books_view.pack(fill='both', expand=True)
            self.page_add.set(text='+ New Notebook')
            self.page_add.command = self.new_notebook

    def toggle_sidebar(self):
        if self.focus_mode:
            self.toggle_focus_mode()
            return
        if self.side_visible:
            self.side_wrap.pack_forget()
        else:
            self.side_wrap.pack(side='right', fill='y', padx=(0, 12), pady=(12, 12), before=self.workspace)
        self.side_visible = not self.side_visible
        self.sidebar_toggle_btn.set(selected=self.side_visible)
        self.root.after_idle(self.repaint)

    def refresh_pages(self):
        if not hasattr(self, 'page_inner'):
            return
        self._sync()
        for child in self.page_inner.winfo_children():
            child.destroy()
        self._page_cards = []
        query = self.page_query.get().strip().casefold()
        visible_pages = [(i, p) for i, p in enumerate(self.book['pages'])
                         if not query or query in p.get('name', '').casefold() or
                         any(query in s.get('text', '').casefold() for s in p.get('strokes', []) if isinstance(s, dict))]
        if not visible_pages:
            tk.Label(self.page_inner, text='No matching pages', bg=WHITE, fg=MUTED,
                     font=('Segoe UI', 10), pady=24).pack(fill='x')
        for index, page in visible_pages:
            selected = (index == self.book['page_index'])
            bg = LAV if selected else WHITE
            border_col = PURPLE if selected else BDR
            card = tk.Frame(self.page_inner, bg=bg, highlightbackground=border_col,
                            highlightthickness=2 if selected else 1)
            card.pack(fill='x', padx=10, pady=5)
            self._page_cards.append(card)

            grip = tk.Canvas(card, width=16, height=76, bg=bg, highlightthickness=0, cursor='sb_v_double_arrow')
            grip.pack(side='left', padx=(4, 2))
            draw_icon(grip, 'grip', 8, 38, size=16)

            th = tk.Canvas(card, width=64, height=84, bg=WHITE, highlightbackground=BDR,
                           highlightthickness=1, cursor='hand2')
            th.pack(side='left', padx=(2, 8), pady=7)
            self._thumbnail(th, page)

            info = tk.Frame(card, bg=bg)
            info.pack(side='left', fill='both', expand=True, pady=10)
            title = tk.Label(
                info, text=f'{index + 1}. {page["name"][:20]}',
                font=('Segoe UI', 10, 'bold'), fg=PURPLE if selected else TEXT,
                bg=bg, anchor='w', wraplength=135, justify='left'
            )
            title.pack(fill='x')
            tk.Label(
                info, text=f'{len(page.get("strokes", []))} items · {page.get("paper", "ruled")}',
                fg=MUTED, bg=bg, font=('Segoe UI', 8)
            ).pack(anchor='w', pady=(4, 0))

            menu = tk.Label(card, text='⋯', fg=MUTED, bg=bg, font=('Segoe UI', 12, 'bold'), cursor='hand2')
            menu.pack(side='right', padx=6, pady=(0, 34))
            menu.bind('<Button-1>', lambda _e, i=index: self.page_menu(i))

            for w in (card, grip, th, info, title):
                w.bind('<ButtonPress-1>', lambda e, i=index: self._on_page_press(e, i))
                w.bind('<B1-Motion>', self._on_page_drag)
                w.bind('<ButtonRelease-1>', self._on_page_release)

    def _on_page_press(self, event, index):
        self._page_drag_idx = index
        self._page_drag_start_y = event.y_root
        self._page_dragging = False

    def _on_page_drag(self, event):
        # Reordering a filtered subset would be ambiguous. Search = navigate only.
        if self.page_query.get().strip():
            return
        if self._page_drag_idx is None:
            return
        if not self._page_dragging and abs(event.y_root - self._page_drag_start_y) > 8:
            self._page_dragging = True
            self._page_cards[self._page_drag_idx].configure(highlightbackground='#a78bfa', highlightthickness=2)
        if not self._page_dragging:
            return

        target = self._compute_drop_index(event.y_root)
        if self._drop_line:
            self._drop_line.destroy()
            self._drop_line = None

        if self._page_cards:
            self._drop_line = tk.Frame(self.page_inner, bg=PURPLE, height=3)
            if target < len(self._page_cards):
                y_pos = max(0, self._page_cards[target].winfo_y() - 3)
            else:
                last = self._page_cards[-1]
                y_pos = last.winfo_y() + last.winfo_height() + 1
            self._drop_line.place(x=10, y=y_pos, width=max(40, self.page_inner.winfo_width() - 20))

    def _compute_drop_index(self, y_root):
        for idx, card in enumerate(self._page_cards):
            mid = card.winfo_rooty() + card.winfo_height() / 2
            if y_root < mid:
                return idx
        return len(self._page_cards)

    def _on_page_release(self, event):
        if self.page_query.get().strip():
            if self._page_drag_idx is not None:
                self.select_page(self._page_drag_idx)
            self._page_drag_idx = None
            self._page_dragging = False
            return
        if self._drop_line:
            self._drop_line.destroy()
            self._drop_line = None
        src = self._page_drag_idx
        was_dragging = self._page_dragging
        self._page_drag_idx = None
        self._page_dragging = False
        if src is None:
            return
        if not was_dragging:
            self.select_page(src)
            return
        dst = self._compute_drop_index(event.y_root)
        if dst > src:
            dst -= 1
        if dst != src and 0 <= dst < len(self.book['pages']):
            self._sync()
            cur_page = self.book['pages'][self.book['page_index']]
            moved = self.book['pages'].pop(src)
            self.book['pages'].insert(dst, moved)
            self.book['page_index'] = self.book['pages'].index(cur_page)
            self._mark_dirty()
            self._update_meta()
            self.set_status(f'Moved "{moved["name"]}" to position {dst + 1}')
        self.refresh_pages()

    def _thumbnail(self, c, page):
        c.delete('all')
        is_landscape = page.get('orientation', 'portrait') == 'landscape'
        doc_w, doc_h = (PAGE_H, PAGE_W) if is_landscape else (PAGE_W, PAGE_H)
        k = min(58 / doc_w, 78 / doc_h)
        offset_x = (64 - doc_w * k) / 2
        offset_y = (84 - doc_h * k) / 2
        c.create_rectangle(offset_x, offset_y, offset_x + doc_w * k, offset_y + doc_h * k,
                           fill=WHITE, outline=BDR)
        typ = page.get('paper', 'ruled')
        if typ == 'ruled':
            for y in range(138, doc_h, 110):
                sy = offset_y + y * k
                c.create_line(offset_x + 4, sy, offset_x + doc_w * k - 4, sy, fill=LINE)
            c.create_line(offset_x + 74 * k, offset_y + 3, offset_x + 74 * k,
                          offset_y + doc_h * k - 3, fill='#f0bbc9')
        elif typ == 'grid':
            for y in range(0, doc_h, 110):
                sy = offset_y + y * k
                c.create_line(offset_x, sy, offset_x + doc_w * k, sy, fill='#ebedf6')
            for x in range(0, doc_w, 110):
                sx = offset_x + x * k
                c.create_line(sx, offset_y, sx, offset_y + doc_h * k, fill='#ebedf6')
        for s in drawing_from_page(page).strokes:
            kind = s.kind
            points = s.points
            if not points:
                continue
            if kind == 'sticky':
                x, y = points[0]
                w = (s.box_w or 240) * k
                h = (s.box_h or 200) * k
                c.create_rectangle(offset_x + x * k, offset_y + y * k,
                                   offset_x + x * k + w, offset_y + y * k + h,
                                   fill=s.color, outline='#cbd5e1')
                continue
            if kind == 'image':
                x, y = points[0]
                w = (s.box_w or 200) * k
                h = (s.box_h or 150) * k
                c.create_rectangle(offset_x + x * k, offset_y + y * k,
                                   offset_x + x * k + w, offset_y + y * k + h,
                                   fill='#e0e7ff', outline='#818cf8')
                continue
            if kind == 'shape':
                points = shape_path(s.shape, points, 12)
            if kind == 'text':
                x, y = points[0]
                c.create_text(offset_x + x * k, offset_y + y * k, text=s.text[:18],
                              fill=s.color, anchor='sw', font=('Segoe UI', 5))
                continue
            coords = []
            for x, y in points:
                coords.extend((offset_x + x * k, offset_y + y * k))
            color = WHITE if kind == 'eraser' else s.color
            if len(coords) > 2:
                c.create_line(*coords, fill=color, width=max(.8, float(s.width) * k), capstyle=tk.ROUND)

    def page_menu(self, index):
        self._prepare_dialog()
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label='Open page', command=lambda: self.select_page(index))
        menu.add_command(label='Rename page', command=lambda: self.rename_page(index))
        menu.add_command(label='Delete page', command=lambda: self.delete_page(index))
        menu.add_command(label='Page orientation…', command=lambda: self.orientation_menu(index))
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()

    def _find_page(self):
        if self.side_tab != 'pages':
            self.set_sidebar('pages')
        if not self.side_visible and not self.focus_mode:
            self.toggle_sidebar()
        if self.focus_mode:
            self.toggle_focus_mode()
        self.page_search_entry.focus_set()

    def _filter_pages(self):
        if hasattr(self, 'page_inner'):
            self.refresh_pages()
        self._set_search_hint()

    def _set_search_hint(self):
        if not hasattr(self, 'page_search_hint'):
            return
        if not self.page_query.get() and self.page_search_entry.focus_get() != self.page_search_entry:
            self.page_search_hint.place(x=40, y=9)
        else:
            self.page_search_hint.place_forget()

    def _update_canvas_info(self):
        if not hasattr(self, 'canvas_page_title'):
            return
        page = self.book['pages'][self.book['page_index']]
        self.canvas_page_title.set(page.get('name', 'Untitled page')[:40])
        self.canvas_page_info.set(page.get('paper', 'ruled').title() + '  ·  ' +
                                  page.get('orientation', 'landscape').title())

    def toggle_writing_guides(self):
        self.show_writing_guides = not self.show_writing_guides
        self.guide_btn.set(selected=self.show_writing_guides)
        self.repaint()
        self.set_status('Touchpad writing guides ' + ('visible' if self.show_writing_guides else 'hidden'))

    def toggle_focus_mode(self):
        """Distraction-free writing, with F11 and a visible reversible control."""
        self.focus_mode = not self.focus_mode
        if self.focus_mode:
            self.side_wrap.pack_forget()
            self.rail_shadow.place_forget()
            self.focus_btn.set(text='Exit Focus', selected=True)
            self.set_status('Focus mode · F11 to restore notebook panels')
        else:
            if self.side_visible:
                self.side_wrap.pack(side='right', fill='y', padx=(0, 12),
                                    pady=(12, 12), before=self.workspace)
            self.rail_shadow.place(x=16, rely=0.5, anchor='w')
            self.focus_btn.set(text='Focus', selected=False)
            self.set_status('Workspace panels restored')
        self.root.after_idle(self.repaint)

    def new_page_gallery(self):
        """Visible new-page template picker rather than a generic text-only dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title('New page · TouchInk Studio')
        dialog.configure(bg=WHITE)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry('526x424')
        tk.Label(dialog, text='Create a page', bg=WHITE, fg=TEXT,
                 font=('Segoe UI', 18, 'bold')).pack(anchor='w', padx=24, pady=(20, 2))
        tk.Label(dialog, text='Choose your paper and layout. You can change them later.',
                 bg=WHITE, fg=MUTED, font=('Segoe UI', 10)).pack(anchor='w', padx=24, pady=(0, 16))
        grid = tk.Frame(dialog, bg=WHITE)
        grid.pack(padx=20, fill='both', expand=True)
        templates = [('ruled', 'landscape', 'Ruled · Wide'),
                     ('grid', 'landscape', 'Grid · Wide'),
                     ('blank', 'landscape', 'Blank · Wide'),
                     ('ruled', 'portrait', 'Ruled · Portrait'),
                     ('grid', 'portrait', 'Grid · Portrait'),
                     ('blank', 'portrait', 'Blank · Portrait')]
        def create(paper, orientation):
            dialog.destroy()
            self.new_page(paper=paper, orientation=orientation)
            self.set_status(f'New {paper} {orientation} page created')
        for i, (paper, orientation, label) in enumerate(templates):
            card = tk.Canvas(grid, width=145, height=118, bg=WHITE, highlightthickness=0,
                             cursor='hand2')
            card.grid(row=i//3, column=i%3, padx=8, pady=6)
            rounded(card, 2, 2, 143, 116, 12, fill=SUBTLE, outline=BDR, width=1)
            dw, dh = (97, 55) if orientation == 'landscape' else (59, 72)
            left, top = (145-dw)/2, 13
            card.create_rectangle(left+2, top+3, left+dw+2, top+dh+3, fill=SHADOW, outline='')
            card.create_rectangle(left, top, left+dw, top+dh, fill=WHITE, outline=BDR)
            if paper == 'ruled':
                for yy in range(9, int(dh)-5, 9):
                    card.create_line(left+7, top+yy, left+dw-6, top+yy, fill=LINE)
                card.create_line(left+13, top+5, left+13, top+dh-5, fill='#f3b8c6')
            elif paper == 'grid':
                for xx in range(10, int(dw)-4, 11):
                    card.create_line(left+xx, top+5, left+xx, top+dh-5, fill=LINE)
                for yy in range(9, int(dh)-4, 11):
                    card.create_line(left+5, top+yy, left+dw-5, top+yy, fill=LINE)
            card.create_text(72, 101, text=label, fill=TEXT, font=('Segoe UI', 9, 'bold'))
            card.bind('<Button-1>', lambda _e, p=paper, o=orientation: create(p, o))
            card.bind('<Enter>', lambda _e, w=card: w.configure(bg=LAV))
            card.bind('<Leave>', lambda _e, w=card: w.configure(bg=WHITE))
        dialog.bind('<Escape>', lambda _e: dialog.destroy())
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width())//2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height())//2
        dialog.geometry(f'+{max(0,x)}+{max(0,y)}')

    def open_menu(self):
        self._prepare_dialog()
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label='Connect RAW touchpad', command=self.start_raw)
        menu.add_command(label='Switch Ink / Navigate (Tab)', command=self.toggle_ink_mode)
        menu.add_command(label='Move writing area up', command=self.up_window)
        menu.add_command(label='Move writing area down', command=self.down_window)
        menu.add_command(label='New notebook', command=self.new_notebook)
        menu.add_command(label='Open notebook', command=self.open_notebook)
        menu.add_command(label='Save notebook', command=self.save)
        menu.add_separator()
        menu.add_command(label='Insert Image… (I)', command=self.insert_image_dialog)
        menu.add_command(label='Add Sticky Note… (S)', command=self.open_sticky_dialog)
        menu.add_command(label='Paste Image / Sticky Note (Ctrl+V)', command=self.paste_from_clipboard)
        menu.add_separator()
        menu.add_command(label='New page from template…', command=self.new_page_gallery)
        menu.add_command(label='Focus mode (F11)', command=self.toggle_focus_mode)
        menu.add_command(label='Paper template…', command=self.paper_menu)
        menu.add_command(label='Page orientation…', command=self.orientation_menu)
        self._auto_pan_menu_var = tk.BooleanVar(value=self.auto_pan)
        menu.add_checkbutton(label='Auto-pan after lift near edge', variable=self._auto_pan_menu_var,
                             command=lambda: self.set_autopan(self._auto_pan_menu_var.get()))
        self._mouse_menu_var = tk.BooleanVar(value=self.mouse_test)
        menu.add_checkbutton(label='Allow mouse drawing (testing)', variable=self._mouse_menu_var,
                             command=lambda: self.set_mouse_test(self._mouse_menu_var.get()))
        menu.add_separator()
        menu.add_command(label='Export PNG', command=lambda: self.export_page('png'))
        menu.add_command(label='Export SVG', command=lambda: self.export_page('svg'))
        menu.add_separator()
        menu.add_command(label='Quit', command=self.close)
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()

    def set_autopan(self, value):
        self.auto_pan = bool(value)
        self.repaint()
        self.set_status('Auto-pan ' + ('enabled' if self.auto_pan else 'disabled'))

    def set_mouse_test(self, value):
        self.mouse_test = bool(value)
        self.set_status('Mouse drawing ' + ('enabled' if self.mouse_test else 'disabled'))

    def paper_menu(self):
        self._prepare_dialog()
        menu = tk.Menu(self.root, tearoff=0)
        for typ in PAPER_TYPES:
            menu.add_command(label=typ.title() + ' paper', command=lambda t=typ: self.set_paper(t))
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()

    def orientation_menu(self, index=None):
        self._prepare_dialog()
        menu = tk.Menu(self.root, tearoff=0)
        for name in ('landscape', 'portrait'):
            menu.add_command(label=name.title(), command=lambda n=name: self.set_orientation(n, index))
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()

    def set_orientation(self, name, index=None):
        if name not in ('landscape', 'portrait'):
            return
        self._sync()
        index = self.book['page_index'] if index is None else index
        page = self.book['pages'][index]
        if page.get('strokes'):
            ok = messagebox.askyesno(
                'Change page layout',
                'This page contains writing. Changing orientation does not scale the ink, '
                'so content near the far edge might be outside the new page. Continue?',
                parent=self.root
            )
            if not ok:
                return
        page['orientation'] = name
        if index == self.book['page_index']:
            bounds = self.page_dims()
            w, h = window_span(self.mapping_zoom, self.pad_ratio, page=bounds)
            self.origin = [clamp(self.origin[0], 0, max(0, bounds[0] - w)),
                           clamp(self.origin[1], 0, max(0, bounds[1] - h))]
        self._mark_dirty()
        self.repaint()
        self.refresh_pages()
        self._update_canvas_info()

    def set_paper(self, kind):
        self.paper = kind
        self._update_paper_pills()
        self._mark_dirty()
        self._update_canvas_info()
        self.repaint()
        self.refresh_pages()

    def _update_color_buttons(self):
        for col, dot in self.color_dots.items():
            dot.active = (col == self.color)
            dot.render()
        if hasattr(self, 'palette_buttons'):
            for key in ('pen', 'fountain', 'highlighter'):
                self.palette_buttons[key].set(accent=self.color)
        if hasattr(self, 'width_button'):
            self.width_button.update_state(color=self.color)

    def choose_color(self, color):
        self.color = color
        if self.tool == 'eraser':
            self.choose_tool('pen')
        self._update_color_buttons()

    def pick_color(self):
        self._prepare_dialog()
        rgb = colorchooser.askcolor(color=self.color, parent=self.root, title='Choose ink color')
        if rgb and rgb[1]:
            self.color = rgb[1]
            self._update_color_buttons()

    def _update_tool_buttons(self):
        for key, button in self.palette_buttons.items():
            button.set(selected=(self.tool == key))
        for key, button in self.rail_buttons.items():
            if key == 'shape':
                button.set(selected=(self.tool == 'shape'), icon=f'shape_{self.shape}')
            else:
                button.set(selected=(self.tool == key))
        self.canvas.configure(
            cursor='fleur' if self.tool == 'hand' else ('arrow' if self.tool == 'select' else 'crosshair')
        )

    def choose_tool(self, key):
        if self.is_down and self.active_source == 'raw':
            self.block_raw_until_up = True
            self.block_time = time.perf_counter()
        if key == 'shape':
            self.open_shape_popover()
            return
        if key == 'image':
            self.insert_image_dialog()
            return
        self._release_active(commit=True)
        self.tool = key
        self.selected = None
        self.selected_many = []
        self.lasso_points = []
        self._selection_strip_update()
        self._update_tool_buttons()
        self.repaint()
        if key == 'sticky':
            self.set_status('Click anywhere on the page to place a Sticky Note')
        else:
            self.set_status(TOOL_INFO[key][1] + ' active')

    def set_shape(self, shape):
        self.shape = shape
        self.tool = 'shape'
        self._update_tool_buttons()
        self.set_status('Shape tool: ' + shape.title() + ' · drag to draw')

    def set_width(self, value):
        self.width = float(value)
        self.width_button.update_state(width_val=self.width)

    # ------------------------------- mapping/view -------------------------------
    def _update_zoom_labels(self):
        self.mapping_label.configure(text=f'{self.mapping_zoom:.2f}×')
        self.view_label.configure(text=f'{self.view_zoom * 100:.0f}%')

    def change_mapping(self, diff):
        if self.is_down and self.active_source == 'raw':
            self.block_raw_until_up = True
            self.block_time = time.perf_counter()
        self._release_active(commit=True)
        self.mapping_zoom = clamp(round((self.mapping_zoom + diff) * 4) / 4, 1, 4)
        page = self.page_dims()
        w, h = window_span(self.mapping_zoom, self.pad_ratio, page=page)
        target = [clamp(self.origin[0], 0, max(0, page[0] - w)),
                  clamp(self.origin[1], 0, max(0, page[1] - h))]
        self._update_zoom_labels()
        self._mark_dirty()
        self._animate_origin_to(target)
        self.set_status(f'Writing scale {self.mapping_zoom:.2f}× · window {w:.0f} × {h:.0f} page units')

    def _geometry(self):
        c = self.canvas
        cw = max(300, c.winfo_width())
        ch = max(400, c.winfo_height())
        pw_doc, ph_doc = self.page_dims()
        base = min((cw - 140) / pw_doc, (ch - 150) / ph_doc)
        self._canvas_scale = max(.12, base * self.view_zoom)
        pw = pw_doc * self._canvas_scale
        ph = ph_doc * self._canvas_scale
        self.ox = max(78, (cw - pw) / 2)
        self.oy = 82
        self.world_w = max(cw, self.ox + pw + 90)
        self.world_h = max(ch, self.oy + ph + 90)
        c.configure(scrollregion=(0, 0, self.world_w, self.world_h))

    def screen(self, p):
        return self.ox + p[0] * self._canvas_scale, self.oy + p[1] * self._canvas_scale

    def page(self, x, y):
        return ((self.canvas.canvasx(x) - self.ox) / self._canvas_scale,
                (self.canvas.canvasy(y) - self.oy) / self._canvas_scale)

    def change_view(self, factor):
        c = self.canvas
        cw = max(1, c.winfo_width())
        ch = max(1, c.winfo_height())
        px, py = self.page(cw / 2, ch / 2)
        old = self.view_zoom
        self.view_zoom = clamp(self.view_zoom * factor, .5, 3.5)
        if abs(self.view_zoom - old) < .001:
            return
        self._update_zoom_labels()
        self.repaint()
        self.root.update_idletasks()
        nx, ny = self.screen((px, py))
        fx = clamp((nx - cw / 2) / max(1, self.world_w - cw), 0, 1) * max(0, self.world_w - cw) / self.world_w
        fy = clamp((ny - ch / 2) / max(1, self.world_h - ch), 0, 1) * max(0, self.world_h - ch) / self.world_h
        self._smooth_scroll_to(fx, fy)

    def fit_page(self):
        self.view_zoom = 1.0
        self._update_zoom_labels()
        self.repaint()
        self._smooth_scroll_to(0.0, 0.0)

    def canvas_resized(self, _event):
        self.root.after_idle(self.repaint)

    def _navigate_area(self,direction,fine=False):
        """Direct 2D movement: no history pop, no forced reset to left on Up."""
        if self.is_down and self.active_source=='raw':
            self.block_raw_until_up=True
            self.block_time=time.perf_counter()
        self._release_active(commit=True, allow_autopan=False)
        target=move_window(self.origin,direction,self.mapping_zoom,self.pad_ratio,
                           self.page_dims(),fine=fine)
        if any(abs(a-b)>.01 for a,b in zip(target,self.origin)):
            self._mark_dirty()
            self._animate_origin_to(target)
        else:self._draw_nav_map()

    def next_window(self):self._navigate_area('right')
    def previous_window(self):self._navigate_area('left')
    def up_window(self):self._navigate_area('up')
    def down_window(self):self._navigate_area('down')
    def next_line(self):self._navigate_area('newline')

    def _keep_area_in_view(self):
        """Scroll the page when a 2D area jump would land outside the viewport."""
        if not hasattr(self,'canvas'):return
        c=self.canvas
        cw,ch=max(1,c.winfo_width()),max(1,c.winfo_height())
        w,h=window_span(self.mapping_zoom,self.pad_ratio,page=self.page_dims())
        center=self.screen((self.origin[0]+w/2,self.origin[1]+h/2))
        vx,vy=c.canvasx(0),c.canvasy(0)
        margin_x=min(95,cw*.20);margin_y=min(95,ch*.20)
        if center[0] < vx+margin_x or center[0] > vx+cw-margin_x:
            target=max(0,min(max(0,self.world_w-cw),center[0]-cw*.5))
            c.xview_moveto(target/max(1,self.world_w))
        if center[1] < vy+margin_y or center[1] > vy+ch-margin_y:
            target=max(0,min(max(0,self.world_h-ch),center[1]-ch*.5))
            c.yview_moveto(target/max(1,self.world_h))

    def _draw_nav_map(self):
        if not hasattr(self,'nav_map') or not self.nav_map.winfo_exists():return
        c=self.nav_map;c.delete('all')
        pw,ph=self.page_dims()
        mw,mh=118,85
        scale=min((mw-10)/pw,(mh-8)/ph)
        width,height=pw*scale,ph*scale
        x0=(mw-width)/2;y0=(mh-height)/2
        self._map_geometry=(x0,y0,width,height)
        c.create_rectangle(x0,y0,x0+width,y0+height,fill='#fcfcff',outline=BDR)
        w,h=window_span(self.mapping_zoom,self.pad_ratio,page=(pw,ph))
        ox,oy=self.origin
        c.create_rectangle(x0+ox*scale,y0+oy*scale,
                           x0+(ox+w)*scale,y0+(oy+h)*scale,
                           outline=PURPLE,fill='#eee7ff',width=2)
        c.create_text(mw/2,mh-4,text='Click to jump',fill=MUTED,font=('Segoe UI',7),anchor='s')

    def on_nav_map_click(self,event):
        x0,y0,width,height=self._map_geometry
        if not (x0<=event.x<=x0+width and y0<=event.y<=y0+height):return
        if self.is_down and self.active_source=='raw':
            self.block_raw_until_up=True
            self.block_time=time.perf_counter()
        self._release_active(commit=True, allow_autopan=False)
        target=window_from_map((event.x-x0)/width,(event.y-y0)/height,
                               self.mapping_zoom,self.pad_ratio,self.page_dims())
        self._mark_dirty()
        self._animate_origin_to(target)

    def toggle_area_move(self):
        self.set_ink_mode(not self.ink_enabled)
        self.set_status('Move Area: drag anywhere on the paper, use arrows or click the overview.'
                        if not self.ink_enabled else 'Ink Mode: real Windows cursor follows the touchpad tip.')

    def set_ink_mode(self,enable):
        enable=bool(enable)
        if self.ink_enabled==enable:return
        if self.is_down and self.active_source=='raw':
            self.block_raw_until_up=True
            self.block_time=time.perf_counter()
        self._release_active(commit=True, allow_autopan=False)
        self.ink_enabled=enable
        self.mode_button.set('✎  Ink Mode' if enable else '↔  Navigate',
                             selected=enable)
        self.area_mode_button.set('Move Area' if enable else '✓ Move Area',selected=not enable)
        self.canvas.configure(cursor='arrow' if enable else 'fleur')
        self.set_status('Ink Mode: touchpad writes and Windows pointer follows.' if enable else
                        'Navigate: touchpad acts like a normal mouse. Drag the paper to relocate the writing area. Tab to write.')

    def toggle_ink_mode(self):self.set_ink_mode(not self.ink_enabled)

    def _raw_suspended(self):
        if not self.ink_enabled:return True
        # RAWINPUT is registered with INPUTSINK: it receives contacts in the
        # background too. Never draw while another application has focus.
        if not self.cursor_follower.foreground(self.root):return True
        # Do not write into an open native/Tk dialog or while typing in a text field.
        try:
            grab=self.root.grab_current()
            if grab is not None and grab is not self.root:return True
            focus=self.root.focus_get()
            if focus is not None and focus.winfo_class() in ('Entry','TEntry','Text','Spinbox','TSpinbox','TCombobox'):
                return True
        except (tk.TclError,AttributeError):pass
        # Shift temporarily gives the touchpad back to Windows for toolbar clicks.
        if sys.platform=='win32':
            try:
                import ctypes
                return bool(ctypes.windll.user32.GetAsyncKeyState(0x10)&0x8000)
            except (OSError,AttributeError):pass
        return False

    def _start_area_drag(self,e):
        self._release_active(commit=True, allow_autopan=False)
        self.area_drag=(self.page(e.x,e.y),list(self.origin))

    def _update_area_drag(self,e):
        if self.area_drag is None:return
        anchor,old=self.area_drag
        x,y=self.page(e.x,e.y)
        pw,ph=self.page_dims()
        w,h=window_span(self.mapping_zoom,self.pad_ratio,page=(pw,ph))
        self.origin=[clamp(old[0]+x-anchor[0],0,max(0,pw-w)),
                     clamp(old[1]+y-anchor[1],0,max(0,ph-h))]
        self._draw_nav_map()
        self.repaint()

    def _finish_area_drag(self):
        if self.area_drag is not None:
            self.area_drag=None
            self._mark_dirty()
            self._draw_nav_map()
            self.repaint()

    # ----------------------------- drawing display -----------------------------
    def _get_tk_image(self, s, sw, sh):
        if not HAS_PIL or not s.image_b64:
            return None
        key = (id(s), sw, sh)
        if key in self._img_tk_cache:
            return self._img_tk_cache[key]
        pil_base = self._img_pil_cache.get(id(s))
        if pil_base is None:
            try:
                raw = base64.b64decode(s.image_b64)
                pil_base = Image.open(io.BytesIO(raw)).convert('RGBA')
                self._img_pil_cache[id(s)] = pil_base
            except Exception:
                return None
        resized = pil_base.resize((max(1, sw), max(1, sh)), Image.Resampling.LANCZOS)
        tk_img = ImageTk.PhotoImage(resized)
        if len(self._img_tk_cache) > 64:
            self._img_tk_cache.clear()
        self._img_tk_cache[key] = tk_img
        return tk_img

    def _stroke_canvas(self, s, tag='strokes', canvas=None, scale=None, translate=None):
        c = canvas or self.canvas
        scale = self._canvas_scale if scale is None else scale
        if translate is None:
            translate = (self.ox, self.oy)
        if not s.points:
            return []
        kind = s.kind

        if kind == 'image':
            px, py = s.points[0]
            x = translate[0] + px * scale
            y = translate[1] + py * scale
            sw = max(4, int(round((s.box_w or 240) * scale)))
            sh = max(4, int(round((s.box_h or 180) * scale)))
            tk_img = self._get_tk_image(s, sw, sh)
            if tk_img:
                return [c.create_image(x, y, image=tk_img, anchor='nw', tags=(tag,))]
            return [c.create_rectangle(x, y, x + sw, y + sh, fill='#eef2ff', outline='#818cf8', tags=(tag,))]

        if kind == 'sticky':
            px, py = s.points[0]
            x = translate[0] + px * scale
            y = translate[1] + py * scale
            sw = (s.box_w or 240) * scale
            sh = (s.box_h or 200) * scale
            fold = min(22 * scale, sw * 0.16, sh * 0.16)
            ids = []
            # Drop shadow
            ids.append(c.create_polygon(
                x + 3, y + 4, x + sw + 3, y + 4, x + sw + 3, y + sh - fold + 4,
                x + sw - fold + 3, y + sh + 4, x + 3, y + sh + 4,
                fill='#cbd5e1', outline='', tags=(tag,)
            ))
            # Main sticky note body with folded bottom-right corner
            ids.append(c.create_polygon(
                x, y, x + sw, y, x + sw, y + sh - fold,
                x + sw - fold, y + sh, x, y + sh,
                fill=s.color, outline='#d4d4d8', width=1.2, tags=(tag,)
            ))
            # Folded corner flap
            ids.append(c.create_polygon(
                x + sw - fold, y + sh, x + sw - fold, y + sh - fold, x + sw, y + sh - fold,
                fill=self._darken_hex(s.color, 0.88), outline='#cbd5e1', width=1, tags=(tag,)
            ))
            ids.append(c.create_text(
                x + 14 * scale, y + 14 * scale, text=s.text, fill='#1e293b', anchor='nw',
                width=max(20, sw - 28 * scale),
                font=('Segoe UI', max(7, int(s.font_size * scale))), tags=(tag,)
            ))
            return ids

        col = WHITE if s.erase or kind == 'eraser' else s.color
        width = max(1, s.width * scale * (1.12 if kind == 'fountain' else 1))
        if kind == 'highlighter':
            col = self._mix_white(s.color, .48)
            width = max(2, width)
        if kind == 'text':
            px, py = s.points[0]
            x = translate[0] + px * scale
            y = translate[1] + py * scale
            return [c.create_text(x, y, text=s.text, fill=col, anchor='sw',
                                  font=('Segoe UI', max(7, int(s.font_size * scale))), tags=(tag,))]
        pts = shape_path(s.shape, s.points) if kind == 'shape' else s.points
        coords = []
        for x, y in pts:
            coords.extend((translate[0] + x * scale, translate[1] + y * scale))
        if len(coords) < 4:
            x, y = coords[:2]
            return [c.create_oval(x - width / 2, y - width / 2, x + width / 2, y + width / 2,
                                  fill=col, outline='', tags=(tag,))]
        ids = [c.create_line(*coords, fill=col, width=width, capstyle=tk.ROUND, joinstyle=tk.ROUND, tags=(tag,))]
        if kind == 'shape' and s.shape == 'arrow':
            wing = arrow_wings(pts[0], pts[-1], max(12, s.width * 4))
            for wx, wy in wing:
                last = pts[-1]
                ids.append(c.create_line(
                    translate[0] + last[0] * scale, translate[1] + last[1] * scale,
                    translate[0] + wx * scale, translate[1] + wy * scale,
                    fill=col, width=width, capstyle=tk.ROUND, tags=(tag,)
                ))
        return ids

    @staticmethod
    def _mix_white(hexcolor, blend):
        try:
            rgb = [int(hexcolor[i:i + 2], 16) for i in (1, 3, 5)]
            return '#' + ''.join(f'{int(round(v * (1 - blend) + 255 * blend)):02x}' for v in rgb)
        except Exception:
            return hexcolor

    @staticmethod
    def _darken_hex(hexcolor, factor=0.88):
        try:
            rgb = [int(hexcolor[i:i + 2], 16) for i in (1, 3, 5)]
            return '#' + ''.join(f'{max(0, min(255, int(round(v * factor)))):02x}' for v in rgb)
        except Exception:
            return hexcolor

    def repaint(self):
        if not hasattr(self, 'canvas') or not self.canvas.winfo_exists():
            return
        c = self.canvas
        self._geometry()
        c.delete('all')

        left = int(c.canvasx(0) // 26) * 26
        top = int(c.canvasy(0) // 26) * 26
        right = int(c.canvasx(c.winfo_width()) + 30)
        bottom = int(c.canvasy(c.winfo_height()) + 30)
        for x in range(left, right, 26):
            for y in range(top, bottom, 26):
                c.create_oval(x, y, x + 1.5, y + 1.5, fill=DOT, outline='')

        pw_doc, ph_doc = self.page_dims()
        x0, y0 = self.screen((0, 0))
        x1, y1 = self.screen((pw_doc, ph_doc))

        c.create_rectangle(x0 + 3, y0 + 5, x1 + 3, y1 + 5, fill='#e6eaf5', outline='')
        c.create_rectangle(x0 + 7, y0 + 10, x1 + 7, y1 + 10, fill='#dce2f0', outline='')
        c.create_rectangle(x0, y0, x1, y1, fill=WHITE, outline='#dce3f2')

        if self.paper == 'ruled':
            for y in range(138, ph_doc, 67):
                sy = self.screen((0, y))[1]
                c.create_line(x0 + 25 * self._canvas_scale, sy, x1 - 25 * self._canvas_scale, sy, fill=LINE)
            mx = self.screen((74, 0))[0]
            c.create_line(mx, y0 + 25 * self._canvas_scale, mx, y1 - 25 * self._canvas_scale, fill='#f1b6cb')
        elif self.paper == 'grid':
            for x in range(0, pw_doc, 48):
                sx = self.screen((x, 0))[0]
                c.create_line(sx, y0, sx, y1, fill='#edf1f9')
            for y in range(0, ph_doc, 48):
                sy = self.screen((0, y))[1]
                c.create_line(x0, sy, x1, sy, fill='#edf1f9')

        page_title = self.book['pages'][self.book['page_index']].get('name', 'Untitled').upper()
        c.create_text(x0 + 37 * self._canvas_scale, y0 + 34 * self._canvas_scale,
                      text=page_title[:36], anchor='nw', fill='#a3b0c4',
                      font=('Segoe UI', max(7, int(10 * self._canvas_scale)), 'bold'))

        # Layer order: images & sticky notes first, then ink strokes on top so you can annotate over them!
        for s in self.drawing.strokes:
            if s is self.drawing.active:
                continue
            if s.kind in ('image', 'sticky'):
                self._stroke_canvas(s)
        for s in self.drawing.strokes:
            if s is self.drawing.active:
                continue
            if s.kind not in ('image', 'sticky'):
                self._stroke_canvas(s)
        if self.drawing.active:
            self._stroke_canvas(self.drawing.active, tag='liveink')
        self._draw_window_overlay()
        if self.selected_many:
            self._draw_selected_many()
        elif self.selected and self.selected in self.drawing.strokes:
            self._draw_selection()
        if self.lasso_points:
            self._draw_lasso()
        self._draw_nav_map()

    def _draw_window_overlay(self):
        c = self.canvas
        if self.show_writing_guides:
            w, h = window_span(self.mapping_zoom, self.pad_ratio, page=self.page_dims())
            x, y = self.screen(self.origin)
            xr, yr = self.screen((self.origin[0] + w, self.origin[1] + h))
            stroke = '#8e80e1' if self.is_down else '#c1b8ee'
            c.create_rectangle(x, y, xr, yr, outline=stroke,
                               width=1.6 if self.is_down else 1.2, dash=(6, 5), tags=('overlay',))
            rounded(c, x, y - 22, x + 136, y - 4, 6,
                    fill='#f7f5ff', outline='#e2dcff', width=1, tags=('overlay',))
            c.create_text(x + 8, y - 13, text=f'WRITING AREA · {self.mapping_zoom:.2f}×',
                          anchor='w', fill='#7665c1', font=('Segoe UI', 8, 'bold'), tags=('overlay',))
            if self.auto_pan:
                # Faint four-edge guides match the four-way AutoPan mechanism.
                inset_x=(xr-x)*.085
                inset_y=(yr-y)*.085
                edge='#dfc29a'
                c.create_line(x+inset_x,y+3,x+inset_x,yr-3,fill=edge,dash=(2,5),tags=('overlay',))
                c.create_line(xr-inset_x,y+3,xr-inset_x,yr-3,fill=edge,dash=(2,5),tags=('overlay',))
                c.create_line(x+3,y+inset_y,xr-3,y+inset_y,fill=edge,dash=(2,5),tags=('overlay',))
                c.create_line(x+3,yr-inset_y,xr-3,yr-inset_y,fill=edge,dash=(2,5),tags=('overlay',))
                if xr-x>65 and yr-y>55:
                    font=('Segoe UI',8,'bold')
                    c.create_text((x+xr)/2,y+5,text='↑',fill='#ae874f',font=font,tags=('overlay',))
                    c.create_text((x+xr)/2,yr-5,text='↓',fill='#ae874f',font=font,tags=('overlay',))
                    c.create_text(x+6,(y+yr)/2,text='←',fill='#ae874f',font=font,tags=('overlay',))
                    c.create_text(xr-6,(y+yr)/2,text='→',fill='#ae874f',font=font,tags=('overlay',))

    def _object_bounds(self, stroke):
        if stroke.kind in ('sticky', 'image'):
            x, y = stroke.points[0]
            return [(x, y), (x + (stroke.box_w or 240), y + (stroke.box_h or 200))]
        if stroke.kind == 'text':
            x, y = stroke.points[0]
            return [(x, y - stroke.font_size), (x + len(stroke.text) * stroke.font_size * .58, y)]
        return shape_path(stroke.shape, stroke.points) if stroke.kind == 'shape' else stroke.points

    def _draw_selection(self):
        if not self.selected or not self.selected.points:
            return
        pts = self._object_bounds(self.selected)
        xx = [p[0] for p in pts]
        yy = [p[1] for p in pts]
        pad = 4 if self.selected.kind in ('sticky', 'image') else 10
        a, b = self.screen((min(xx) - pad, min(yy) - pad))
        d, e = self.screen((max(xx) + pad, max(yy) + pad))
        self.canvas.create_rectangle(a, b, d, e, outline=PURPLE, width=1.8, tags=('selection',))
        for hx, hy in [(a, b), (d, b), (a, e), (d, e)]:
            self.canvas.create_oval(hx - 4, hy - 4, hx + 4, hy + 4, fill=WHITE, outline=PURPLE, width=1.8, tags=('selection',))

    def _draw_selected_many(self):
        for stroke in self.selected_many:
            if stroke not in self.drawing.strokes or not stroke.points:
                continue
            pts = self._object_bounds(stroke)
            a, b = self.screen((min(p[0] for p in pts) - 5, min(p[1] for p in pts) - 5))
            c, d = self.screen((max(p[0] for p in pts) + 5, max(p[1] for p in pts) + 5))
            self.canvas.create_rectangle(a, b, c, d, outline=PURPLE, dash=(3, 3), width=1.8, tags=('selection',))

    def _draw_lasso(self):
        if not self.lasso_points:
            return
        coords = []
        for point in self.lasso_points:
            coords.extend(self.screen(point))
        if len(coords) >= 4:
            self.canvas.create_line(*coords, fill=PURPLE, width=2, dash=(5, 3),
                                    capstyle=tk.ROUND, joinstyle=tk.ROUND, tags=('lassoink',))

    def _selection_strip_update(self):
        if not hasattr(self, 'selection_strip'):
            return
        count = len(self.selected_many) if self.selected_many else (1 if self.selected else 0)
        if count:
            self.selection_count.configure(text=f'{count} object' + ('s' if count != 1 else '') + ' selected')
            self.selection_strip.place(relx=.5, y=68, anchor='n')
            self.selection_strip.lift()
        else:
            self.selection_strip.place_forget()

    def clear_selection(self):
        self.selected = None
        self.selected_many = []
        self.lasso_points = []
        self._selection_strip_update()
        self.repaint()

    def _refresh_live(self):
        if not hasattr(self, 'canvas'):
            return
        self.canvas.delete('liveink')
        if self.drawing.active:
            self._stroke_canvas(self.drawing.active, tag='liveink')
        self.canvas.delete('cursor')
        if self.lasso_points:
            self._draw_lasso()
        if self.current_cursor:
            cx, cy = self.screen(self.current_cursor)
            if self.tool == 'eraser':
                r = (self.width * 3.0) * self._canvas_scale
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=PURPLE, width=1.2,
                                        dash=(3, 3), tags=('cursor',))
            # Other tools use the native Windows pointer, not a synthetic ink dot.

    # ----------------------------- interaction -----------------------------
    def _stroke_at(self, x, y):
        tolerance = max(8, 12 / max(.25, self._canvas_scale))
        best = None
        distance = tolerance
        # First check ink/shapes/text on top
        for s in reversed(self.drawing.strokes):
            if s.kind in ('sticky', 'image'):
                continue
            pts = shape_path(s.shape, s.points, 32) if s.kind == 'shape' else s.points
            if s.kind == 'text':
                xx, yy = pts[0]
                if xx - 10 <= x <= xx + len(s.text) * s.font_size * .62 + 10 and yy - s.font_size - 10 <= y <= yy + 15:
                    return s
            if len(pts) == 1:
                d = math.dist((x, y), pts[0])
                if d < distance:
                    best = s
                    distance = d
            for a, b in zip(pts, pts[1:]):
                vx = b[0] - a[0]
                vy = b[1] - a[1]
                l2 = vx * vx + vy * vy
                t = clamp(((x - a[0]) * vx + (y - a[1]) * vy) / l2, 0, 1) if l2 else 0
                d = math.dist((x, y), (a[0] + t * vx, a[1] + t * vy))
                if d < distance:
                    best = s
                    distance = d
        if best:
            return best
        # Then check sticky notes & images underneath
        for s in reversed(self.drawing.strokes):
            if s.kind in ('sticky', 'image') and s.points:
                xx, yy = s.points[0]
                w = s.box_w or 240
                h = s.box_h or 200
                if xx <= x <= xx + w and yy <= y <= yy + h:
                    return s
        return None

    def mouse_double_click(self, e):
        x, y = self.page(e.x, e.y)
        hit = self._stroke_at(x, y)
        if hit and hit.kind == 'sticky':
            self.open_sticky_dialog(edit_stroke=hit)

    def _input_down(self, x, y, source='raw', u=None, v=None):
        self.active_source = source
        self.is_down = True
        self.drag_start = (x, y)
        self.current_cursor = (x, y)
        self.start_u = u
        self.last_u = u
        self.path_u = [u] if u is not None else []
        self.start_v = v
        self.last_v = v
        self.path_v = [v] if v is not None else []
        if self.tool == 'lasso':
            self.selected = None
            self.selected_many = []
            self.lasso_points = [(x, y)]
            self._selection_strip_update()
            self._refresh_live()
            return
        if self.tool == 'eraser':
            self.selected = None
            self.selected_many = []
            self._selection_strip_update()
            self.drawing.start_eraser()
            self.eraser_last = (x, y)
            if self.drawing.erase_to((x, y), (x, y), self.width * 3.0):
                self._mark_dirty()
                self.repaint()
            else:
                self._refresh_live()
            return
        if self.tool == 'select':
            self.selected_many = []
            self.selected = self._stroke_at(x, y)
            self._selection_strip_update()
            self.drag_old = list(self.selected.points) if self.selected else None
            self.repaint()
            return
        if self.tool == 'hand':
            self._pan_origin = list(self.origin)
            return
        if self.tool == 'text':
            self.pending_text = (x, y)
            self._refresh_live()
            return
        if self.tool == 'sticky':
            self.pending_sticky = (x, y)
            self._refresh_live()
            return
        self.fx = OneEuro()
        self.fy = OneEuro()
        multiplier = {'pen': 1, 'fountain': 1.15, 'highlighter': 5.0, 'eraser': 6.0, 'shape': 1}.get(self.tool, 1)
        self.drawing.begin(x, y, color=self.color, width=self.width * multiplier,
                           erase=self.tool == 'eraser', kind=self.tool,
                           shape=self.shape if self.tool == 'shape' else '')
        self._refresh_live()

    def _input_move(self, x, y, t, u=None, v=None):
        if not self.is_down:
            return
        if u is not None:
            self.last_u=u
            self.path_u.append(u)
            if len(self.path_u)>100:self.path_u.pop(0)
        if v is not None:
            self.last_v=v
            self.path_v.append(v)
            if len(self.path_v)>100:self.path_v.pop(0)
        if self.tool == 'lasso':
            self.current_cursor = (x, y)
            if not self.lasso_points or math.dist(self.lasso_points[-1], (x, y)) > 1.6:
                self.lasso_points.append((x, y))
                self._refresh_live()
            return
        if self.tool == 'eraser':
            a = self.eraser_last or (x, y)
            b = (x, y)
            self.eraser_last = b
            self.current_cursor = b
            if self.drawing.erase_to(a, b, self.width * 3.0):
                self._mark_dirty()
                if t - self._last_erase_paint > .025:
                    self._last_erase_paint = t
                    self.repaint()
            else:
                self._refresh_live()
            return
        if self.tool == 'select' and self.selected and self.drag_old:
            dx = x - self.drag_start[0]
            dy = y - self.drag_start[1]
            self.selected.points = [(px + dx, py + dy) for px, py in self.drag_old]
            self.repaint()
            return
        if self.tool == 'hand':
            if self.active_source == 'raw':
                dx = x - self.drag_start[0]
                dy = y - self.drag_start[1]
                page = self.page_dims()
                w, h = window_span(self.mapping_zoom, self.pad_ratio, page=page)
                self.origin = [clamp(self._pan_origin[0] - dx, 0, max(0, page[0] - w)),
                               clamp(self._pan_origin[1] - dy, 0, max(0, page[1] - h))]
                self.repaint()
            return
        if self.tool in ('text', 'sticky'):
            return
        if self.smooth and self.tool != 'shape':
            x = self.fx.update(x, t)
            y = self.fy.update(y, t)
        if self.drawing.move(x, y):
            self.current_cursor = (x, y)
            self._mark_dirty()
            self._refresh_live()

    def _release_active(self, commit=True, allow_autopan=True):
        if not self.is_down:
            return
        was_tool = self.tool
        source = self.active_source
        if self.tool == 'lasso':
            if len(self.lasso_points) >= 3:
                self.selected_many = strokes_in_lasso(self.drawing.strokes, self.lasso_points)
            else:
                self.selected_many = []
            self.lasso_points = []
            self.selected = None
            self._selection_strip_update()
            self.set_status(f'Lasso: {len(self.selected_many)} object(s) selected · Delete to remove')
        if self.tool == 'eraser':
            self.drawing.finish_eraser()
            self.eraser_last = None
        if self.tool == 'select' and self.selected and self.drag_old:
            newer = list(self.selected.points)
            self.selected.points = list(self.drag_old)
            dx = newer[0][0] - self.drag_old[0][0]
            dy = newer[0][1] - self.drag_old[0][1]
            self.drawing.move_stroke(self.selected, dx, dy)
            if abs(dx) + abs(dy) > .1:
                self._mark_dirty()
        if self.tool == 'hand' and self.active_source == 'raw':
            self._mark_dirty()
        if self.drawing.active:
            self.drawing.end()
            self._mark_dirty()
        if was_tool == 'text' and self.pending_text and commit:
            location = self.pending_text
            self.root.after_idle(lambda p=location: self.prompt_text(p))
        if was_tool == 'sticky' and self.pending_sticky and commit:
            location = self.pending_sticky
            self.root.after_idle(lambda p=location: self.open_sticky_dialog(location=p))
        self.pending_text = None
        self.pending_sticky = None
        auto_direction = (edge_turn(self.start_u,self.start_v,self.last_u,self.last_v,len(self.path_u))
                          if (allow_autopan and was_tool in ('pen','fountain','highlighter') and source=='raw' and self.auto_pan)
                          else None)
        self.is_down = False
        self.active_source = None
        self.drag_start = None
        self.drag_old = None
        self.last_u = None
        self.start_u = None
        self.path_u = []
        self.last_v = None
        self.start_v = None
        self.path_v = []
        self.current_cursor = None
        if auto_direction:
            self.history.append(list(self.origin))
            target=move_window(self.origin,auto_direction,self.mapping_zoom,self.pad_ratio,self.page_dims())
            if target!=self.origin:
                self._mark_dirty()
                self._animate_origin_to(target)
        if was_tool in ('pen', 'fountain', 'highlighter', 'eraser', 'shape', 'select', 'lasso', 'hand'):
            self.refresh_pages()
        self.repaint()

    def prompt_text(self, location):
        self._prepare_dialog()
        value = simpledialog.askstring('Insert text', 'Type your text:', parent=self.root)
        if value:
            self.drawing.add_text(*location, value, self.color, font_size=34)
            self._mark_dirty()
            self.repaint()
            self.refresh_pages()

    def start_raw(self):
        if not self.raw.running:
            self.raw.start()
        self.raw_mode = True
        self.set_status('RAW input requested. Touch your touchpad to begin writing.')
        self.raw_state.configure(text='● Listening for RAW', fg='#0284c7')

    def _prepare_dialog(self):
        """End a stroke safely before opening a dialog; never block Windows mouse."""
        if self.is_down and self.active_source=='raw':
            self.block_raw_until_up=True
            self.block_time=time.perf_counter()
        if self.is_down:self._release_active(commit=False,allow_autopan=False)

    def _focus_check(self):
        # No global mouse lock to release; cursor follower checks foreground itself.
        return None

    def poll(self):
        if self._closing:return
        if self.raw.running:
            now=time.perf_counter()
            suspended=self._raw_suspended()
            # An open modal dialog becomes a different foreground HWND; no pointer
            # changes are allowed there. Foreground is rechecked by CursorFollower.
            latest_point=None
            for _ in range(240):
                try:ev=self.raw.events.get_nowait()
                except Exception:break
                if ev[0]=='up':
                    self.block_raw_until_up=False
                    if self.active_source=='raw':self._release_active()
                elif ev[0]=='point':
                    _,u,v,t=ev
                    self.last_seen=now
                    if suspended:
                        if self.active_source=='raw':
                            self._release_active()
                            self.block_raw_until_up=True
                        continue
                    if self.block_raw_until_up:continue
                    x,y=point_to_page(u,v,self.origin,self.mapping_zoom,
                                        self.pad_ratio,page=self.page_dims())
                    if not self.is_down:self._input_down(x,y,'raw',u,v)
                    elif self.active_source=='raw':self._input_move(x,y,t,u,v)
                    # Only warp once per Tk frame, not once per HID sample.
                    latest_point=self.current_cursor if self.current_cursor else (x,y)
            if self.is_down and self.active_source=='raw' and now-self.last_seen>.20:
                self._release_active()
            if self.block_raw_until_up and now-self.block_time>1.0 and now-self.last_seen>.2:
                self.block_raw_until_up=False
            if (latest_point is not None and self.ink_enabled and not suspended
                    and not self.block_raw_until_up):
                self.cursor_follower.follow(self.root,self.canvas,self.screen(latest_point))
            status=self.raw.status
            if status!=self._last_device_status:
                self._last_device_status=status
                if 'RAW ABSOLUTE' in status:
                    self.raw_state.configure(text='● RAW ABSOLUTE',fg='#16a34a')
                elif 'error' in status.lower() or 'parser' in status.lower():
                    self.raw_state.configure(text='● RAW unavailable',fg=RED)
                    self.set_status(status)
                else:self.raw_state.configure(text='● Listening for RAW',fg='#0284c7')
        self.root.after(12,self.poll)

    def mouse_down(self, e):
        # In Navigate mode / Shift+drag, reposition the writing window directly.
        if not self.ink_enabled or (e.state & 0x0001):
            self._start_area_drag(e)
            return
        if self.tool == 'hand':
            self.canvas.scan_mark(e.x, e.y)
            self.hand_pan = True
            return
        if self.raw_mode and not self.mouse_test and self.tool not in ('select', 'lasso', 'sticky', 'text'):
            return
        x, y = self.page(e.x, e.y)
        if 0 <= x <= self.page_dims()[0] and 0 <= y <= self.page_dims()[1]:
            self._input_down(x, y, 'mouse')

    def mouse_move(self, e):
        if self.area_drag is not None:
            self._update_area_drag(e)
            return
        if self.hand_pan:
            self.canvas.scan_dragto(e.x, e.y, gain=1)
            return
        if self.active_source == 'mouse' and self.is_down:
            x, y = self.page(e.x, e.y)
            self._input_move(x, y, time.perf_counter())

    def mouse_up(self, _e):
        if self.area_drag is not None:
            self._finish_area_drag()
            return
        if self.hand_pan:
            self.hand_pan = False
            return
        if self.active_source == 'mouse':
            self._release_active()

    def mouse_wheel(self, e):
        if e.state & 0x4:
            self.change_view(1.13 if e.delta > 0 else 1 / 1.13)
        elif e.state & 0x1:
            self.canvas.xview_scroll(-3 if e.delta > 0 else 3, 'units')
        else:
            self.canvas.yview_scroll(-3 if e.delta > 0 else 3, 'units')

    def pan_start(self, e):
        self.canvas.scan_mark(e.x, e.y)

    def pan_drag(self, e):
        self.canvas.scan_dragto(e.x, e.y, gain=1)

    def undo(self):
        self._release_active()
        self.selected = None
        self.selected_many = []
        self._selection_strip_update()
        self.drawing.undo()
        self._mark_dirty()
        self.repaint()
        self.refresh_pages()

    def redo(self):
        self._release_active()
        self.selected = None
        self.selected_many = []
        self._selection_strip_update()
        self.drawing.redo_one()
        self._mark_dirty()
        self.repaint()
        self.refresh_pages()

    def delete_selected(self):
        selected = self.selected_many or ([self.selected] if self.selected else [])
        if selected:
            count = self.drawing.delete_strokes(selected)
            self.selected = None
            self.selected_many = []
            self.lasso_points = []
            self._selection_strip_update()
            if count:
                self._mark_dirty()
                self.repaint()
                self.refresh_pages()
                self.set_status(f'Deleted {count} object(s) · Ctrl+Z to undo')

    def set_status(self, text):
        if hasattr(self, 'status_var'):
            self.status_var.set(str(text)[:155])

    @staticmethod
    def _is_editing_text(event):
        """Do not hijack text entry while naming/searching/editing a note."""
        try:
            return event.widget.winfo_class() in ('Entry', 'TEntry', 'Text', 'Spinbox',
                                                  'TSpinbox', 'TCombobox')
        except (AttributeError, tk.TclError):
            return False

    def _only_while_writing(self, action):
        return lambda event: None if self._is_editing_text(event) else action()

    def _search_first_page(self):
        query = self.page_query.get().strip().casefold()
        if not query:
            return
        for idx, page in enumerate(self.book['pages']):
            if query in page.get('name', '').casefold() or any(
                query in obj.get('text', '').casefold()
                for obj in page.get('strokes', []) if isinstance(obj, dict)
            ):
                self.select_page(idx)
                self.canvas.focus_set()
                return

    def _tab_ink_mode(self,event):
        if self._is_editing_text(event):return None
        self.toggle_ink_mode()
        return 'break'

    def _bind_keys(self):
        self.root.bind_all('<Control-s>', lambda _e: self.save())
        self.root.bind_all('<Control-o>', lambda _e: self.open_notebook())
        self.root.bind_all('<Control-n>', lambda _e: self.new_page())
        self.root.bind_all('<Control-v>', lambda _e: self.paste_from_clipboard())
        self.root.bind_all('<Control-Shift-S>', lambda _e: self.save_as())
        self.root.bind_all('<Control-z>', lambda _e: self.undo())
        self.root.bind_all('<Control-y>', lambda _e: self.redo())
        self.root.bind_all('<Tab>', self._tab_ink_mode)
        self.root.bind_all('<F8>', lambda _e: self.set_ink_mode(False))
        self.root.bind_all('<F11>', lambda _e: self.toggle_focus_mode())
        self.root.bind_all('<Control-f>', lambda _e: self._find_page())
        self.root.bind_all('<Control-Shift-N>', lambda _e: self.new_page_gallery())
        self.root.bind_all('<Escape>', lambda _e: (self.clear_selection(), self.set_ink_mode(False)))
        self.root.bind_all('<Left>', self._only_while_writing(lambda: self.previous_window()))
        self.root.bind_all('<Up>', self._only_while_writing(lambda: self.up_window()))
        self.root.bind_all('<Down>', self._only_while_writing(lambda: self.down_window()))
        self.root.bind_all('<Right>', self._only_while_writing(lambda: self.next_window()))
        self.root.bind_all('<Return>', self._only_while_writing(lambda: self.next_line()))
        self.root.bind_all('<Delete>', self._only_while_writing(lambda: self.delete_selected()))
        for key, tool in [('1', 'pen'), ('2', 'fountain'), ('3', 'highlighter'), ('4', 'eraser')]:
            self.root.bind_all(key, lambda e, t=tool: None if self._is_editing_text(e) else self.choose_tool(t))
        self.root.bind_all('5', self._only_while_writing(lambda: self.choose_tool('select')))
        self.root.bind_all('6', self._only_while_writing(lambda: self.set_shape(self.shape)))
        self.root.bind_all('7', self._only_while_writing(lambda: self.choose_tool('text')))
        self.root.bind_all('8', self._only_while_writing(lambda: self.choose_tool('hand')))
        self.root.bind_all('9', self._only_while_writing(lambda: self.choose_tool('lasso')))
        self.root.bind_all('s', self._only_while_writing(lambda: self.choose_tool('sticky')))
        self.root.bind_all('i', self._only_while_writing(lambda: self.insert_image_dialog()))
        self.root.bind_all('<Control-plus>', lambda _e: self.change_view(1.2))
        self.root.bind_all('<Home>', self._only_while_writing(lambda: self._navigate_area('home')))
        self.root.bind_all('<Control-minus>', lambda _e: self.change_view(1 / 1.2))
        self.root.bind('<FocusOut>', lambda _e: self.root.after(90, self._focus_check))

    def close(self):
        self._prepare_dialog()
        self._release_active()
        if self.dirty and not self.save():
            return
        self._closing = True
        self.raw.stop()
        try:
            os.makedirs(DOCS, exist_ok=True)
            with open(SETTINGS, 'w', encoding='utf-8') as f:
                json.dump(dict(mapping_zoom=self.mapping_zoom, pad_ratio=self.pad_ratio,
                               canvas_zoom=self.view_zoom, auto_pan=self.auto_pan,
                               show_writing_guides=self.show_writing_guides,
                               last_book=self.book_path), f, indent=2)
        except OSError:
            pass
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    Studio(root)
    root.mainloop()
