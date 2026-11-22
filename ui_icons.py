"""Vector icon renderer and high-DPI app icon generator for TouchInk Studio."""
import math
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def create_app_icon(size=64):
    """Generate a friendly squircle TouchInk app icon using Pillow (supersampled)."""
    if not HAS_PIL:
        return None
    s = size * 4
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)

    pad = int(s * 0.08)
    r = int(s * 0.26)
    dr.rounded_rectangle([pad, pad + int(s * 0.03), s - pad, s - pad + int(s * 0.03)],
                         radius=r, fill=(79, 58, 179, 70))
    dr.rounded_rectangle([pad, pad, s - pad, s - pad],
                         radius=r, fill=(108, 78, 230, 255))
    dr.rounded_rectangle([pad + 6, pad + 6, s - pad - 6, int(s * 0.52)],
                         radius=max(8, r - 6), fill=(128, 100, 245, 110))

    ribbon = []
    for i in range(40):
        t = i / 39.0
        rx = s * (0.24 + 0.52 * t)
        ry = s * (0.74 - 0.08 * math.sin(t * math.pi * 1.6))
        ribbon.append((rx, ry))
    dr.line(ribbon, fill=(255, 213, 46, 255), width=max(4, int(s * 0.055)), joint='curve')

    nib = [
        (s * 0.68, s * 0.22),
        (s * 0.78, s * 0.32),
        (s * 0.48, s * 0.62),
        (s * 0.33, s * 0.67),
        (s * 0.38, s * 0.52),
    ]
    dr.polygon(nib, fill=(255, 255, 255, 255))
    dr.line([(s * 0.35, s * 0.65), (s * 0.50, s * 0.50)],
            fill=(108, 78, 230, 255), width=max(2, int(s * 0.022)))
    cx, cy, br = s * 0.51, s * 0.49, s * 0.032
    dr.ellipse([cx - br, cy - br, cx + br, cy + br], fill=(108, 78, 230, 255))

    img = img.resize((size, size), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(img)


def draw_icon(c: tk.Canvas, name: str, cx: float, cy: float, size: float = 20,
              color: str = '#23293a', accent: str = '#6c4ee6', active: bool = False):
    """Draw crisp, friendly vector icons centered at (cx, cy)."""
    s = size * 0.5
    ink = accent if active else color

    if name == 'logo':
        r = s * 0.48
        pts = [
            cx - s + r, cy - s, cx + s - r, cy - s, cx + s, cy - s, cx + s, cy - s + r,
            cx + s, cy + s - r, cx + s, cy + s, cx + s - r, cy + s, cx - s + r, cy + s,
            cx - s, cy + s, cx - s, cy + s - r, cx - s, cy - s + r, cx - s, cy - s
        ]
        c.create_polygon(pts, smooth=True, splinesteps=16, fill='#6c4ee6', outline='')
        c.create_arc(cx - s * 0.55, cy + s * 0.15, cx + s * 0.55, cy + s * 0.68,
                     start=195, extent=150, style='arc', outline='#ffd43b', width=2.4)
        c.create_polygon(
            cx + s * 0.36, cy - s * 0.52,
            cx + s * 0.56, cy - s * 0.32,
            cx - s * 0.10, cy + s * 0.34,
            cx - s * 0.42, cy + s * 0.44,
            cx - s * 0.32, cy + s * 0.12,
            fill='#ffffff', outline=''
        )
        c.create_line(cx - s * 0.38, cy + s * 0.40, cx - s * 0.06, cy + s * 0.08,
                      fill='#6c4ee6', width=1.6, capstyle=tk.ROUND)

    elif name == 'pen':
        c.create_polygon(
            cx + s * 0.35, cy - s * 0.78,
            cx + s * 0.74, cy - s * 0.39,
            cx - s * 0.14, cy + s * 0.49,
            cx - s * 0.53, cy + s * 0.10,
            fill='#f4f6fc' if not active else '#ebe5ff',
            outline=ink, width=1.7, joinstyle=tk.ROUND
        )
        c.create_line(cx + s * 0.18, cy - s * 0.61, cx + s * 0.57, cy - s * 0.22,
                      fill=accent, width=3.0, capstyle=tk.ROUND)
        c.create_polygon(
            cx - s * 0.53, cy + s * 0.10,
            cx - s * 0.14, cy + s * 0.49,
            cx - s * 0.72, cy + s * 0.70,
            fill=accent, outline=ink, width=1.4, joinstyle=tk.ROUND
        )

    elif name == 'fountain':
        c.create_polygon(
            cx + s * 0.32, cy - s * 0.78,
            cx + s * 0.74, cy - s * 0.36,
            cx + s * 0.44, cy - s * 0.06,
            cx + s * 0.02, cy - s * 0.48,
            fill=ink, outline=ink, width=1.2
        )
        c.create_polygon(
            cx + s * 0.02, cy - s * 0.48,
            cx + s * 0.44, cy - s * 0.06,
            cx + s * 0.12, cy + s * 0.44,
            cx - s * 0.72, cy + s * 0.70,
            cx - s * 0.46, cy - s * 0.14,
            fill='#ffffff', outline=ink, width=1.7, joinstyle=tk.ROUND
        )
        c.create_line(cx - s * 0.68, cy + s * 0.66, cx - s * 0.06, cy + s * 0.04,
                      fill=accent, width=1.8, capstyle=tk.ROUND)
        c.create_oval(cx - s * 0.13, cy - s * 0.05, cx + s * 0.03, cy + s * 0.11,
                      fill=accent, outline='')

    elif name == 'highlighter':
        c.create_polygon(
            cx + s * 0.26, cy - s * 0.78,
            cx + s * 0.74, cy - s * 0.30,
            cx + s * 0.02, cy + s * 0.42,
            cx - s * 0.46, cy - s * 0.06,
            fill='#f8f9fd', outline=ink, width=1.7, joinstyle=tk.ROUND
        )
        c.create_polygon(
            cx - s * 0.46, cy - s * 0.06,
            cx + s * 0.02, cy + s * 0.42,
            cx - s * 0.34, cy + s * 0.68,
            cx - s * 0.68, cy + s * 0.34,
            fill=accent, outline=ink, width=1.4, joinstyle=tk.ROUND
        )
        c.create_line(cx - s * 0.74, cy + s * 0.76, cx + s * 0.24, cy + s * 0.76,
                      fill=accent, width=3.2, capstyle=tk.ROUND)

    elif name == 'eraser':
        c.create_polygon(
            cx + s * 0.16, cy - s * 0.72,
            cx + s * 0.74, cy - s * 0.14,
            cx + s * 0.24, cy + s * 0.36,
            cx - s * 0.34, cy - s * 0.22,
            fill='#ff8fa3' if not active else '#ff6b8b',
            outline=ink, width=1.6, joinstyle=tk.ROUND
        )
        c.create_polygon(
            cx - s * 0.34, cy - s * 0.22,
            cx + s * 0.24, cy + s * 0.36,
            cx - s * 0.14, cy + s * 0.74,
            cx - s * 0.72, cy + s * 0.16,
            fill='#ffffff', outline=ink, width=1.6, joinstyle=tk.ROUND
        )
        c.create_line(cx - s * 0.14, cy + s * 0.74, cx + s * 0.68, cy + s * 0.74,
                      fill=ink, width=1.6, capstyle=tk.ROUND)

    elif name == 'select':
        c.create_rectangle(cx + s * 0.05, cy + s * 0.05, cx + s * 0.76, cy + s * 0.76,
                           outline=accent if active else '#9aa3b8', width=1.4, dash=(2, 2))
        c.create_polygon(
            cx - s * 0.62, cy - s * 0.68,
            cx - s * 0.62, cy + s * 0.42,
            cx - s * 0.28, cy + s * 0.12,
            cx - s * 0.06, cy + s * 0.56,
            cx + s * 0.14, cy + s * 0.46,
            cx - s * 0.08, cy + s * 0.02,
            cx + s * 0.34, cy + s * 0.02,
            fill='#ffffff' if not active else accent,
            outline=ink, width=1.6, joinstyle=tk.ROUND
        )

    elif name == 'lasso':
        pts = [
            cx - s * 0.58, cy - s * 0.10,
            cx - s * 0.35, cy - s * 0.65,
            cx + s * 0.35, cy - s * 0.60,
            cx + s * 0.68, cy - s * 0.05,
            cx + s * 0.42, cy + s * 0.52,
            cx - s * 0.25, cy + s * 0.45,
        ]
        c.create_polygon(pts, smooth=True, fill='#f3efff' if active else '',
                         outline=ink, width=1.8, dash=(3, 2))
        c.create_oval(cx - s * 0.42, cy + s * 0.26, cx - s * 0.06, cy + s * 0.62,
                      fill=accent, outline='#ffffff', width=1.3)
        c.create_line(cx - s * 0.24, cy + s * 0.58, cx - s * 0.04, cy + s * 0.82,
                      fill=ink, width=1.8, capstyle=tk.ROUND)

    elif name == 'hand':
        for dx, top, bot in [(-0.42, -0.25, 0.25), (-0.16, -0.62, 0.20),
                             (0.10, -0.68, 0.20), (0.36, -0.52, 0.25)]:
            c.create_line(cx + s * dx, cy + s * top, cx + s * dx, cy + s * bot,
                          fill=ink, width=2.4, capstyle=tk.ROUND)
        c.create_arc(cx - s * 0.52, cy - s * 0.15, cx + s * 0.48, cy + s * 0.75,
                     start=180, extent=180, style='pieslice',
                     fill='#efeaff' if active else '#ffffff', outline=ink, width=1.6)
        c.create_line(cx - s * 0.68, cy + s * 0.12, cx - s * 0.42, cy + s * 0.42,
                      fill=ink, width=2.4, capstyle=tk.ROUND)

    elif name == 'shape':
        c.create_oval(cx - s * 0.68, cy - s * 0.68, cx + s * 0.16, cy + s * 0.16,
                      fill='#efeaff' if active else '#ffffff', outline=ink, width=1.7)
        c.create_rectangle(cx - s * 0.08, cy - s * 0.08, cx + s * 0.68, cy + s * 0.68,
                           fill='#ffffff', outline=accent, width=1.8)

    elif name == 'shape_line':
        c.create_line(cx - s * 0.62, cy + s * 0.62, cx + s * 0.62, cy - s * 0.62,
                      fill=ink, width=2.2, capstyle=tk.ROUND)

    elif name == 'shape_arrow':
        c.create_line(cx - s * 0.62, cy + s * 0.62, cx + s * 0.58, cy - s * 0.58,
                      fill=ink, width=2.2, capstyle=tk.ROUND)
        c.create_line(cx + s * 0.10, cy - s * 0.58, cx + s * 0.60, cy - s * 0.60,
                      fill=ink, width=2.2, capstyle=tk.ROUND)
        c.create_line(cx + s * 0.60, cy - s * 0.60, cx + s * 0.58, cy - s * 0.10,
                      fill=ink, width=2.2, capstyle=tk.ROUND)

    elif name == 'shape_rectangle':
        c.create_rectangle(cx - s * 0.64, cy - s * 0.48, cx + s * 0.64, cy + s * 0.48,
                           fill='#f5f3ff' if active else '#ffffff', outline=ink, width=2.0)

    elif name == 'shape_ellipse':
        c.create_oval(cx - s * 0.62, cy - s * 0.54, cx + s * 0.62, cy + s * 0.54,
                      fill='#f5f3ff' if active else '#ffffff', outline=ink, width=2.0)

    elif name == 'shape_triangle':
        c.create_polygon(cx, cy - s * 0.62, cx + s * 0.66, cy + s * 0.54, cx - s * 0.66, cy + s * 0.54,
                         fill='#f5f3ff' if active else '#ffffff', outline=ink, width=2.0, joinstyle=tk.ROUND)

    elif name == 'text':
        c.create_line(cx - s * 0.56, cy - s * 0.58, cx + s * 0.56, cy - s * 0.58,
                      fill=ink, width=2.2, capstyle=tk.ROUND)
        c.create_line(cx, cy - s * 0.58, cx, cy + s * 0.62,
                      fill=ink, width=2.2, capstyle=tk.ROUND)
        c.create_line(cx - s * 0.28, cy + s * 0.62, cx + s * 0.28, cy + s * 0.62,
                      fill=accent, width=2.0, capstyle=tk.ROUND)

    elif name == 'sticky':
        # Miro-style folded corner sticky note icon
        c.create_polygon(
            cx - s * 0.62, cy - s * 0.62,
            cx + s * 0.62, cy - s * 0.62,
            cx + s * 0.62, cy + s * 0.24,
            cx + s * 0.24, cy + s * 0.62,
            cx - s * 0.62, cy + s * 0.62,
            fill='#fef08a', outline=ink, width=1.6, joinstyle=tk.ROUND
        )
        c.create_polygon(
            cx + s * 0.24, cy + s * 0.62,
            cx + s * 0.24, cy + s * 0.24,
            cx + s * 0.62, cy + s * 0.24,
            fill='#fde047', outline=ink, width=1.4, joinstyle=tk.ROUND
        )
        c.create_line(cx - s * 0.34, cy - s * 0.24, cx + s * 0.32, cy - s * 0.24,
                      fill='#854d0e', width=1.5, capstyle=tk.ROUND)
        c.create_line(cx - s * 0.34, cy + s * 0.06, cx + s * 0.14, cy + s * 0.06,
                      fill='#854d0e', width=1.5, capstyle=tk.ROUND)

    elif name == 'image':
        # Framed landscape photo icon
        c.create_rectangle(cx - s * 0.66, cy - s * 0.54, cx + s * 0.66, cy + s * 0.54,
                           fill='#f8fafc', outline=ink, width=1.7)
        c.create_oval(cx - s * 0.42, cy - s * 0.32, cx - s * 0.18, cy - s * 0.08,
                      fill='#f59e0b', outline='')
        c.create_polygon(
            cx - s * 0.54, cy + s * 0.44,
            cx - s * 0.12, cy - s * 0.04,
            cx + s * 0.18, cy + s * 0.26,
            cx + s * 0.36, cy + s * 0.08,
            cx + s * 0.56, cy + s * 0.44,
            fill=accent, outline=''
        )

    elif name == 'pages':
        c.create_rectangle(cx - s * 0.34, cy - s * 0.68, cx + s * 0.58, cy + s * 0.46,
                           fill='#f4f5fa', outline='#9aa3b8', width=1.4)
        c.create_rectangle(cx - s * 0.56, cy - s * 0.44, cx + s * 0.36, cy + s * 0.68,
                           fill='#ffffff', outline=ink, width=1.7)
        c.create_line(cx - s * 0.34, cy - s * 0.12, cx + s * 0.14, cy - s * 0.12,
                      fill=accent, width=1.6, capstyle=tk.ROUND)
        c.create_line(cx - s * 0.34, cy + s * 0.18, cx + s * 0.04, cy + s * 0.18,
                      fill='#9aa3b8', width=1.5, capstyle=tk.ROUND)

    elif name == 'undo':
        c.create_arc(cx - s * 0.52, cy - s * 0.32, cx + s * 0.58, cy + s * 0.62,
                     start=0, extent=170, style='arc', outline=ink, width=2.0)
        c.create_polygon(cx - s * 0.64, cy - s * 0.05, cx - s * 0.26, cy - s * 0.42,
                         cx - s * 0.22, cy + s * 0.06, fill=ink, outline='')

    elif name == 'redo':
        c.create_arc(cx - s * 0.58, cy - s * 0.32, cx + s * 0.52, cy + s * 0.62,
                     start=10, extent=170, style='arc', outline=ink, width=2.0)
        c.create_polygon(cx + s * 0.64, cy - s * 0.05, cx + s * 0.26, cy - s * 0.42,
                         cx + s * 0.22, cy + s * 0.06, fill=ink, outline='')

    elif name == 'menu':
        for dy, w_fac in [(-0.44, 0.64), (0.0, 0.48), (0.44, 0.64)]:
            c.create_line(cx - s * 0.60, cy + s * dy, cx - s * 0.60 + s * 2 * w_fac, cy + s * dy,
                          fill=ink, width=2.0, capstyle=tk.ROUND)

    elif name == 'grip':
        for dx in (-0.26, 0.26):
            for dy in (-0.45, 0.0, 0.45):
                c.create_oval(cx + s * dx - 1.5, cy + s * dy - 1.5,
                              cx + s * dx + 1.5, cy + s * dy + 1.5,
                              fill='#b0b8ca', outline='')
