# OpticLogic — Technical Implementation Report

| Field | Value |
|---|---|
| Project | OpticLogic — grid-based optical puzzle game |
| Language / Framework | Python 3.12, Pygame 2.6 |
| Deliverables | `opticlogic_prototype.py` (Iteration 1), `opticlogic.py` (Iteration 2) |
| Supporting assets | `levels/example.json`, `screenshots/`, `tools/take_screenshots.py` |
| Document scope | Architecture, core algorithms, prototype-to-release evolution, error tracking |

---

## 1. Introduction

### 1.1 Purpose

This document records the technical implementation of OpticLogic, a two-dimensional
puzzle game in which the player places optical components on a 16×16 grid to route
laser beams onto colour-matched receptors. It describes the system architecture, the
core ray-tracing algorithm, the colour model, and the persistence layer, and it traces
the evolution of the codebase from an initial prototype to the refined release version.
A dedicated error-tracking section (Section 6) documents defects encountered during
development, their root causes, and their resolutions.

### 1.2 Functional Summary

- **Grid:** fixed 16×16 board; every component occupies exactly one cell.
- **Beam propagation:** recursive ray-tracing, hard-capped at 50 total segments per frame.
- **Components:** emitters, plane mirrors, beam splitters, triangular prisms, obstacles,
  and receptors.
- **Colour system:** beams carry independent red/green/blue channels which can be
  split by prisms and additively recombined at receptors.
- **Win condition:** every receptor receives exactly its required channel set.
- **Level editor:** in-game editor with JSON serialisation for saving and loading puzzles.

---

## 2. System Architecture

### 2.1 Module Structure

The release version is a single module (`opticlogic.py`) organised into six functional
layers. The layers communicate only through plain data structures, which keeps the
simulation logic independent of Pygame and therefore testable without a display.

| Layer | Functions | Responsibility |
|---|---|---|
| Constants and geometry | `turn_left`, `turn_right`, `cell_centre`, direction/bounce tables | Grid mathematics and direction algebra |
| Component model | `make_component`, `default_level` | Construction of component records |
| Simulation | `trace_all`, `_trace`, `check_win` | Beam propagation and win evaluation |
| Persistence | `save_level`, `load_level` | JSON serialisation of the board |
| Input | `play_click`, `editor_place`, `editor_rotate`, `editor_cycle_colour` | Mode-dependent mouse/keyboard handling |
| Rendering | `draw`, `draw_component` | Frame composition |

### 2.2 Data Model

The board is a dictionary mapping cell coordinates to component records:

```python
comps: dict[tuple[int, int], dict]
```

Components are deliberately plain dictionaries rather than classes. This decision was
made after the prototype phase because it makes the persistence layer trivial: a
component record is already a valid JSON object and requires no custom encoder or
schema-mapping code (Section 5.3).

| Key | Present on | Type | Meaning |
|---|---|---|---|
| `type` | all | string | One of `emitter`, `mirror`, `splitter`, `prism`, `obstacle`, `receptor` |
| `fixed` | all | boolean | `true` for level furniture; `false` for player-placed mirrors |
| `orient` | mirror, splitter | string | `"/"` or `"\"` — reflection axis |
| `dir` | emitter | `[dx, dy]` | Emission direction |
| `colour` | emitter, receptor | `[r, g, b]` | Channel flags (0 or 1 per channel) |

### 2.3 Coordinate Conventions

- Cell coordinates are `(x, y)` with the origin at the top-left; `y` increases downwards.
- Directions are unit vectors: `RIGHT (1, 0)`, `LEFT (-1, 0)`, `UP (0, -1)`, `DOWN (0, 1)`.
- Pixel conversion is performed only in the rendering layer via
  `cell_centre(x, y) = (x·CELL + CELL/2, y·CELL + CELL/2)` with `CELL = 40`.
- Because `y` grows downwards, a mathematically "anticlockwise" rotation appears
  clockwise on screen; the helpers `turn_left((dx, dy)) = (dy, -dx)` and
  `turn_right((dx, dy)) = (-dy, dx)` encapsulate this so no other code reasons about it.

---

## 3. Core Algorithms

### 3.1 Recursive Ray-Tracing

