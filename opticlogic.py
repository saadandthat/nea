"""OpticLogic -- Iteration 2, the refined version.

Grid-based (16x16) laser puzzle with:
  * recursive ray-tracing, hard-capped at 50 segments
  * plane mirrors ('/' and '\\')
  * triangular prisms that split a beam into its R/G/B channels
  * beam splitters (pass-through + 90-degree reflection)
  * obstacles
  * colour-matched receptors with additive RGB mixing
  * a level editor with JSON save/load

Controls
--------
Play mode:
  left click        place / rotate / remove a player mirror
  Tab               switch to the editor
Editor mode:
  1..6              select tool (emitter, mirror, splitter, prism,
                    obstacle, receptor)
  left click        place selected component
  right click       delete component
  R                 rotate component under the cursor
  C                 cycle colour of emitter/receptor under the cursor
  S / L             save to / load from levels/custom.json
  Tab               back to play mode
"""

import copy
import json
import os
import sys

import pygame

# --- constants ---------------------------------------------------------------

GRID_SIZE = 16
CELL = 40
PANEL_H = 72
SCREEN_W = GRID_SIZE * CELL
SCREEN_H = GRID_SIZE * CELL + PANEL_H

MAX_SEGMENTS = 50  # global budget shared by every beam in the frame

DEFAULT_LEVEL_PATH = os.path.join("levels", "custom.json")

RIGHT, LEFT, UP, DOWN = (1, 0), (-1, 0), (0, -1), (0, 1)
DIRS = [RIGHT, DOWN, LEFT, UP]  # clockwise rotation order

SLASH_BOUNCE = {RIGHT: UP, LEFT: DOWN, UP: RIGHT, DOWN: LEFT}
BACKSLASH_BOUNCE = {RIGHT: DOWN, LEFT: UP, UP: LEFT, DOWN: RIGHT}

# colour channels are (r, g, b) flags; render colour is channel * 255
COLOUR_CYCLE = [
    (1, 0, 0), (0, 1, 0), (0, 0, 1),          # primaries
    (1, 1, 0), (0, 1, 1), (1, 0, 1),          # secondaries
    (1, 1, 1),                                # white
]

TOOLS = ["emitter", "mirror", "splitter", "prism", "obstacle", "receptor"]

BG_COLOUR = (18, 18, 24)
GRID_COLOUR = (45, 45, 60)
PANEL_COLOUR = (30, 30, 40)


def turn_left(d):
    dx, dy = d
    return (dy, -dx)


def turn_right(d):
    dx, dy = d
    return (-dy, dx)


def channel_rgb(colour):
    return tuple(255 if c else 0 for c in colour)


# --- components ---------------------------------------------------------------

def make_component(ctype, fixed=True):
    """Components are plain dicts so they serialise to JSON directly."""
    comp = {"type": ctype, "fixed": fixed}
    if ctype in ("mirror", "splitter"):
        comp["orient"] = "/"
    if ctype == "emitter":
        comp["dir"] = list(RIGHT)
        comp["colour"] = [1, 1, 1]
    if ctype == "receptor":
        comp["colour"] = [1, 1, 1]
    return comp


def default_level():
    """Built-in demo level.

    A white emitter fires into a prism whose three channels land on
    matching receptors, and a red + green emitter pair must be steered
    by the player onto a yellow receptor (colour mixing).
    """
    comps = {}
    comps[(0, 3)] = {"type": "emitter", "fixed": True,
                     "dir": list(RIGHT), "colour": [1, 1, 1]}
    comps[(8, 3)] = {"type": "prism", "fixed": True}
    comps[(15, 3)] = {"type": "receptor", "fixed": True, "colour": [1, 0, 0]}
    comps[(8, 0)] = {"type": "receptor", "fixed": True, "colour": [0, 1, 0]}
    comps[(8, 15)] = {"type": "receptor", "fixed": True, "colour": [0, 0, 1]}

    comps[(0, 10)] = {"type": "emitter", "fixed": True,
                      "dir": list(RIGHT), "colour": [1, 0, 0]}
    comps[(0, 12)] = {"type": "emitter", "fixed": True,
                      "dir": list(RIGHT), "colour": [0, 1, 0]}
    comps[(15, 11)] = {"type": "receptor", "fixed": True, "colour": [1, 1, 0]}
    comps[(6, 8)] = {"type": "obstacle", "fixed": True}
    comps[(6, 9)] = {"type": "obstacle", "fixed": True}
    return comps


