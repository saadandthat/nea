"""Render documentation screenshots for both iterations headlessly.

Usage: python3 tools/take_screenshots.py
Writes PNGs into screenshots/.
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pygame

OUT = os.path.join(os.path.dirname(__file__), "..", "screenshots")
os.makedirs(OUT, exist_ok=True)


def save(screen, name):
    path = os.path.join(OUT, name)
    pygame.image.save(screen, path)
    print("wrote", path)


def prototype_shots():
    import opticlogic_prototype as p

    pygame.init()
    screen = pygame.display.set_mode((p.SCREEN_W, p.SCREEN_H))
    font = pygame.font.SysFont(None, 26)

    # 1. initial state: beam fires straight across and misses the receptor
    grid, emitter = p.make_level()
    segments, won = p.trace_beam(grid, emitter)
    p.draw(screen, font, grid, segments, won)
    save(screen, "iter1_initial.png")

    # 2. solved: two backslash mirrors route the beam into the receptor
    grid[3][10] = p.MIRROR_BACKSLASH
    grid[12][10] = p.MIRROR_BACKSLASH
    segments, won = p.trace_beam(grid, emitter)
    p.draw(screen, font, grid, segments, won)
    save(screen, "iter1_solved.png")

    pygame.display.quit()


def refined_shots():
    import opticlogic as g

    pygame.init()
    screen = pygame.display.set_mode((g.SCREEN_W, g.SCREEN_H))
    font = pygame.font.SysFont(None, 22)

    def render(comps, mode="play", tool="mirror", message=""):
        segments, hits = g.trace_all(comps)
        won = mode == "play" and g.check_win(comps, hits)
        g.draw(screen, font, comps, segments, hits, won, mode, tool, message)
        return won

    # 3. default level as first seen: prism has already split the white
    #    beam into R/G/B; the yellow mixing receptor is still unsolved
    comps = g.default_level()
    render(comps)
    save(screen, "iter2_prism_split.png")

    # 4. solved: player mirrors steer red + green onto the yellow receptor
    comps[(15, 10)] = {"type": "mirror", "fixed": False, "orient": "\\"}
    comps[(15, 12)] = {"type": "mirror", "fixed": False, "orient": "/"}
    won = render(comps)
    assert won
    save(screen, "iter2_mixing_solved.png")

    # 5. beam splitter demo: one white beam split into two paths that
    #    both terminate on white receptors
    comps = {
        (0, 8): {"type": "emitter", "fixed": True, "dir": [1, 0], "colour": [1, 1, 1]},
        (7, 8): {"type": "splitter", "fixed": True, "orient": "/"},
        (14, 8): {"type": "receptor", "fixed": True, "colour": [1, 1, 1]},
        (7, 2): {"type": "receptor", "fixed": True, "colour": [1, 1, 1]},
    }
    won = render(comps)
    assert won
    save(screen, "iter2_splitter.png")

    # 6. editor mode with the default level loaded and the prism tool armed
    comps = g.default_level()
    render(comps, mode="edit", tool="prism")
    save(screen, "iter2_editor.png")

    pygame.display.quit()


if __name__ == "__main__":
    prototype_shots()
    refined_shots()