Beam propagation is implemented as a depth-first recursion. `trace_all` starts one
trace per emitter; `_trace` walks cell by cell in a straight line until it meets a
component or the board edge, emits exactly one visual segment, and then either
terminates or recurses in one or more new directions.

Key properties of the algorithm:

- **One segment per call.** Every invocation of `_trace` appends exactly one entry to
  the segment list. The recursion depth and the segment count are therefore identical,
  which allows a single counter to bound both.
- **Shared segment budget.** A mutable one-element list `budget = [MAX_SEGMENTS]`
  is threaded through the recursion and decremented on entry. When it reaches zero
  every pending branch terminates, regardless of the component configuration. With
  `MAX_SEGMENTS = 50` this guarantees termination even for closed mirror loops and
  exponentially branching splitter arrangements (Sections 6.1 and 6.2).
- **Stateless re-simulation.** The full trace is recomputed from the component
  dictionary every frame. With at most 50 segments the cost is negligible
  (microseconds), and it eliminates any possibility of stale beam state after an edit.

The branching behaviour per component type is:

| Component | Beams out | Direction rule | Colour rule |
|---|---|---|---|
| Obstacle | 0 | — | Beam absorbed |
| Emitter (hit by beam) | 0 | — | Beam absorbed |
| Receptor | 0 | — | Channels accumulated into `hits` (Section 3.2) |
| Plane mirror | 1 | 90° reflection per `SLASH_BOUNCE` / `BACKSLASH_BOUNCE` table | Unchanged |
| Beam splitter | 2 | Pass-through **and** 90° reflection | Both copies unchanged |
| Prism | 1–3 | Red continues straight; green deviates 90° left; blue deviates 90° right | Beam decomposed into its individual channels |

Reflection is table-driven rather than computed. For a `/` mirror:

```python
SLASH_BOUNCE = {RIGHT: UP, LEFT: DOWN, UP: RIGHT, DOWN: LEFT}
```

This is both faster and less error-prone than deriving the reflection from vector
arithmetic at runtime, and the two tables double as documentation of the intended
physics.

### 3.2 The RGB Channel Model

A beam's colour is a tuple of three binary channel flags, giving seven possible beam
colours (the eighth state, `(0, 0, 0)`, is "no beam" and is rejected at the top of
`_trace`).

| Channels | Rendered colour |
|---|---|
| `(1, 0, 0)` | Red |
| `(0, 1, 0)` | Green |
| `(0, 0, 1)` | Blue |
| `(1, 1, 0)` | Yellow |
| `(0, 1, 1)` | Cyan |
| `(1, 0, 1)` | Magenta |
| `(1, 1, 1)` | White |

Two operations are defined on this model:

- **Splitting (prism).** The beam is decomposed into its constituent channels; each
  present channel leaves the prism in its own direction. A white beam therefore fans
  into three primary beams, while a yellow beam produces only a red and a green beam.
- **Mixing (receptor).** Receptors accumulate the channels of every beam that reaches
  them with a bitwise OR: `acc[i] |= colour[i]`. Mixing is therefore idempotent and
  order-independent — two red beams mix to red, and a red plus a green beam mix to
  yellow irrespective of arrival order (see Section 6.4 for the defect history of this
  operation).

### 3.3 Win Evaluation

`check_win` requires an **exact** match between each receptor's accumulated channels
and its required colour. An exact match, rather than a superset test, was chosen so
that over-delivery is a failure state: flooding a red receptor with a white beam does
not solve it. This materially increases puzzle design space, because obstacles and
prisms can be used to force the player to *remove* channels as well as to deliver them.

### 3.4 Level Persistence

Levels serialise to a single JSON document:

```json
{
  "grid_size": 16,
  "components": [
    { "x": 0, "y": 3, "type": "emitter", "fixed": true,
      "dir": [1, 0], "colour": [1, 1, 1] },
    { "x": 8, "y": 3, "type": "prism", "fixed": true }
  ]
}
```

- `save_level` flattens the `{(x, y): comp}` dictionary into a coordinate-sorted list
  (sorting makes saved files diff-stable under version control).
- `load_level` reverses the transformation; because components are already plain
  dictionaries, no per-type deserialisation logic exists.
- The format round-trips exactly: `load_level(save_level(c)) == c` is asserted in the
  verification suite (Section 5.4).