# --- ray tracing ----------------------------------------------------------------

def trace_all(comps):
    """Trace every emitter's beam.

    Returns (segments, hits):
      segments -- list of (start_cell, end_cell, channel_colour)
      hits     -- {receptor_pos: [r, g, b]} accumulated channels
    """
    segments = []
    hits = {}
    budget = [MAX_SEGMENTS]
    for pos, comp in comps.items():
        if comp["type"] == "emitter":
            _trace(comps, pos, tuple(comp["dir"]), tuple(comp["colour"]),
                   segments, hits, budget)
    return segments, hits


def _trace(comps, start, direction, colour, segments, hits, budget):
    """Recursively trace one beam. Each call emits exactly one segment,
    so the shared budget caps total segments at MAX_SEGMENTS."""
    if budget[0] <= 0 or colour == (0, 0, 0):
        return
    budget[0] -= 1

    x, y = start
    dx, dy = direction

    while True:
        nx, ny = x + dx, y + dy

        if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
            segments.append((start, (x, y), colour))
            return

        comp = comps.get((nx, ny))
        if comp is None:
            x, y = nx, ny
            continue

        segments.append((start, (nx, ny), colour))
        ctype = comp["type"]

        if ctype in ("obstacle", "emitter"):
            return  # absorbed

        if ctype == "receptor":
            acc = hits.setdefault((nx, ny), [0, 0, 0])
            for i in range(3):
                acc[i] |= colour[i]
            return

        if ctype == "mirror":
            bounce = SLASH_BOUNCE if comp["orient"] == "/" else BACKSLASH_BOUNCE
            _trace(comps, (nx, ny), bounce[direction], colour,
                   segments, hits, budget)
            return

        if ctype == "splitter":
            bounce = SLASH_BOUNCE if comp["orient"] == "/" else BACKSLASH_BOUNCE
            _trace(comps, (nx, ny), direction, colour,
                   segments, hits, budget)              # pass-through
            _trace(comps, (nx, ny), bounce[direction], colour,
                   segments, hits, budget)              # reflected
            return

        if ctype == "prism":
            r, g, b = colour
            if r:
                _trace(comps, (nx, ny), direction, (1, 0, 0),
                       segments, hits, budget)          # red: straight
            if g:
                _trace(comps, (nx, ny), turn_left(direction), (0, 1, 0),
                       segments, hits, budget)          # green: deviates left
            if b:
                _trace(comps, (nx, ny), turn_right(direction), (0, 0, 1),
                       segments, hits, budget)          # blue: deviates right
            return


def check_win(comps, hits):
    """Every receptor must receive exactly its required channel set."""
    receptors = [(pos, c) for pos, c in comps.items() if c["type"] == "receptor"]
    if not receptors:
        return False
    return all(hits.get(pos, [0, 0, 0]) == list(c["colour"])
               for pos, c in receptors)


# --- JSON save / load ----------------------------------------------------------

def save_level(comps, path=DEFAULT_LEVEL_PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data = {
        "grid_size": GRID_SIZE,
        "components": [{"x": x, "y": y, **comp}
                       for (x, y), comp in sorted(comps.items())],
    }
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)


