"""Pure two-axis writing-area navigation, independent of Windows and Tk."""
from engine import clamp, window_span


def move_window(origin, direction, zoom, pad_ratio, page, overlap=.16, fine=False):
    """Move one writing-window cell; preserve X for vertical, Y for horizontal.

    `newline` is a separate intentional operation that returns to the left margin.
    """
    w, h = window_span(zoom, pad_ratio, page=page)
    rate = .23 if fine else (1.0 - clamp(overlap, .05, .5))
    dx, dy = w * rate, h * rate
    x, y = origin
    if direction == 'left': x -= dx
    elif direction == 'right': x += dx
    elif direction == 'up': y -= dy
    elif direction == 'down': y += dy
    elif direction == 'newline':
        x = page[0] * .09
        y += h * .82
    elif direction == 'home': x = page[0] * .09
    else: raise ValueError('Invalid navigation direction')
    return [clamp(x, 0, max(0, page[0] - w)), clamp(y, 0, max(0, page[1] - h))]


def window_from_map(u, v, zoom, pad_ratio, page):
    """Click a page overview to center the active writing window there."""
    w,h = window_span(zoom,pad_ratio,page=page)
    return [clamp(clamp(u)*page[0]-w/2,0,max(0,page[0]-w)),
            clamp(clamp(v)*page[1]-h/2,0,max(0,page[1]-h))]


def edge_turn(start_u,start_v,last_u,last_v,num_points,threshold=.085):
    """Auto-pan only on a directional stroke ending near an outward edge."""
    if num_points < 5 or None in (start_u,start_v,last_u,last_v):
        return None
    dx,dy=last_u-start_u,last_v-start_v
    candidates=[]
    if last_u>=.925 and dx>=threshold:candidates.append(('right',abs(dx)))
    if last_u<=.075 and dx<=-threshold:candidates.append(('left',abs(dx)))
    if last_v>=.925 and dy>=threshold:candidates.append(('down',abs(dy)))
    if last_v<=.075 and dy<=-threshold:candidates.append(('up',abs(dy)))
    return max(candidates,key=lambda p:p[1])[0] if candidates else None