---

## 4. Evolution: Prototype to Refined Version

### 4.1 Prototype Scope (Iteration 1)

The prototype (`opticlogic_prototype.py`) was intentionally minimal and served to
validate the core interaction loop before any complex features were committed to:

- 16×16 grid with one hard-coded emitter and one receptor;
- plane mirrors placed by cycling a cell through `empty → / → \ → empty`;
- a **flat, iterative** beam walk (`trace_beam`) — a single `for` loop bounded at 50
  iterations, sufficient because a mirror-only system can never branch;
- a monochrome white beam and a boolean win flag.

### 4.2 Refinement Summary (Iteration 2)

The introduction of splitters and prisms was the forcing function for the refactor:
a beam that can branch cannot be traced by a single loop, so the tracer was rewritten
as a recursion and every other subsystem was generalised around it.

| Concern | Prototype | Refined version | Reason for change |
|---|---|---|---|
| Board representation | `16×16` list-of-lists of integer codes | `dict[(x, y) → component dict]` | Components acquired per-instance state (orientation, direction, colour, ownership) that integer codes cannot carry; a sparse dict also serialises directly to JSON |
| Beam tracing | Single iterative loop, one beam | Recursive `_trace` with shared 50-segment budget | Splitters and prisms branch the beam; recursion mirrors the branching structure naturally |
| Colour | Implicit white | `(r, g, b)` channel tuple with splitting and OR-mixing | Core requirement of the final design |
| Win condition | Boolean "beam touched receptor" | Exact per-receptor channel match over all receptors | Multiple receptors with distinct colour requirements |
| Components | Emitter, mirror, receptor | + splitter, prism, obstacle; fixed vs player-owned flag | Final feature set; editor needs to distinguish level furniture from player pieces |
| Persistence | None | JSON save/load with round-trip guarantee | Level editor requirement |
| Modes | Play only | Play / Edit with mode-specific input handling | Level editor requirement |

### 4.3 What Was Deliberately Preserved

- The **50-segment hard cap** carried over unchanged from the prototype's loop bound;
  it simply moved from a `for`-loop range into a recursion budget.
- The **table-driven mirror reflection** (`SLASH_BOUNCE` / `BACKSLASH_BOUNCE`)
  survived verbatim and was reused by the beam splitter's reflected branch.
- The **per-frame full re-trace** policy was retained after profiling confirmed it was
  not a bottleneck at the capped segment count (Section 6.2).

---

## 5. Verification

### 5.1 Method

The simulation layer is fully decoupled from the display, so all functional testing was
performed headlessly under `SDL_VIDEODRIVER=dummy`. Screenshots for documentation
were produced the same way by `tools/take_screenshots.py`.

### 5.2 Functional Test Matrix

| # | Scenario | Expected result | Outcome |
|---|---|---|---|
| 1 | White beam into prism | Three primary beams; R/G/B receptors each report exactly their own channel | Pass |
| 2 | Red + green emitters mirrored onto a yellow receptor | `hits == [1, 1, 0]`; `check_win` returns `True` | Pass |
| 3 | Single beam into a `/` splitter | Exactly 3 segments (1 inbound, 2 outbound) | Pass |
| 4 | Chained splitter "hall of mirrors" (6 splitters, 18 mirrors) | Trace terminates; total segments ≤ 50 (measured: 34) | Pass |
| 5 | JSON round-trip of a mid-game board | `load_level(path)` equals the saved dictionary exactly | Pass |
| 6 | Closed four-mirror loop (prototype) | Loop terminates at the segment cap; no hang | Pass |

### 5.3 Documentation Screenshots

| File | State captured |
|---|---|
| `screenshots/iter1_initial.png` | Prototype: unsolved level, beam travelling straight |
| `screenshots/iter1_solved.png` | Prototype: two-mirror solution, win banner |
| `screenshots/iter2_prism_split.png` | Prism dispersing a white beam into R/G/B |
| `screenshots/iter2_mixing_solved.png` | Yellow receptor solved by mixing red and green |
| `screenshots/iter2_splitter.png` | Beam splitter pass-through and reflection |
| `screenshots/iter2_editor.png` | Editor mode with tool palette |

---

## 6. Development and Error Tracking