def load_level(path=DEFAULT_LEVEL_PATH):
    with open(path) as fh:
        data = json.load(fh)
    comps = {}
    for entry in data["components"]:
        entry = dict(entry)
        pos = (entry.pop("x"), entry.pop("y"))
        comps[pos] = entry
    return comps


# --- input ---------------------------------------------------------------------

def play_click(comps, cell):
    """Play mode: cycle a player mirror (empty -> '/' -> '\\' -> empty)."""
    comp = comps.get(cell)
    if comp is None:
        comps[cell] = make_component("mirror", fixed=False)
    elif comp["type"] == "mirror" and not comp["fixed"]:
        if comp["orient"] == "/":
            comp["orient"] = "\\"
        else:
            del comps[cell]
    # fixed level furniture is untouchable in play mode


def editor_place(comps, cell, tool):
    comps[cell] = make_component(tool, fixed=True)


def editor_rotate(comps, cell):
    comp = comps.get(cell)
    if comp is None:
        return
    if comp["type"] in ("mirror", "splitter"):
        comp["orient"] = "\\" if comp["orient"] == "/" else "/"
    elif comp["type"] == "emitter":
        idx = DIRS.index(tuple(comp["dir"]))
        comp["dir"] = list(DIRS[(idx + 1) % 4])


def editor_cycle_colour(comps, cell):
    comp = comps.get(cell)
    if comp is None or comp["type"] not in ("emitter", "receptor"):
        return
    idx = COLOUR_CYCLE.index(tuple(comp["colour"]))
    comp["colour"] = list(COLOUR_CYCLE[(idx + 1) % len(COLOUR_CYCLE)])


# --- drawing ---------------------------------------------------------------------

def cell_centre(x, y):
    return x * CELL + CELL // 2, y * CELL + CELL // 2


