"""OpticLogic -- Iteration 1 prototype.

A minimal grid-based laser puzzle:
  * 16x16 grid
  * one fixed emitter firing a white beam
  * plane mirrors the player can place/rotate/remove by clicking
  * one receptor; the level is "won" when the beam reaches it

No colours, prisms, splitters or level editor yet -- this is the
throwaway prototype used to validate the core beam-tracing loop.
"""

import sys

import pygame

# --- constants -------------------------------------------------------------

GRID_SIZE = 16
CELL = 40
STATUS_H = 40
SCREEN_W = GRID_SIZE * CELL
SCREEN_H = GRID_SIZE * CELL + STATUS_H

MAX_SEGMENTS = 50  # hard cap so a mirror loop can never hang the game

# cell contents
EMPTY = 0
EMITTER = 1
MIRROR_SLASH = 2      # '/'
MIRROR_BACKSLASH = 3  # '\'
RECEPTOR = 4

# directions as (dx, dy); y grows downwards
RIGHT = (1, 0)
LEFT = (-1, 0)
UP = (0, -1)
DOWN = (0, 1)

# how each mirror bounces an incoming direction
SLASH_BOUNCE = {RIGHT: UP, LEFT: DOWN, UP: RIGHT, DOWN: LEFT}
BACKSLASH_BOUNCE = {RIGHT: DOWN, LEFT: UP, UP: LEFT, DOWN: RIGHT}

BG_COLOUR = (18, 18, 24)
GRID_COLOUR = (45, 45, 60)
BEAM_COLOUR = (255, 255, 255)


# --- level state -----------------------------------------------------------

def make_level():
    """Hard-coded test level: emitter on the left edge, receptor bottom-right."""
    grid = [[EMPTY for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    grid[3][0] = EMITTER
    grid[12][15] = RECEPTOR
    emitter = {"pos": (0, 3), "dir": RIGHT}
    return grid, emitter


def cell_centre(x, y):
    return x * CELL + CELL // 2, y * CELL + CELL // 2


# --- beam tracing ----------------------------------------------------------

def trace_beam(grid, emitter):
    """Walk the beam cell by cell.

    Returns (segments, won) where segments is a list of
    ((x1, y1), (x2, y2)) pixel pairs and won is True if the beam
    reached the receptor.
    """
    segments = []
    won = False

    x, y = emitter["pos"]
    dx, dy = emitter["dir"]
    seg_start = (x, y)

    for _ in range(MAX_SEGMENTS):
        nx, ny = x + dx, y + dy

        # left the board -> final segment ends at the last cell
        if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
            segments.append((cell_centre(*seg_start), cell_centre(x, y)))
            break

        cell = grid[ny][nx]

        if cell == RECEPTOR:
            segments.append((cell_centre(*seg_start), cell_centre(nx, ny)))
            won = True
            break

        if cell in (MIRROR_SLASH, MIRROR_BACKSLASH):
            # segment ends on the mirror, beam continues in the new direction
            segments.append((cell_centre(*seg_start), cell_centre(nx, ny)))
            bounce = SLASH_BOUNCE if cell == MIRROR_SLASH else BACKSLASH_BOUNCE
            dx, dy = bounce[(dx, dy)]
            x, y = nx, ny
            seg_start = (nx, ny)
            continue

        if cell == EMITTER:
            # beam dies if it comes back to the emitter
            segments.append((cell_centre(*seg_start), cell_centre(nx, ny)))
            break

        x, y = nx, ny

    return segments, won


# --- input -----------------------------------------------------------------

def handle_click(grid, px, py):
    """Left click cycles a cell: empty -> '/' -> '\\' -> empty."""
    if py >= GRID_SIZE * CELL:
        return  # clicked the status bar
    x, y = px // CELL, py // CELL
    cell = grid[y][x]
    if cell == EMPTY:
        grid[y][x] = MIRROR_SLASH
    elif cell == MIRROR_SLASH:
        grid[y][x] = MIRROR_BACKSLASH
    elif cell == MIRROR_BACKSLASH:
        grid[y][x] = EMPTY
    # emitter and receptor are fixed: clicks on them do nothing


# --- drawing ---------------------------------------------------------------

def draw(screen, font, grid, segments, won):
    screen.fill(BG_COLOUR)

    for i in range(GRID_SIZE + 1):
        pygame.draw.line(screen, GRID_COLOUR, (i * CELL, 0), (i * CELL, GRID_SIZE * CELL))
        pygame.draw.line(screen, GRID_COLOUR, (0, i * CELL), (GRID_SIZE * CELL, i * CELL))

    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            cell = grid[y][x]
            cx, cy = cell_centre(x, y)
            if cell == EMITTER:
                pygame.draw.rect(screen, (200, 60, 60),
                                 (x * CELL + 6, y * CELL + 6, CELL - 12, CELL - 12))
            elif cell == RECEPTOR:
                colour = (80, 220, 80) if won else (120, 120, 140)
                pygame.draw.circle(screen, colour, (cx, cy), CELL // 2 - 6, 3)
            elif cell == MIRROR_SLASH:
                pygame.draw.line(screen, (150, 200, 255),
                                 (x * CELL + 5, (y + 1) * CELL - 5),
                                 ((x + 1) * CELL - 5, y * CELL + 5), 4)
            elif cell == MIRROR_BACKSLASH:
                pygame.draw.line(screen, (150, 200, 255),
                                 (x * CELL + 5, y * CELL + 5),
                                 ((x + 1) * CELL - 5, (y + 1) * CELL - 5), 4)

    for start, end in segments:
        pygame.draw.line(screen, BEAM_COLOUR, start, end, 3)

    msg = "SOLVED!" if won else "Click a cell to place / rotate / remove a mirror"
    colour = (80, 220, 80) if won else (200, 200, 200)
    text = font.render(msg, True, colour)
    screen.blit(text, (10, GRID_SIZE * CELL + 10))


# --- main loop ---------------------------------------------------------------

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("OpticLogic (prototype)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 26)

    grid, emitter = make_level()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                handle_click(grid, *event.pos)

        segments, won = trace_beam(grid, emitter)
        draw(screen, font, grid, segments, won)
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