Defects were tracked with sequential identifiers. The four most instructive are
documented below with root-cause analysis and the corrective change.

| ID | Symptom | Subsystem | Severity | Status |
|---|---|---|---|---|
| ERR-01 | Game froze, then crashed with `RecursionError`, when two mirrors faced each other | Ray tracer | Critical | Closed |
| ERR-02 | Frame rate collapsed from 60 FPS to under 15 FPS once several beams were on screen | Rendering | High | Closed |
| ERR-03 | Mirrors placed one cell away from the clicked cell near cell boundaries | Input | Medium | Closed |
| ERR-04 | Yellow (mixed-colour) receptors could never be satisfied | Colour model | High | Closed |

### 6.1 ERR-01 — Unbounded Recursion in the Beam Tracer

**Symptom.** Placing two parallel mirrors facing each other (`/` above `\`) froze the
game for several seconds and then crashed with
`RecursionError: maximum recursion depth exceeded`.

**Root cause.** When the tracer was first converted from the prototype's flat loop to
a recursive function, the prototype's iteration bound was lost in translation. The
recursive version had no termination condition other than "beam leaves the board or is
absorbed" — a condition that a closed mirror loop never satisfies. Each bounce
consumed a stack frame until Python's recursion limit (~1000) was reached.

**Before:**

```python
def _trace(comps, start, direction, colour, segments, hits):
    x, y = start
    dx, dy = direction
    while True:
        nx, ny = x + dx, y + dy
        ...
        if ctype == "mirror":
            bounce = SLASH_BOUNCE if comp["orient"] == "/" else BACKSLASH_BOUNCE
            _trace(comps, (nx, ny), bounce[direction], colour,
                   segments, hits)     # nothing stops a closed loop
            return
```

**Fix.** A shared budget — a one-element mutable list so that every branch of the
recursion decrements the *same* counter — is checked on entry. Because each call emits
exactly one segment, capping calls at 50 also caps drawn segments at 50.

**After:**

```python
def _trace(comps, start, direction, colour, segments, hits, budget):
    if budget[0] <= 0 or colour == (0, 0, 0):
        return
    budget[0] -= 1
    ...
```

**Verification.** Test 6 (closed mirror loop) and test 4 (splitter cascade) both
terminate within the cap. The worst observed recursion depth is 50, far below the
interpreter limit.

**Lesson.** When porting an iterative algorithm to a recursive one, loop bounds are
part of the algorithm, not an implementation detail; they must be ported too — and for
*branching* recursion the bound must be shared across branches, not per-branch.

### 6.2 ERR-02 — Frame-Rate Collapse from Per-Cell Beam Drawing

**Symptom.** With the prism level loaded, the frame rate fell from a locked 60 FPS to
12–15 FPS, and input became visibly laggy. Profiling with `python -m cProfile` showed
more than 80 % of frame time inside surface creation and blitting.

**Root cause.** The first rendering pass drew the beam one grid cell at a time, and
each cell drew a "glow" by allocating a fresh per-pixel-alpha surface every frame. A
beam crossing the board is up to 16 cells, so five beams cost ~80 surface allocations
and blits per frame — repeated 60 times per second. The allocation, not the drawing,
was the bottleneck.

**Before:**

```python
# inside the tracer: one draw entry per cell stepped through
for cell in beam_cells:
    glow = pygame.Surface((CELL, CELL), pygame.SRCALPHA)   # new surface per cell,
    pygame.draw.rect(glow, (*rgb, 90), glow.get_rect())    # per frame
    screen.blit(glow, (cell[0] * CELL, cell[1] * CELL))
```

**Fix.** The tracer was changed to emit one entry per *straight run* rather than per
cell: a segment is recorded only when the beam changes direction, terminates, or
leaves the board. Rendering then draws each segment as a single line between the two
cell centres, with no intermediate surfaces.

**After:**

```python
# tracer output: ((start_cell, end_cell, colour)) per straight run
for start, end, colour in segments:
    pygame.draw.line(screen, channel_rgb(colour),
                     cell_centre(*start), cell_centre(*end), 3)
```

**Verification.** The draw cost is now bounded by the segment cap (≤ 50 line calls per
frame). The prism level renders at a stable 60 FPS, and the change had a second
benefit: the segment list became the natural unit for the ERR-01 budget.

**Lesson.** In Pygame, per-frame `Surface` allocation is far more expensive than the
draw calls themselves; batch geometry into the fewest primitives possible and never
allocate surfaces inside the render loop.

### 6.3 ERR-03 — Grid Snapping Offset in Mouse Placement

**Symptom.** Clicking near the right or bottom edge of a cell placed the mirror in the
*adjacent* cell. The defect was intermittent in play-testing — clicks near cell
centres behaved correctly — which initially suggested an event-handling race rather
than an arithmetic error.

**Root cause.** Pixel-to-cell conversion used `round()` (snap to the **nearest** cell
origin) instead of floor division (snap to the **containing** cell). For any click in
the right half of a cell, `round(px / CELL)` rounds up to the next column. A
secondary defect in the same code path was that clicks on the status panel below the
board produced row 16 and crashed the prototype's list-based grid with an
`IndexError`.

**Before:**

```python
def handle_click(grid, px, py):
    x = round(px / CELL)          # snaps to nearest gridline, not containing cell
    y = round(py / CELL)
    cell = grid[y][x]             # IndexError when the panel is clicked (y == 16)
```

**After:**

```python
def handle_click(grid, px, py):
    if py >= GRID_SIZE * CELL:    # ignore clicks on the status panel
        return
    x, y = px // CELL, py // CELL # floor division: the containing cell
```

**Verification.** Parameterised checks over all four corner pixels of several cells
(e.g. `(x·CELL, y·CELL)` and `((x+1)·CELL − 1, (y+1)·CELL − 1)`) confirm every pixel
maps to its containing cell, and panel clicks are ignored.

**Lesson.** "Snap to grid" has two distinct meanings — nearest gridline versus
containing cell — and `round()` silently implements the wrong one for hit-testing.
Integer floor division is the correct primitive for point-in-cell queries.

### 6.4 ERR-04 — Incorrect Colour Blending at Receptors

**Symptom.** Receptors requiring mixed colours (e.g. yellow, `[1, 1, 0]`) never
registered as satisfied, even when a red and a green beam were both visibly
terminating on them. Single-colour receptors worked correctly, which wrongly directed
suspicion at the prism rather than the receptor.

**Root cause.** Channel accumulation used arithmetic addition. Two red beams hitting
the same receptor produced `[2, 0, 0]`; a red and a green beam produced `[1, 1, 0]`
*only if no channel arrived twice*. In the prism level, the receptor was also grazed
by a second red beam reflected off a player mirror, yielding `[2, 1, 0]` — which fails
the exact-match comparison `hits.get(pos) == list(colour)` because `2 != 1`.

**Before:**

```python
if ctype == "receptor":
    acc = hits.setdefault((nx, ny), [0, 0, 0])
    for i in range(3):
        acc[i] += colour[i]       # counts beams; [2, 1, 0] != [1, 1, 0]
    return
```

**Fix.** Light does not stack per channel in this model — a channel is either present
or absent. Accumulation was changed to a bitwise OR, which is idempotent and
order-independent.

**After:**

```python
if ctype == "receptor":
    acc = hits.setdefault((nx, ny), [0, 0, 0])
    for i in range(3):
        acc[i] |= colour[i]       # presence, not count: [1, 1, 0] == [1, 1, 0]
    return
```

**Verification.** Test 2 (red + green onto a yellow receptor) passes, including the
variant where the same channel arrives via two distinct beam paths.

**Lesson.** The accumulation operator must match the semantics of the domain model.
Presence-based systems require an idempotent operation (OR, set union); using a
counting operation introduced states (`2`) that the rest of the system did not define.

---

## 7. Conclusions

- Bounding the tracer by **total segments** rather than recursion depth solved the
  termination problem (ERR-01) and the rendering-cost problem (ERR-02) with a single
  mechanism, because "one call = one segment" ties the two together.
- Representing components as **plain JSON-shaped dictionaries** made the level editor's
  persistence layer nearly free and eliminated an entire class of serialisation bugs.
- The prototype-first approach paid off: the flat tracer, the bounce tables, and the
  segment cap all survived into the release version, while the parts that were going to
  change anyway (integer cell codes, the boolean win flag) were never over-engineered.