def draw_component(screen, pos, comp, hits):
    x, y = pos
    cx, cy = cell_centre(x, y)
    ctype = comp["type"]

    if ctype == "emitter":
        pygame.draw.rect(screen, channel_rgb(comp["colour"]),
                         (x * CELL + 7, y * CELL + 7, CELL - 14, CELL - 14))
        dx, dy = comp["dir"]
        tip = (cx + dx * (CELL // 2 - 4), cy + dy * (CELL // 2 - 4))
        pygame.draw.line(screen, (255, 255, 255), (cx, cy), tip, 3)

    elif ctype == "mirror":
        shade = (150, 200, 255) if comp["fixed"] else (255, 220, 130)
        if comp["orient"] == "/":
            pts = ((x * CELL + 5, (y + 1) * CELL - 5),
                   ((x + 1) * CELL - 5, y * CELL + 5))
        else:
            pts = ((x * CELL + 5, y * CELL + 5),
                   ((x + 1) * CELL - 5, (y + 1) * CELL - 5))
        pygame.draw.line(screen, shade, *pts, 4)

    elif ctype == "splitter":
        pygame.draw.rect(screen, (110, 110, 160),
                         (x * CELL + 4, y * CELL + 4, CELL - 8, CELL - 8), 2)
        if comp["orient"] == "/":
            pts = ((x * CELL + 8, (y + 1) * CELL - 8),
                   ((x + 1) * CELL - 8, y * CELL + 8))
        else:
            pts = ((x * CELL + 8, y * CELL + 8),
                   ((x + 1) * CELL - 8, (y + 1) * CELL - 8))
        pygame.draw.line(screen, (190, 190, 235), *pts, 2)

    elif ctype == "prism":
        tri = ((cx, y * CELL + 6),
               (x * CELL + 6, (y + 1) * CELL - 6),
               ((x + 1) * CELL - 6, (y + 1) * CELL - 6))
        pygame.draw.polygon(screen, (70, 70, 95), tri)
        pygame.draw.polygon(screen, (220, 220, 255), tri, 2)

    elif ctype == "obstacle":
        pygame.draw.rect(screen, (90, 90, 100),
                         (x * CELL + 3, y * CELL + 3, CELL - 6, CELL - 6))

    elif ctype == "receptor":
        required = channel_rgb(comp["colour"])
        received = hits.get(pos, [0, 0, 0])
        satisfied = received == list(comp["colour"])
        pygame.draw.circle(screen, required, (cx, cy), CELL // 2 - 6,
                           0 if satisfied else 3)
        if received != [0, 0, 0] and not satisfied:
            pygame.draw.circle(screen, channel_rgb(received), (cx, cy),
                               CELL // 2 - 14)


def draw(screen, font, comps, segments, hits, won, mode, tool, message=""):
    screen.fill(BG_COLOUR)

    for i in range(GRID_SIZE + 1):
        pygame.draw.line(screen, GRID_COLOUR, (i * CELL, 0),
                         (i * CELL, GRID_SIZE * CELL))
        pygame.draw.line(screen, GRID_COLOUR, (0, i * CELL),
                         (GRID_SIZE * CELL, i * CELL))

    for start, end, colour in segments:
        pygame.draw.line(screen, channel_rgb(colour),
                         cell_centre(*start), cell_centre(*end), 3)

    for pos, comp in comps.items():
        draw_component(screen, pos, comp, hits)

    # status panel
    pygame.draw.rect(screen, PANEL_COLOUR,
                     (0, GRID_SIZE * CELL, SCREEN_W, PANEL_H))
    if mode == "play":
        line1 = "PLAY   |   click: place / rotate / remove mirror   |   Tab: editor"
        line2 = "SOLVED!" if won else (message or "Route every colour to its receptor.")
        colour2 = (80, 220, 80) if won else (200, 200, 200)
    else:
        names = "  ".join("[%d]%s%s" % (i + 1, t, "*" if t == tool else "")
                          for i, t in enumerate(TOOLS))
        line1 = "EDIT   " + names
        line2 = message or "click place | rclick delete | R rotate | C colour | S save | L load | Tab play"
        colour2 = (200, 200, 200)
    screen.blit(font.render(line1, True, (160, 200, 255)),
                (10, GRID_SIZE * CELL + 10))
    screen.blit(font.render(line2, True, colour2),
                (10, GRID_SIZE * CELL + 38))


# --- main loop --------------------------------------------------------------------

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("OpticLogic")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 22)

    comps = default_level()
    mode = "play"
    tool = "mirror"
    message = ""

    while True:
        mouse_cell = None
        mx, my = pygame.mouse.get_pos()
        if my < GRID_SIZE * CELL:
            mouse_cell = (mx // CELL, my // CELL)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    mode = "edit" if mode == "play" else "play"
                    message = ""
                elif mode == "edit":
                    if pygame.K_1 <= event.key <= pygame.K_6:
                        tool = TOOLS[event.key - pygame.K_1]
                    elif event.key == pygame.K_r and mouse_cell:
                        editor_rotate(comps, mouse_cell)
                    elif event.key == pygame.K_c and mouse_cell:
                        editor_cycle_colour(comps, mouse_cell)
                    elif event.key == pygame.K_s:
                        save_level(comps)
                        message = "saved to " + DEFAULT_LEVEL_PATH
                    elif event.key == pygame.K_l:
                        try:
                            comps = load_level()
                            message = "loaded " + DEFAULT_LEVEL_PATH
                        except FileNotFoundError:
                            message = "no saved level found"

            if event.type == pygame.MOUSEBUTTONDOWN and mouse_cell:
                if mode == "play" and event.button == 1:
                    play_click(comps, mouse_cell)
                elif mode == "edit":
                    if event.button == 1:
                        editor_place(comps, mouse_cell, tool)
                    elif event.button == 3:
                        comps.pop(mouse_cell, None)

        segments, hits = trace_all(comps)
        won = mode == "play" and check_win(comps, hits)
        draw(screen, font, comps, segments, hits, won, mode, tool, message)
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
