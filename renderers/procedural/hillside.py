"""The hillside's built things and its land detail (v3 phase 3, part 1).

A walled kitchen garden high on the left of the hill, with a shed and three beehives in it; a field gate
standing open in the gap the path goes through; rock outcrops breaking through the turf, gorse, heather
and patches of wildflowers; and puddles after rain.

None of it is light. Everything is drawn into the hill's own albedo and normal layers (land.py), so the
frame's sun, moon and sky light it, the tower's and the tree's shadows fall across it, its own shadows
fall on the grass the way the walls' do, and lying snow settles on whatever faces up. It is near
scenery: drawn once per keyframe, in foreground().

The year shows through season.py and through two stages that phase 5 will drive week by week (a garden
dug and planted, a wall rising stone by stone). Phase 3 sets them from the date alone:
`garden_stage(doy)` and `WallStage()` (a finished wall). Positions are fixed fractions of the frame
(LAYOUT and friends), so the same hillside is under every frame and every day; docs/v3/phase3-hillside.md
lists them in pixels of the 2880 x 1800 frame for the animals that will use them.
"""
import math
from dataclasses import dataclass

import numpy as np

from core import ALT_TOP, AZ_SPAN, CLOUD_SHADE, GLOW_COL, SKY_HOR, SKY_MID, SKY_ZEN, VH, keys, normalize, sm
from season import bump, ramp

MS = 72.0            # pixels per metre at a perspective of 1 on a 3840-wide frame (the tower's own scale)


# ------------------------------------------------------------------- stages --
@dataclass(frozen=True)
class GardenStage:
    """How far the garden's year has gone. Each field is 0..1 and the garden draws whatever it says,
    so a later phase can move them on day by day; `garden_stage` sets them from the date.

    The year's work in order: the beds are dug (bed by bed, front to back, each from left to right),
    sown or planted (potatoes, salads, beans, then the cabbages), grow, ripen, are cleared (salads,
    potatoes, beans; the cabbage bed stands through the winter as kale), and the cleared ground is dug
    over rough for the winter. A garden with nothing done yet (all 0) looks the same as one whose year
    is over (all 1): rough winter beds and the kale."""
    dug: float = 0.0
    sown: float = 0.0
    growth: float = 0.0
    ripe: float = 0.0
    cleared: float = 0.0
    rough: float = 0.0


@dataclass(frozen=True)
class WallStage:
    """How far a dry-stone wall is built: `courses` 0..4, three courses of stones and then the coping.
    A fraction builds the next course along the wall from its start, so a wall rising stone by stone is
    `courses` creeping up week by week. The stones are the same at every stage (they are drawn from the
    same draws and only shown when laid)."""
    courses: float = 4.0


def garden_stage(doy):
    """The garden's stage on a day of the year (phase 3: the date alone). The garden's year starts at
    the end of February with the first digging."""
    c = (doy - 50) % 365
    return GardenStage(dug=ramp(c, 0, 40),            # late February to the end of March
                       sown=ramp(c, 36, 116),         # April to mid June
                       growth=ramp(c, 44, 160),       # to the end of July
                       ripe=ramp(c, 165, 228),        # August to early October
                       cleared=ramp(c, 176, 262),     # mid August to early November
                       rough=ramp(c, 236, 286))       # October to late November


def gorse_bloom(doy):
    """Gorse flowers a little all year ("when gorse is out of bloom, kissing's out of season"), in a
    blaze from March to May, and again more thinly in the autumn."""
    return 0.10 + 0.90 * bump(doy, 40, 78, 138, 168) + 0.14 * bump(doy, 255, 282, 318, 345)


def heather_bloom(doy):
    """Ling heather is purple from late July to September, then rusty brown, dark through the winter."""
    return bump(doy, 200, 218, 252, 274)


def hive_tiers(doy):
    """The hives' boxes: two through the winter, a third in spring, a fourth (the honey super) in summer."""
    return 2 + (1 if 75 <= doy < 300 else 0) + (1 if 135 <= doy < 240 else 0)


def hive_wrapped(doy):
    """The hives are wrapped in tarred felt from mid November to early March."""
    return doy >= 318 or doy < 62


# ------------------------------------------------------------------- layout --
# Frame fractions (x of the width, y of the height). The garden is a quadrilateral on the ground: its
# front-left, front-right, back-left and back-right corners.
GARDEN = ((0.030, 0.688), (0.170, 0.694), (0.064, 0.641), (0.196, 0.646))
SHED_AB = (0.0, 0.29, 0.66, 0.99)          # the shed's footprint in the garden's (a, b) coordinates
BEDS = ((0.06, 0.18), (0.21, 0.33), (0.36, 0.48), (0.51, 0.63))   # b ranges, front to back
BED_A = (0.06, 0.94)
CROPS = ("cabbage", "potato", "salad", "bean")                      # bed by bed, front to back
DIG_ORDER = (3, 0, 1, 2)          # the order the beds are dug (each bed's place in it)
SOW_ORDER = (3, 0, 1, 2)          # potatoes, salads, beans, cabbages
CLEAR_ORDER = (None, 1, 0, 2)     # salads, potatoes, beans; the cabbages stand as winter kale
# the new dry-stone wall's stretches, each built as far as its WallStage says (garden-front runs from the
# garden's left corner to its wicket gate, garden-front-east from the gate to the right corner)
WALLS = ("garden-back", "garden-left", "garden-right", "garden-front", "garden-front-east")
HIVES_A = (0.62, 0.74, 0.86)      # along the back, right of the shed
HIVES_B = 0.82
GATE_GAP = 0.80, 0.90             # the garden's wicket gate: an a range in the front wall
# the field gate: hung on the post at the end of the upper wall, swung open toward you
FIELD_GATE = dict(hinge=(0.148, 0.812), latch=(0.196, 0.826), open_deg=108.0)
# rock outcrops: (x, y, width in px at scale 1 and perspective 1, seed)
OUTCROPS = ((0.040, 0.912, 150, 1), (0.392, 0.842, 120, 2))
# gorse: (x, y, width, height, seed): beside the outcrops, and below the garden's left corner
GORSE = ((0.085, 0.889, 96, 62, 1), (0.010, 0.932, 84, 56, 2), (0.432, 0.829, 82, 52, 3),
         (0.012, 0.703, 100, 62, 4), (0.224, 0.671, 96, 60, 5), (0.203, 0.657, 72, 46, 6))
# heather: (x, y, half width, half depth, seed)
HEATHER = ((0.020, 0.880, 64, 14, 1), (0.062, 0.958, 46, 11, 2), (0.360, 0.852, 60, 14, 3),
           (0.418, 0.858, 44, 10, 4), (0.236, 0.682, 40, 7, 5))
# wildflower patches: (x, y, half width, half depth, count, seed)
MEADOW = ((0.260, 0.905, 90, 22, 70, 1), (0.330, 0.800, 70, 14, 46, 2), (0.060, 0.835, 70, 14, 46, 3),
          (0.100, 0.708, 90, 7, 40, 4))
# puddles on the path: (along 0..1, across -1..1, size); and in hollows: (x, y, rx at scale 1)
PATH_PUDDLES = ((0.12, 0.40, 1.1), (0.31, 0.38, 1.1), (0.335, -0.40, 0.9), (0.52, 0.41, 0.8), (0.70, -0.40, 0.7))
HOLLOW_PUDDLES = ((0.170, 0.834, 30),)


def enc(n):
    n = normalize(n)
    return tuple(float(v) for v in (np.asarray(n) + 1) * 127.5)


UP = (0.0, -0.25, 0.97)          # the ground's own slope (it falls away toward the sea)
FRONT = (0.0, 0.97, 0.12)        # a face toward you
WEST = (-0.97, 0.18, 0.12)       # a face to your right (the oblique shows the right-hand sides)
OBJ = (0, 0, 255)                # the object mask: no grass shading here


class HillsideMixin:
    # ------------------------------------------------------------- helpers --
    def hs_persp(self, y):
        return 0.35 + 1.3 * min(1.0, max(0.0, (y / self.H - 0.6) / 0.4))

    def hs_m(self, y):
        """Pixels per metre at frame row y."""
        return MS * self.s * self.hs_persp(y)

    def hs_face(self, pts, alb, n, a=1.0, obj=True):
        A, N, X = self._hsA, self._hsN, self._hsX
        A.poly(pts, alb, a)
        N.poly(pts, enc(n), a)
        if obj:
            X.poly(pts, OBJ)

    def hs_ell(self, x, y, rx, ry, alb, n, a=1.0, obj=True):
        A, N, X = self._hsA, self._hsN, self._hsX
        A.ellipse(x, y, rx, ry, alb, a)
        N.ellipse(x, y, rx, ry, enc(n), a)
        if obj:
            X.ellipse(x, y, rx, ry, OBJ)

    def hs_line(self, pts, alb, n, w, obj=True):
        A, N, X = self._hsA, self._hsN, self._hsX
        A.line(pts, alb, w)
        N.line(pts, enc(n), w)
        if obj:
            X.line(pts, OBJ, w)

    def hs_cast(self, foot, h):
        """Something standing on foot (points on the ground) h px tall casts a shadow on the grass."""
        self._hs_casters.append(("poly", [tuple(map(float, p)) for p in foot], float(h)))

    def hs_cast_line(self, p0, p1, h0, h1, w):
        """A bar from ground point p0 at height h0 px to p1 at h1 casts a thin shadow."""
        self._hs_casters.append(("line", (float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1])), float(h0), float(h1), float(w)))

    # -------------------------------------------------------------- the hill --
    def hillside(self, A, N, X, WM, persp):
        """Draw everything into the hill's layers (A albedo, N normals, X: blue = no grass shading here,
        red/green = puddles and their wet rims; WM: where things stand, so they don't fall in their own
        shadow). Returns what casts shadows on the grass and where it darkens the grass at its foot."""
        self._hsA, self._hsN, self._hsX, self._hsWM = A, N, X, WM
        self._hs_casters, self._hs_feet = [], []
        se = self.season
        d = se.doy
        self.hs_puddles(persp)
        self.hs_heather(d)
        self.hs_meadows()
        for i, o in enumerate(OUTCROPS):
            self.hs_outcrop(*o)
        for g in GORSE:
            self.hs_gorse(*g, bloom=gorse_bloom(d))
        self.hs_garden(self.hs_garden_stage(), d)
        self.hs_field_gate(FIELD_GATE["open_deg"])
        return self._hs_casters, self._hs_feet

    # ------------------------------------------------------------ the garden --
    def hs_garden_stage(self):
        """The garden's stage today: the Day's own `garden_stage` (a GardenStage) if a later phase has
        set one, else what the date alone says."""
        st = getattr(self.day, "garden_stage", None)
        return st if isinstance(st, GardenStage) else garden_stage(self.season.doy)

    def hs_wall_stage(self, name):
        """How far the new wall stretch `name` (WALLS) is built today: the Day's own `wall_stages[name]`
        (a WallStage) if a later phase has set one, else finished."""
        st = (getattr(self.day, "wall_stages", None) or {}).get(name)
        return st if isinstance(st, WallStage) else WallStage()

    def hs_corners(self):
        W, H = self.W, self.H
        return [np.array((x * W, y * H), np.float64) for x, y in GARDEN]

    def hs_g(self, a, b, h=0.0):
        """A point of the garden: a across (0 left, 1 right), b back (0 front, 1 back), h metres up."""
        FL, FR, BL, BR = self.hs_corners()
        p = (1 - a) * (1 - b) * FL + a * (1 - b) * FR + (1 - a) * b * BL + a * b * BR
        return (float(p[0]), float(p[1] - h * self.hs_m(p[1])))

    def hs_garden(self, st, doy):
        g = self.hs_g
        rng = np.random.default_rng(301)
        # the ground inside: the hill's grass, mown short, worn to earth along the paths between the beds
        self.hs_face([g(0, 0), g(1, 0), g(1, 1), g(0, 1)], (92, 108, 58), UP, a=0.45, obj=False)
        worn = np.array((122, 108, 80), np.float32)
        for b_ in [0.03] + [(BEDS[i][1] + BEDS[i + 1][0]) / 2 for i in range(len(BEDS) - 1)] + [0.645]:
            self.hs_face([g(0.02, b_ - 0.016), g(0.98, b_ - 0.016), g(0.98, b_ + 0.016), g(0.02, b_ + 0.016)], worn, UP, a=0.6, obj=False)
        self.hs_face([g(0.94, 0.0), g(0.985, 0.0), g(0.985, 0.66), g(0.94, 0.66)], worn, UP, a=0.6, obj=False)
        # the back wall, behind everything, from the shed to the right-hand corner
        self.hs_wall("garden-back", [g(a_, 1.0) for a_ in np.linspace(SHED_AB[1] - 0.01, 1.0, 40)])
        # the back row: the hives, the shed
        tiers = hive_tiers(doy)
        for i, a_ in enumerate(HIVES_A[::-1]):
            self.hs_hive(*g(a_, HIVES_B), tiers, hive_wrapped(doy), np.random.default_rng(310 + i))
        self.hs_shed(rng)
        # the left wall, whose inner face you see, then the beds front to back over it
        self.hs_wall("garden-left", [g(0.0, b_) for b_ in np.linspace(0.0, SHED_AB[2] + 0.01, 30)])
        for k in range(len(BEDS) - 1, -1, -1):
            self.hs_bed(k, st, np.random.default_rng(320 + k))
        # the right wall (you see its outer face; it hides the garden behind it), then the front wall
        self.hs_wall("garden-right", [g(1.0, b_) for b_ in np.linspace(0.0, 1.0, 30)])
        a0, a1 = GATE_GAP
        self.hs_wall("garden-front", [g(a_, 0.0) for a_ in np.linspace(0.0, a0, 40)])
        self.hs_wall("garden-front-east", [g(a_, 0.0) for a_ in np.linspace(a1, 1.0, 10)])
        self.hs_wicket(g(a0, 0.0), g(a1, 0.0))

    def hs_wall(self, name, pts, height=1.25):
        """The new wall's stretch `name` (WALLS) along pts: land.py's stonework with its own stones, a
        quarter taller than the field walls (a garden wall), built as far as its WallStage says."""
        stage = self.hs_wall_stage(name)
        seg = np.array(pts, np.float64)
        persp = lambda y: 0.35 + 1.3 * np.clip((np.asarray(y) / self.H - 0.6) / 0.4, 0, 1)
        r2 = np.random.default_rng(360 + WALLS.index(name))
        self.wall_body(self._hsA, self._hsN, seg, persp, r2, self._hsWM, courses=stage.courses, height=height,
                       X=self._hsX)
        hgt = lambda y: 29 * self.s * float(persp(y)) * height * min(1.0, stage.courses / 4)
        if stage.courses <= 0:
            return
        for (xa, ya), (xb, yb) in zip(seg[:-1], seg[1:]):
            self._hs_casters.append(("wall", (xa, ya), (xb, yb), hgt(ya), hgt(yb), 0.0))
            self._hs_feet.append(((xa, ya), (xb, yb)))

    def hs_wicket(self, p0, p1):
        """A small wooden gate in the front wall's gap, shut."""
        k = self.hs_m(p0[1])
        h = 0.62 * k
        wood = np.array((128, 118, 100), np.float32)
        post = 0.07 * k
        for (x, y) in (p0, p1):          # posts
            self.hs_face([(x - post, y), (x + post, y), (x + post, y - h * 1.18), (x - post, y - h * 1.18)], wood * 0.8, FRONT)
            self.hs_face([(x - post, y - h * 1.18), (x + post, y - h * 1.18), (x + post * 0.6, y - h * 1.24), (x - post * 0.6, y - h * 1.24)], wood, UP)
        n = 7
        for i in range(n):              # pales
            t0, t1 = (i + 0.18) / n, (i + 0.82) / n
            xa, ya = p0[0] + (p1[0] - p0[0]) * t0, p0[1] + (p1[1] - p0[1]) * t0
            xb, yb = p0[0] + (p1[0] - p0[0]) * t1, p0[1] + (p1[1] - p0[1]) * t1
            top = h * (0.92 + 0.05 * math.sin(math.pi * (i + 0.5) / n))
            self.hs_face([(xa, ya - 0.04 * k), (xb, yb - 0.04 * k), (xb, yb - top), ((xa + xb) / 2, (ya + yb) / 2 - top - 0.05 * k), (xa, ya - top)],
                         wood * (0.92 + 0.12 * ((i * 7) % 3) / 2), FRONT)
        for f in (0.28, 0.72):          # rails behind the pales show between them
            self.hs_line([(p0[0], p0[1] - h * f), (p1[0], p1[1] - h * f)], wood * 0.7, FRONT, max(1.0, 0.05 * k), obj=True)
        self.hs_cast([p0, p1, (p1[0], p1[1] - 2), (p0[0], p0[1] - 2)], h)

    # ----------------------------------------------------------------- shed --
    def hs_shed(self, rng):
        """A timber garden shed in the garden's back corner: boarded walls, a slate roof, a door, a window,
        a water butt at its corner."""
        g = self.hs_g
        a0, a1, b0, b1 = SHED_AB
        bm = (b0 + b1) / 2
        he, hr, ov = 2.0, 2.85, 0.03          # eaves and ridge (metres), roof overhang (of the garden's a)
        boards = np.array((134, 122, 104), np.float32)
        trim = np.array((176, 170, 156), np.float32)
        slate = np.array((92, 96, 104), np.float32)
        # the back slope of the roof first: only its edge shows above the ridge
        self.hs_face([g(a0 - ov, bm, hr), g(a1 + ov, bm, hr), g(a1 + ov, b1 + 0.04, he - 0.1), g(a0 - ov, b1 + 0.04, he - 0.1)],
                     slate * 0.95, (0.0, -0.55, 0.83))
        # the gable end (west), boarded, lit by the evening sun
        gable = [g(a1, b0, 0), g(a1, b1, 0), g(a1, b1, he), g(a1, bm, hr), g(a1, b0, he)]
        self.hs_face(gable, boards * 0.96, WEST)
        for t in np.linspace(0.08, 0.92, 7):      # its boards, vertical
            b_ = b0 + (b1 - b0) * t
            hh = he + (hr - he) * (1 - abs(b_ - bm) / ((b1 - b0) / 2))
            self.hs_line([g(a1, b_, 0.02), g(a1, b_, hh - 0.04)], boards * 0.62, WEST, max(1.0, 0.6 * self.s))
        # the front wall: boards, a door and a window
        front = [g(a0, b0, 0), g(a1, b0, 0), g(a1, b0, he), g(a0, b0, he)]
        self.hs_face(front, boards, FRONT)
        for t in np.linspace(0.04, 0.96, 15):
            a_ = a0 + (a1 - a0) * t
            self.hs_line([g(a_, b0, 0.02), g(a_, b0, he - 0.02)], boards * rng.uniform(0.6, 0.7), FRONT, max(1.0, 0.6 * self.s))
        da0, da1 = a0 + (a1 - a0) * 0.16, a0 + (a1 - a0) * 0.40     # the door, painted the tower dome's green
        door = np.array((74, 112, 100), np.float32)
        self.hs_face([g(da0, b0, 0), g(da1, b0, 0), g(da1, b0, 1.78), g(da0, b0, 1.78)], door, FRONT)
        for t in (0.33, 0.66):
            a_ = da0 + (da1 - da0) * t
            self.hs_line([g(a_, b0, 0.04), g(a_, b0, 1.74)], door * 0.7, FRONT, max(1.0, 0.5 * self.s))
        self.hs_line([g(da0, b0, 0.35), g(da1, b0, 1.45)], door * 1.12, FRONT, max(1.0, 0.9 * self.s))   # the brace
        for hh in (0.35, 1.45):
            self.hs_line([g(da0, b0, hh), g(da1, b0, hh)], door * 1.08, FRONT, max(1.0, 1.0 * self.s))
        lx, ly = g(da1 - (da1 - da0) * 0.14, b0, 0.95)
        self.hs_ell(lx, ly, 1.2 * self.s, 1.2 * self.s, (30, 30, 32), FRONT)
        wa0, wa1 = a0 + (a1 - a0) * 0.56, a0 + (a1 - a0) * 0.86      # the window: four panes in a white frame
        wf = [g(wa0, b0, 0.95), g(wa1, b0, 0.95), g(wa1, b0, 1.72), g(wa0, b0, 1.72)]
        self.hs_face(wf, trim, FRONT)
        i0, i1 = wa0 + (wa1 - wa0) * 0.1, wa1 - (wa1 - wa0) * 0.1
        self.hs_face([g(i0, b0, 1.02), g(i1, b0, 1.02), g(i1, b0, 1.65), g(i0, b0, 1.65)], (40, 48, 58), FRONT)
        self.hs_face([g(i0, b0, 1.36), g(i1, b0, 1.36), g(i1, b0, 1.65), g(i0, b0, 1.65)], (62, 74, 88), (0.0, 0.7, 0.7))   # sky in the glass
        self.hs_line([g((i0 + i1) / 2, b0, 1.02), g((i0 + i1) / 2, b0, 1.65)], trim, FRONT, max(1.0, 0.8 * self.s))
        self.hs_line([g(i0, b0, 1.33), g(i1, b0, 1.33)], trim, FRONT, max(1.0, 0.8 * self.s))
        self.hs_face([g(wa0 - 0.01, b0, 0.9), g(wa1 + 0.01, b0, 0.9), g(wa1 + 0.012, b0, 0.95), g(wa0 - 0.012, b0, 0.95)], trim * 1.05, UP)  # sill
        # the front slope of the roof: slates in courses, a pale ridge, barge boards at the gable
        roof = [g(a0 - ov, b0 - 0.05, he - 0.12), g(a1 + ov, b0 - 0.05, he - 0.12), g(a1 + ov, bm, hr), g(a0 - ov, bm, hr)]
        rn = (0.0, 0.57, 0.82)
        self.hs_face(roof, slate, rn)
        for t in np.linspace(0.15, 0.9, 5):
            bb, hh = (b0 - 0.05) + (bm - b0 + 0.05) * t, (he - 0.12) + (hr - he + 0.12) * t
            self.hs_line([g(a0 - ov, bb, hh), g(a1 + ov, bb, hh)], slate * 0.78, rn, max(1.0, 0.6 * self.s))
        for i in range(10):
            a_ = a0 - ov + (a1 - a0 + 2 * ov) * rng.uniform(0.02, 0.98)
            t = rng.uniform(0.05, 0.9)
            bb, hh = (b0 - 0.05) + (bm - b0 + 0.05) * t, (he - 0.12) + (hr - he + 0.12) * t
            x, y = g(a_, bb, hh)
            self.hs_ell(x, y, rng.uniform(2, 5) * self.s, 1.0 * self.s, slate * rng.choice([0.85, 1.15]) + np.array((8, 10, 0)), rn)
        self.hs_line([g(a0 - ov, bm, hr), g(a1 + ov, bm, hr)], slate * 1.25, (0.0, 0.1, 1.0), max(1.0, 1.4 * self.s))
        self.hs_line([g(a1 + ov, b0 - 0.05, he - 0.12), g(a1 + ov, bm, hr)], trim * 0.82, WEST, max(1.2, 1.6 * self.s))
        self.hs_line([g(a1 + ov, bm, hr), g(a1 + ov, b1 + 0.04, he - 0.1)], trim * 0.7, WEST, max(1.2, 1.4 * self.s))
        self.hs_line([g(a0 - ov, b0 - 0.05, he - 0.12), g(a1 + ov, b0 - 0.05, he - 0.12)], slate * 0.6, FRONT, max(1.0, 0.8 * self.s))
        # a water butt at the front corner: a wooden barrel with iron hoops
        bx, by = g(a1 + 0.035, b0 + 0.03)
        k = self.hs_m(by)
        r, hb = 0.32 * k, 0.9 * k
        oak = np.array((104, 80, 56), np.float32)
        for j, e in enumerate((0.75, 0.25, -0.25, -0.75)):     # four staves, each lit as it faces
            xa, xb = bx - r + 2 * r * j / 4, bx - r + 2 * r * (j + 1) / 4
            bulge = 0.06 * r * (1 if 0 < j < 3 else 0)
            self.hs_face([(xa - bulge, by), (xb + bulge, by), (xb + bulge, by - hb), (xa - bulge, by - hb)], oak * (0.95 + 0.05 * j % 2), (e, 0.62, 0.1))
        for f in (0.15, 0.85):
            self.hs_line([(bx - r * 1.04, by - hb * f), (bx + r * 1.04, by - hb * f)], (52, 50, 50), FRONT, max(1.0, 0.8 * self.s))
        self.hs_ell(bx, by - hb, r, r * 0.3, (40, 44, 50), (0.0, 0.0, 1.0))          # water, under the sky
        self.hs_cast([(bx - r, by), (bx + r, by), (bx, by - r * 0.4)], hb)
        # its shadow and its foot
        foot = [g(a0, b0), g(a1, b0), g(a1, b1), g(a0, b1)]
        self._hs_casters.append(("box", foot, [g(a0, b0, he), g(a1, b0, he), g(a1, b1, he), g(a0, b1, he),
                                               g(a0, bm, hr), g(a1, bm, hr)]))
        self._hs_feet.append((foot[0], foot[1]))
        self._hs_feet.append((foot[1], foot[2]))
        self._hsWM.poly([g(a0 - ov, b0, 0), g(a1 + ov, b0, 0), g(a1 + ov, b1, 0), g(a1 + ov, bm, hr), g(a0 - ov, bm, hr)], (255, 255, 255))

    # ----------------------------------------------------------------- hives --
    def hs_hive(self, x, y, tiers, wrapped, rng):
        """A white WBC hive on its stand: legs, a floor with a landing board, stepped lifts, a gabled roof
        whose gable faces you. In the winter its lifts are wrapped in tarred felt and a stone holds the roof."""
        k = self.hs_m(y)
        s = self.s
        w, dp = 0.58 * k, 0.16 * k            # half width; the depth the oblique shows
        dx, dy = dp * 0.9, -dp * 0.75        # going back one depth
        paint = np.array((226, 224, 214), np.float32)
        felt = np.array((48, 46, 44), np.float32)
        leg = 0.24 * k
        for lx in (-0.8, 0.8):
            self.hs_line([(x + lx * w * 0.5 + dx, y + dy), (x + lx * w * 0.5 + dx, y + dy - leg)], (60, 56, 50), FRONT, max(1.0, 0.07 * k))
            self.hs_line([(x + lx * w * 0.5, y), (x + lx * w * 0.5, y - leg)], (70, 64, 56), FRONT, max(1.0, 0.07 * k))
        yb = y - leg
        # the floor and its landing board
        self.hs_face([(x - w * 0.62, yb + 0.05 * k), (x + w * 0.62, yb + 0.05 * k), (x + w * 0.55, yb - 0.04 * k), (x - w * 0.55, yb - 0.04 * k)],
                     paint * 0.9, (0.0, 0.6, 0.8))
        yy = yb - 0.04 * k
        th = 0.2 * k
        for t in range(tiers):
            ww = w * (0.5 if t == 0 else 0.53)
            col = felt if wrapped else paint * (0.97 + 0.03 * (t % 2))
            # the right side of the lift, then its front, flared a little at the foot
            self.hs_face([(x + ww, yy), (x + ww + dx, yy + dy), (x + ww + dx, yy + dy - th), (x + ww, yy - th)], col, WEST)
            self.hs_face([(x - ww * 1.06, yy), (x + ww * 1.06, yy), (x + ww, yy - th), (x - ww, yy - th)], col, FRONT)
            self.hs_line([(x - ww * 1.06, yy - 0.5), (x + ww * 1.06, yy - 0.5)], col * 0.72, (0.0, 0.5, -0.8), max(1.0, 0.4 * s))
            if t == 0:                    # the entrance, a dark slit (narrowed for the winter)
                ew = ww * (0.35 if wrapped else 0.7)
                self.hs_face([(x - ew, yy - 0.01 * k), (x + ew, yy - 0.01 * k), (x + ew, yy - 0.05 * k), (x - ew, yy - 0.05 * k)], (24, 22, 20), FRONT)
            if wrapped:                   # the felt is tied with twine
                self.hs_line([(x - ww, yy - th * 0.5), (x + ww, yy - th * 0.5)], (120, 108, 84), FRONT, max(1.0, 0.4 * s))
            yy -= th
        # the roof: its gable facing you, its slopes going back
        rw = w * 0.66
        rh = 0.24 * k
        self.hs_face([(x, yy - rh), (x + dx, yy - rh + dy), (x + rw + dx, yy + dy), (x + rw, yy)], paint * 0.95, (-0.6, 0.0, 0.8))
        self.hs_face([(x - rw, yy), (x + rw, yy), (x, yy - rh)], paint, FRONT)
        self.hs_face([(x - rw, yy), (x, yy - rh), (x + dx, yy - rh + dy), (x - rw + dx, yy + dy)], paint * 0.97, (0.6, 0.3, 0.75))
        self.hs_line([(x - rw * 1.05, yy + 0.3), (x + rw * 1.05, yy + 0.3)], paint * 0.7, FRONT, max(1.0, 0.5 * s))
        if wrapped:                       # a stone on the roof against the winter gales
            self.hs_ell(x + dx * 0.5, yy - rh * 0.7 + dy * 0.5, 0.11 * k, 0.07 * k, (120, 116, 108), (0.0, 0.4, 0.9))
        foot = [(x - w * 0.6, y), (x + w * 0.6, y), (x + w * 0.6 + dx, y + dy), (x - w * 0.6 + dx, y + dy)]
        self.hs_cast(foot, y - (yy - rh))
        self._hsWM.poly([(x - w * 0.7, y + 1), (x + w * 0.7 + dx, y + 1), (x + w * 0.7 + dx, yy - rh + dy), (x - w * 0.7, yy - rh)], (255, 255, 255))

    # ------------------------------------------------------------------ beds --
    # Every draw below is made whatever the stage, and only what the stage says is shown, so the same
    # clods and plants stand in the same places from one day to the next as a later phase moves the
    # stage on (each bed and each crop has its own generator).
    def hs_bed(self, k, st, rng):
        """Bed k: a raised bed edged with boards, its soil as the year has left it, its crop in rows."""
        g = self.hs_g
        b0, b1 = BEDS[k]
        a0, a1 = BED_A
        lift = 0.12
        crop = CROPS[k]
        board = np.array((112, 96, 74), np.float32)
        n = 24
        dig = float(np.clip(st.dug * 4 - DIG_ORDER[k], 0, 1))
        sow = float(np.clip(st.sown * 4 - SOW_ORDER[k], 0, 1))
        order = CLEAR_ORDER[k]
        rough_a = float(np.clip(st.rough * 3 - order, 0, 1)) if order is not None else 0.0
        clr = float(np.clip(st.cleared * 3 - order, 0, 1)) if order is not None else 0.0
        fine = np.array((86, 64, 46), np.float32)       # fresh tilth, dark
        settled = np.array((112, 92, 70), np.float32)
        settle = sm(0.15, 0.6, st.growth)
        # the soil, in strips along the bed: rough where it lies over the winter (not yet dug this year, or
        # dug over after clearing), fresh dark tilth where just dug, settling as the crop grows
        for i in range(n):
            f0, f1 = i / n, (i + 1) / n
            fa, fb = a0 + (a1 - a0) * f0, a0 + (a1 - a0) * f1
            fm = (f0 + f1) / 2
            dug_here = fm < dig
            if order is None:             # the cabbage bed: kale stands on it through the winter
                rough_here = False
                col = settled * 0.92 if not dug_here else fine * (1 - settle) + settled * 0.92 * settle
            else:
                rough_here = (not dug_here) or (fm < rough_a)
                col = settled * 0.92 if rough_here else fine * (1 - settle) + settled * settle
            tone = rng.uniform(0.95, 1.05)
            self.hs_face([g(fa, b0, lift), g(fb, b0, lift), g(fb, b1, lift), g(fa, b1, lift)], col * tone, UP)
            for _ in range(5):            # winter clods, turned up in ridges
                a_, b_ = rng.uniform(fa, fb), rng.uniform(b0 + 0.01, b1 - 0.01)
                rx, ry, c, nx, ny = rng.uniform(0.07, 0.14), rng.uniform(0.04, 0.07), rng.uniform(0.75, 1.15), rng.normal(0, 0.4), rng.uniform(0.0, 0.7)
                if rough_here:
                    x, y = g(a_, b_, lift)
                    m = self.hs_m(y)
                    self.hs_ell(x, y, rx * m, ry * m, settled * c, (nx, ny, 0.7))
        # the board along the front, catching the sky on its top edge
        self.hs_face([g(a0, b0, 0), g(a1, b0, 0), g(a1, b0, lift), g(a0, b0, lift)], board, FRONT)
        self.hs_line([g(a0, b0, lift), g(a1, b0, lift)], board * 1.2, UP, max(1.0, 0.7 * self.s))
        self.hs_face([g(a1, b0, 0), g(a1, b1, 0), g(a1, b1, lift), g(a1, b0, lift)], board * 0.9, WEST)
        # the crop
        crng = np.random.default_rng(330 + k)
        lag = SOW_ORDER[k] * 0.12
        gr = float(np.clip((st.growth - lag) / (1 - lag), 0, 1))
        if crop == "cabbage":
            if sow <= 0:                  # last year's kale, until the bed is dug
                self.hs_kale(k, 1.0, dig, 1.0, crng)
            else:
                self.hs_kale(k, max(gr, 0.05), 0.0, sow, crng, young=st.ripe < 0.5)
        elif sow > 0 and crop in ("potato", "salad"):
            self.hs_rows(k, crng, sow, clr, gr, st.ripe, crop)
        elif sow > 0:
            self.hs_beans(k, crng, sow, clr, gr, st.ripe)

    def hs_kale(self, k, gr, f0, f1, rng, young=False):
        """Cabbages, which stand through the winter as kale: round blue-green heads in two rows, from f0 to
        f1 along the bed."""
        g = self.hs_g
        b0, b1 = BEDS[k]
        a0, a1 = BED_A
        blue = np.array((76, 106, 90), np.float32) if young else np.array((62, 88, 74), np.float32)
        for row in (0.68, 0.3):
            b_ = b0 + (b1 - b0) * row
            for f in np.arange(0.03, 1.0, 0.045):
                jit, sz, tone = rng.normal(0, 0.006), rng.uniform(0.85, 1.1), rng.uniform(0.95, 1.12)
                if not (f0 <= f <= f1):
                    continue
                x, y = g(a0 + (a1 - a0) * (f + jit), b_, 0.12)
                m = self.hs_m(y)
                r = (0.13 + 0.13 * gr) * m * sz
                hgt = r * (0.9 if young else 1.6)
                self.hs_ell(x, y - hgt * 0.5, r, hgt * 0.62, blue * 0.82, FRONT)
                self.hs_ell(x - r * 0.15, y - hgt * 0.7, r * 0.72, hgt * 0.42, blue * tone, (0.1, 0.4, 0.9))
                if not young:              # kale's frilled leaves
                    for e in (-1, 1):
                        self.hs_ell(x + e * r * 0.7, y - hgt * 0.8, r * 0.38, r * 0.3, blue * 1.05, (-0.6 * e, 0.3, 0.75))

    def hs_rows(self, k, rng, sow, clear, gr, ripe, kind):
        """Potatoes (a row of leafy mounds, white-flowered in high summer) or salads (lettuces, and carrots
        between them), sown from the left as far as `sow`, cleared from the left as far as `clear`."""
        g = self.hs_g
        b0, b1 = BEDS[k]
        a0, a1 = BED_A
        if kind == "potato":
            green = np.array((70, 108, 50), np.float32) * (1 - 0.55 * ripe) + np.array((150, 128, 70), np.float32) * 0.55 * ripe
            rows, step, size = (0.5,), 0.05, 0.28
        else:
            green = np.array((112, 150, 70), np.float32) * (1 - 0.4 * ripe) + np.array((140, 130, 70), np.float32) * 0.4 * ripe
            rows, step, size = (0.72, 0.42, 0.14), 0.03, 0.12
        for ri, row in enumerate(rows):
            b_ = b0 + (b1 - b0) * row
            for f in np.arange(0.02 + 0.01 * ri, 1.0, step):
                sz, tone, fl, fx = rng.uniform(0.8, 1.15), rng.uniform(0.95, 1.1), rng.random(), rng.normal(0, 0.4)
                if f > sow or f < clear:
                    continue
                x, y = g(a0 + (a1 - a0) * f, b_, 0.12)
                m = self.hs_m(y)
                r = max(0.4 * self.s, (0.03 + size * gr) * m * sz)
                if kind == "potato":
                    self.hs_ell(x, y - r * 0.5, r, r * 0.75, green * 0.8, FRONT)
                    self.hs_ell(x - r * 0.1, y - r * 0.8, r * 0.75, r * 0.5, green * tone, (0.0, 0.3, 0.95))
                    if gr > 0.75 and ripe < 0.3 and fl < 0.35:     # flowers in high summer
                        self.hs_ell(x + fx * r, y - r * 1.1, 0.6 * self.s, 0.6 * self.s, (232, 228, 236), UP)
                elif ri == 1:              # carrots: feathery tops
                    for e in (-1, 0, 1):
                        self.hs_line([(x, y), (x + e * r * 0.5, y - r * 1.6)], green * 0.75, (e * -0.4, 0.4, 0.8), max(1.0, 0.5 * self.s))
                else:                      # lettuces: a pale rosette
                    self.hs_ell(x, y - r * 0.4, r, r * 0.55, green * tone, (0.0, 0.35, 0.94))

    def hs_beans(self, k, rng, sow, clear, gr, ripe):
        """Runner beans up wigwams of hazel poles; the poles stand from sowing until the bed is cleared."""
        g = self.hs_g
        b0, b1 = BEDS[k]
        a0, a1 = BED_A
        pole = np.array((150, 128, 92), np.float32)
        leaf = np.array((58, 100, 46), np.float32) * (1 - 0.6 * ripe) + np.array((120, 96, 56), np.float32) * 0.6 * ripe
        bm = (b0 + b1) / 2
        for f in (0.12, 0.30, 0.48, 0.66, 0.84):
            tones = rng.uniform(0.85, 1.1, 4)
            vines = [(rng.uniform(0, 1), int(rng.integers(0, 4)), rng.normal(0, 0.06), rng.uniform(0.8, 1.15), rng.normal(0, 0.5), rng.random())
                     for _ in range(60)]
            if f > sow + 0.05 or f < clear:
                continue
            cx, cy = g(a0 + (a1 - a0) * f, bm, 0.12)
            m = self.hs_m(cy)
            top = (cx, cy - 2.1 * m)
            feet = [(cx - 0.32 * m, cy + 0.03 * m), (cx + 0.32 * m, cy + 0.02 * m), (cx - 0.12 * m, cy - 0.06 * m), (cx + 0.18 * m, cy - 0.07 * m)]
            for j, (fx, fy) in sorted(enumerate(feet), key=lambda q: q[1][1]):
                self.hs_line([(fx, fy), (top[0] + (fx - cx) * 0.06, top[1])], pole * tones[j], (0.0, 0.7, 0.5), max(1.0, 0.035 * m))
                self.hs_cast_line((fx, fy), (fx, fy), 0, 2.1 * m, 0.035 * m)
            if gr > 0.05:                  # the vines climb the poles, leaf by leaf
                hgt = 2.0 * m * min(1.0, gr * 1.15)
                for t, j, jx, tone, nx, fl in vines[:int(60 * min(1.0, gr * 1.3))]:
                    fx, fy = feet[j]
                    u = t * hgt / (2.1 * m)
                    x, y = fx + (top[0] - fx) * u + jx * m, fy + (top[1] - fy) * u
                    self.hs_ell(x, y, 0.11 * m, 0.085 * m, leaf * tone, (nx, 0.6, 0.6))
                    if 0.55 < gr and ripe < 0.6 and fl < 0.18:         # scarlet flowers
                        self.hs_ell(x + 0.05 * m, y - 0.03 * m, 0.035 * m, 0.035 * m, (196, 52, 40), FRONT)

    # ------------------------------------------------------------ field gate --
    def hs_field_gate(self, open_deg):
        """A five-barred wooden gate hung on a stone post at the end of the upper wall, standing open, swung
        back toward you into the field; its latch post stands at the end of the lower wall."""
        W, H, s = self.W, self.H, self.s
        hx, hy = FIELD_GATE["hinge"][0] * W, FIELD_GATE["hinge"][1] * H
        lx, ly = FIELD_GATE["latch"][0] * W, FIELD_GATE["latch"][1] * H
        KF = 0.30
        # the closed leaf in ground terms (across, toward you), swung toward you by open_deg
        gx, gz = lx - hx, (ly - hy) / KF
        L = math.hypot(gx, gz) * 0.92
        phi = math.atan2(gz, gx) + math.radians(open_deg)
        ux, uz = math.cos(phi), math.sin(phi)
        ex, ey = hx + L * ux, hy + L * uz * KF          # the latch end of the leaf, on the screen
        n_face = (uz * 0.35, abs(ux) * 0.9 + 0.2, 0.15)      # facing you, a little toward the open side
        per = lambda y: 26 * s * (0.35 + 1.3 * min(1.0, max(0.0, (y / H - 0.6) / 0.4)))
        hgt0, hgt1 = per(hy) * 1.18, per(ey) * 1.18
        wood = np.array((156, 150, 136), np.float32)
        # the latch post first (it is the farther), then the leaf, then the post it hangs on
        self.hs_gate_post(lx, ly, per(ly), 1)
        self.hs_gate_leaf(hx, hy, ex, ey, hgt0, hgt1, wood, n_face)
        iron = (36, 34, 34)
        for f in (0.22, 0.8):             # the hinges' straps
            self.hs_line([(hx, hy - hgt0 * f), (hx + (ex - hx) * 0.14, hy + (ey - hy) * 0.14 - hgt0 * f)], iron, n_face, max(1.0, 0.9 * s))
        self.hs_gate_post(hx, hy, per(hy), 2)
        rng = np.random.default_rng(345)
        for _ in range(14):               # grass grown up round the bottom rail
            t = rng.uniform(0.05, 1)
            x, y = hx + (ex - hx) * t, hy + (ey - hy) * t + rng.uniform(0.5, 3) * s
            self.tuft(self._hsA, self._hsN, x, y, rng.uniform(5, 9) * s, rng, np.array((52, 84, 36)), np.array((104, 124, 58)))

    def hs_gate_post(self, px, py, wall_h, seed):
        """A squared stone gatepost at a wall's end, half as tall again as the wall, lichened."""
        stone = np.array((132, 128, 118), np.float32)
        ph, pw = wall_h * 1.5, wall_h * 0.24
        self.hs_face([(px - pw, py + 1), (px + pw, py + 1), (px + pw * 0.92, py - ph), (px - pw * 0.9, py - ph)], stone * 0.92, FRONT)
        self.hs_face([(px + pw, py + 1), (px + pw * 1.5, py - pw * 0.3), (px + pw * 1.4, py - ph - pw * 0.3), (px + pw * 0.92, py - ph)],
                     stone * 0.8, WEST)
        self.hs_face([(px - pw * 0.9, py - ph), (px + pw * 0.92, py - ph), (px + pw * 1.4, py - ph - pw * 0.3), (px - pw * 0.4, py - ph - pw * 0.35)],
                     stone * 1.15, (0.0, 0.2, 0.98))
        rng = np.random.default_rng(340 + seed)
        for _ in range(4):                # lichen
            self.hs_ell(px + rng.uniform(-0.7, 0.7) * pw, py - rng.uniform(0.2, 0.9) * ph, pw * 0.25, pw * 0.15, (150, 150, 96), FRONT)
        self.hs_cast([(px - pw, py), (px + pw * 1.5, py), (px + pw * 1.5, py - pw * 0.3), (px - pw, py - pw * 0.3)], ph)
        self._hsWM.poly([(px - pw * 1.1, py + 2), (px + pw * 1.6, py + 2), (px + pw * 1.6, py - ph - pw), (px - pw * 1.1, py - ph - pw)], (255, 255, 255))

    def hs_gate_leaf(self, hx, hy, ex, ey, h0, h1, wood, n):
        s = self.s
        P = lambda t, f: (hx + (ex - hx) * t, hy + (ey - hy) * t - (h0 + (h1 - h0) * t) * f)
        w = max(1.4, 2.3 * s)
        # rails: five, closer together near the bottom, the top one stoutest
        for f, ww in ((0.08, 1.0), (0.26, 1.0), (0.45, 1.0), (0.66, 1.0), (0.93, 1.5)):
            self.hs_line([P(0.0, f), P(1.0, f)], wood * (1.0 if f < 0.9 else 1.08), n, w * ww)
            self.hs_line([P(0.02, f + 0.035), P(0.98, f + 0.035)], wood * 1.22, (0.0, 0.3, 0.95), max(1.0, 0.5 * s))   # its top takes the sky
            self.hs_cast_line(P(0.0, 0.0), P(1.0, 0.0), (h0) * f, (h1) * f, w * ww)
        # the stiles and the brace, from the foot of the hanging stile up to the top of the latch end
        self.hs_line([P(0.0, 0.0), P(0.0, 1.0)], wood * 0.92, n, w * 1.7)
        self.hs_line([P(1.0, 0.0), P(1.0, 0.98)], wood * 0.95, n, w * 1.2)
        self.hs_line([P(0.03, 0.06), P(0.62, 0.92)], wood * 0.9, n, w * 1.1)
        self.hs_line([P(0.5, 0.06), P(0.5, 0.94)], wood * 0.9, n, w * 0.9)
        self.hs_cast_line(P(0.0, 0.0), P(0.0, 0.0), 0, h0, w * 1.7)
        self.hs_cast_line(P(1.0, 0.0), P(1.0, 0.0), 0, h1, w * 1.2)
        self._hsWM.poly([P(0.0, -0.1), P(1.0, -0.1), P(1.0, 1.1), P(0.0, 1.1)], (255, 255, 255))

    # ------------------------------------------------------------- outcrops --
    def hs_rock(self, cx, cy, rx, ry, rng, alb, shadow=0.45):
        """A faceted stone (land.py's rock(), from its own draws), marked in X so the grass doesn't shade
        it. Returns its outline."""
        k = int(rng.integers(7, 11))
        ang = (np.arange(k) + rng.uniform(-0.3, 0.3, k)) / k * 2 * np.pi + rng.uniform(0, 6.28)
        rad = rng.uniform(0.78, 1.0, k)
        outer = [(cx + rx * r_ * math.cos(a_), cy + ry * r_ * math.sin(a_) * (0.8 if math.sin(a_) > 0 else 1.0)) for a_, r_ in zip(ang, rad)]
        tcx, tcy = cx + rng.normal(0, 0.12) * rx, cy - 0.32 * ry
        top = rng.uniform(0.38, 0.58)
        inner = [(tcx + top * (x - cx), tcy + top * 0.8 * (y - cy)) for x, y in outer]
        alb = np.asarray(alb, np.float32)
        if shadow:
            self._hsA.ellipse(cx, cy + 0.55 * ry, rx * 1.08, ry * 0.45, (20, 22, 18), a=shadow)
        self.hs_face(outer, alb * 0.75, (0, 0.85, 0.25))
        for i in range(k):
            j = (i + 1) % k
            am = (ang[i] + ang[j] + (2 * np.pi if j == 0 else 0)) / 2
            n = (-math.cos(am) * 0.72, math.sin(am) * 0.72, 0.6)
            self.hs_face([outer[i], outer[j], inner[j], inner[i]], alb * rng.uniform(0.84, 1.1), n)
        self.hs_face(inner, alb * 1.08, (rng.normal(0, 0.12), 0.22 + rng.normal(0, 0.1), 0.95))
        return outer, inner

    def hs_outcrop(self, xf, yf, wpx, seed):
        """Rock breaking through the turf: a broad, low shelf and a few boulders heaved up beside it, grey
        and weathered, with cracks, lichen on their tops, and grass grown up round their feet."""
        W, H, s = self.W, self.H, self.s
        rng = np.random.default_rng(350 + seed)
        x0, y0 = xf * W, yf * H
        p = self.hs_persp(y0)
        wide = wpx * s * p
        base = np.array((128, 124, 114), np.float32)
        lichen = [np.array((150, 150, 96), np.float32), np.array((196, 150, 70), np.float32), np.array((176, 178, 166), np.float32)]
        self._hsA.ellipse(x0, y0 + 0.01 * wide, wide * 0.62, wide * 0.09, (28, 34, 22), a=0.32)
        stones = []
        for i, (dx_, rx_, tall) in enumerate(((-0.16, 0.22, 0.9), (0.12, 0.19, 1.05), (0.33, 0.12, 0.8))):   # the crag
            rx = wide * rx_ * rng.uniform(0.9, 1.1)
            ry = rx * tall * rng.uniform(0.85, 1.05)
            stones.append((x0 + dx_ * wide, y0 - 0.42 * ry + rng.uniform(-0.02, 0.0) * wide, rx, ry))
        stones.append((x0 - 0.02 * wide, y0 + 0.015 * wide, wide * 0.36, wide * 0.1))              # a low shelf in front
        for i in range(4):                                                                          # loose stones
            side = (-1) ** i
            r_ = wide * rng.uniform(0.035, 0.06)
            stones.append((x0 + side * rng.uniform(0.38, 0.55) * wide, y0 + rng.uniform(-0.01, 0.03) * wide, r_, r_ * 0.6))
        for cx, cy, rx, ry in sorted(stones, key=lambda t: t[1] + t[3]):
            c = base * rng.uniform(0.86, 1.1)
            outer, inner = self.hs_rock(cx, cy, rx, ry, rng, c, shadow=0.0)
            if rx < wide * 0.08:
                continue
            for _ in range(int(rng.integers(1, 3))):      # a crack, down from the top
                t0 = int(rng.integers(0, len(inner)))
                xa, ya = inner[t0]
                self.hs_line([(xa, ya), (xa + rng.normal(0, 0.12) * rx, ya + ry * rng.uniform(0.4, 0.7))], c * 0.5, (0, 0.8, 0.3), max(1.0, 0.7 * s))
            for _ in range(int(rng.integers(2, 6))):      # lichen on the tops
                lx_ = np.mean([x for x, _ in inner]) + rng.normal(0, 0.25) * rx
                ly_ = np.mean([y for _, y in inner]) + rng.normal(0, 0.15) * ry
                self.hs_ell(lx_, ly_, rx * rng.uniform(0.06, 0.12), ry * rng.uniform(0.05, 0.1), lichen[int(rng.integers(0, 3))], (0.0, 0.2, 0.97))
        self.hs_cast([(x0 - 0.3 * wide, y0), (x0 + 0.4 * wide, y0), (x0 + 0.1 * wide, y0 - 0.05 * wide)], wide * 0.28)
        for _ in range(int(14 + wide / (5 * s))):         # turf grown up round the foot and between the stones
            a_ = rng.uniform(-0.55, 0.55)
            x = x0 + a_ * wide
            y = y0 + rng.uniform(0.02, 0.1) * wide * (1 - (1.6 * a_) ** 2) ** 0.5 if abs(a_) < 0.6 else y0
            self.tuft(self._hsA, self._hsN, x, y, rng.uniform(5, 11) * s * p, rng, np.array((52, 84, 36)), np.array((104, 124, 58)))

    # ---------------------------------------------------------------- gorse --
    def hs_gorse(self, xf, yf, wpx, hpx, seed, bloom):
        """A gorse bush: a mound of dark, spiny lobes bristling past its outline, its tops a little paler
        where they face the sky, flecked with yellow as the season says."""
        W, H, s = self.W, self.H, self.s
        rng = np.random.default_rng(370 + seed)
        x0, y0 = xf * W, yf * H
        p = self.hs_persp(y0)
        w, h = wpx * s * p, hpx * s * p
        dark = np.array((40, 58, 32), np.float32)
        mid = np.array((70, 94, 46), np.float32)
        yel = np.array((236, 196, 50), np.float32)
        self._hsA.ellipse(x0, y0, w * 0.56, w * 0.08, (24, 28, 18), a=0.4)
        lobes = []
        for i in range(9):               # irregular lobes: a few sprays stand up above the mound
            u = (i + rng.uniform(-0.35, 0.35)) / 8.0 - 0.5
            r = rng.uniform(0.11, 0.25) * w * (1 - 0.5 * u * u)
            ly = y0 - r * 0.8 - rng.uniform(0.15, 1.0) * max(0.0, h - 1.2 * r) * (1 - 2.2 * u * u)
            lobes.append((ly, x0 + u * w * 0.84, r))
        lobes.sort()
        for ly, lx, r in lobes:
            self.hs_ell(lx, ly, r, r * 0.86, dark * rng.uniform(0.9, 1.1), (0.0, 0.6, 0.75))
            n = int(min(80, 20 * r / (5 * s * p)))
            for _ in range(n):            # spines, bristling past the lobe's edge
                t = rng.uniform(-math.pi, math.pi * 0.15)
                rr = r * rng.uniform(0.55, 1.0)
                x, y = lx + math.cos(t) * rr, ly + math.sin(t) * rr * 0.86
                ln = rng.uniform(1.5, 3.2) * s * p
                dxn, dyn = math.cos(t) * 0.8, math.sin(t) * 0.8 - 0.35
                up = max(0.0, -dyn)
                c = (mid * (1.0 + 0.35 * up) if rng.random() < 0.55 + 0.4 * up else dark * 0.85) * rng.uniform(0.85, 1.15)
                self.hs_line([(x, y), (x + dxn * ln, y + dyn * ln)], c, (-dxn * 0.6, 0.3 - dyn * 0.2, 0.3 + up), max(1.0, 0.6 * s), obj=False)
            nf = int(16 * bloom * (r / (5 * s * p)) ** 1.5)
            for _ in range(nf):           # flowers, mostly on the top
                t = rng.uniform(-math.pi * 0.95, -math.pi * 0.05)
                rr = r * rng.uniform(0.2, 1.0)
                fr = rng.uniform(0.7, 1.25) * s * p
                self.hs_ell(lx + math.cos(t) * rr, ly + math.sin(t) * rr * 0.86, fr, fr * 0.8, yel * rng.uniform(0.9, 1.06),
                            (math.cos(t) * -0.3, 0.3, 0.9))
        self.hs_cast([(x0 - w * 0.45, y0), (x0 + w * 0.45, y0), (x0, y0 - w * 0.12)], h * 0.85)

    # -------------------------------------------------------------- heather --
    def hs_heather(self, doy):
        """Low, wiry mats of ling heather by the outcrops and on the poorer ground: dark green most of the
        year with paler new tips in early summer, purple from late July, its dead flowers rusty after. Each
        mat is a thicket of short, stiff sprigs, thinning out at its ragged edge into the grass."""
        W, H, s = self.W, self.H, self.s
        bl = heather_bloom(doy)
        rust = bump(doy, 262, 285, 340, 365 + 60)
        tips = bump(doy, 120, 140, 175, 200)
        green = np.array((70, 84, 50), np.float32)
        rustc = np.array((140, 98, 70), np.float32)
        purple = np.array((166, 106, 170), np.float32)
        spring = np.array((112, 136, 70), np.float32)
        for (xf, yf, rx, ry, seed) in HEATHER:
            rng = np.random.default_rng(390 + seed)
            x0, y0 = xf * W, yf * H
            p = self.hs_persp(y0)
            rx_, ry_ = rx * s * p, ry * s * p
            lobes = [(rng.uniform(-0.6, 0.6), rng.uniform(-0.4, 0.4), rng.uniform(0.35, 0.6)) for _ in range(4)]
            pts = []
            for _ in range(int(rx * ry * 1.6)):
                u, v = rng.uniform(-1, 1), rng.uniform(-1, 1)
                inside = max(1 - ((u - lu) ** 2 + (v - lv) ** 2) / lr ** 2 for lu, lv, lr in lobes)
                if rng.random() > inside * 1.6:     # thins out to a ragged edge
                    continue
                pts.append((v, u, inside))
            pts.sort()                               # back to front
            for v, u, inside in pts:
                x, y = x0 + u * rx_, y0 + v * ry_
                r = rng.uniform(0.9, 1.5) * s * p
                hh = rng.uniform(3.0, 6.5) * s * p * (0.5 + 0.5 * min(1, inside * 1.5))
                c = green * rng.uniform(0.8, 1.2)
                q = rng.random()
                if q < 0.75 * bl:
                    c = purple * rng.uniform(0.8, 1.12)
                elif q < 0.35 * rust:
                    c = rustc * rng.uniform(0.8, 1.15)
                elif q < 0.45 * tips:
                    c = spring * rng.uniform(0.9, 1.1)
                lean = rng.normal(0, 0.25)
                self.hs_line([(x, y), (x + lean * hh, y - hh)], green * 0.62, (lean * -0.5, 0.5, 0.75), max(1.0, 0.8 * r))
                self.hs_ell(x + lean * hh, y - hh, r, r * 0.8, c, (lean * -0.4, 0.25, 0.92), obj=False)

    # ------------------------------------------------------------- meadows --
    def hs_meadows(self):
        """Patches of whatever wildflowers are out, thicker than the scattered ones, on stems."""
        W, H, s = self.W, self.H, self.s
        se = self.season
        if not se.flowers:
            return
        dens = min(1.0, sum(w for _, w in se.flowers) / 1.2)
        for (xf, yf, rx, ry, cnt, seed) in MEADOW:
            rng = np.random.default_rng(410 + seed)
            cols = se.flower_palette(np.random.default_rng(420 + seed), cnt)
            x0, y0 = xf * W, yf * H
            p = self.hs_persp(y0)
            for i in range(int(cnt * dens)):
                t, u = rng.uniform(0, 2 * np.pi), rng.uniform(0, 1) ** 0.7
                x, y = x0 + math.cos(t) * u * rx * s * p, y0 + math.sin(t) * u * ry * s * p
                hgt = rng.uniform(4, 9) * s * self.hs_persp(y)
                r = rng.uniform(1.1, 1.9) * s * self.hs_persp(y)
                lean = rng.normal(0, 0.18) * hgt
                self.hs_line([(x, y), (x + lean, y - hgt)], (70, 98, 46), FRONT, max(1.0, 0.5 * s), obj=False)
                self.hs_ell(x + lean, y - hgt, r, r * 0.8, cols[i], (0.0, 0.3, 0.95), obj=False)

    # -------------------------------------------------------------- puddles --
    def hs_puddles(self, persp):
        """Standing water after rain, in the path's ruts and in the hollows by the gate: drawn into X (red:
        the water, green: its wet rim), as big as the ground is wet. The hill lights them (land.py)."""
        wet = self.wx.wet
        k = sm(0.3, 0.9, wet)
        if k <= 0.02 or self.wx.snow_cover > 0.6:
            return
        W, H, s = self.W, self.H, self.s
        X = self._hsX
        tw = self.tw
        p = self.bezier((0.10 * W, 1.03 * H), (0.15 * W, 0.80 * H), (0.27 * W, 0.71 * H), (tw["cx"], tw["yb"] + 10 * s), 400)
        d = np.gradient(p, axis=0)
        d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-6
        spots = []
        for t, ac, sz in PATH_PUDDLES:
            i = int(t * (len(p) - 1))
            w = (0.038 + (0.009 - 0.038) * t) * W
            nx, ny = -d[i, 1], d[i, 0]
            x, y = p[i, 0] + nx * ac * w, p[i, 1] + ny * ac * w
            spots.append((x, y, sz * w * 0.3, math.atan2(d[i, 1], d[i, 0])))
        for xf, yf, rx in HOLLOW_PUDDLES:
            spots.append((xf * W, yf * H, rx * s * self.hs_persp(yf * H), 0.0))
        rng = np.random.default_rng(430)
        for x, y, rx, ang in spots:
            rx = rx * (0.4 + 0.6 * k)
            ry = rx * 0.24
            sh = 0.35 * math.sin(ang) * ry / max(rx, 1e-6)     # lie along the rut
            n = 28
            jit = 1 + 0.12 * np.convolve(rng.normal(0, 1, n + 4), np.ones(5) / 5, "valid")
            ring = lambda f, dy=0.0: [(x + f * jit[j] * rx * math.cos(2 * math.pi * j / n),
                                       y + dy + f * jit[j] * ry * math.sin(2 * math.pi * j / n) + sh * f * jit[j] * rx * math.cos(2 * math.pi * j / n))
                                      for j in range(n)]
            X.poly(ring(1.3, 0.1 * ry), (0, 255, 0))          # the wet, darker ground round it
            if k > 0.12:
                X.poly(ring(1.0), (255, 255, 0))
                X.poly(ring(0.97, 0.06 * ry), (128, 255, 0))       # its far bank, mirrored dark
                X.poly(ring(0.94, 0.1 * ry), (255, 255, 0))

    def puddle_light(self, col, pud, Yg, xw, L, buried):
        """Water standing in the puddles mirrors the sky: the sky's colour at the angle you look down at
        the water (as sky.py paints it), greyed under cloud, brighter toward the sun; ice in a hard frost.
        col (rows, cols, 3) is the lit hill, pud (rows, xw) the water, Yg (rows, 1) the frame rows."""
        W, H = self.W, self.H
        sa = self.sun_alt
        a = np.maximum((Yg - VH * H) / (VH * H) * ALT_TOP, 0.5)           # degrees below the horizon
        zen, mid, hor = keys(SKY_ZEN, sa), keys(SKY_MID, sa), keys(SKY_HOR, sa)
        tu = sm(6, 60, a)[..., None]
        sky = mid * (1 - tu) + zen * tu
        wh = np.exp(-a / 7.0)[..., None]
        sky = sky * (1 - wh) + hor * wh
        ov = self.overcast
        sky = sky * (1 - ov) + keys(CLOUD_SHADE, sa) * 1.05 * ov
        vis = sm(-14, -1, sa)
        if vis > 0:                      # the sun's glow, seen in the water
            az = np.radians(180 + ((np.arange(xw, dtype=np.float32) + 0.5) / W - 0.5) * AZ_SPAN)[None, :]
            ar = np.radians(a)
            dot = np.cos(ar) * np.sin(az) * self.sunv[0] + np.cos(ar) * np.cos(az) * self.sunv[1] + np.sin(ar) * self.sunv[2]
            g = np.degrees(np.arccos(np.clip(dot, -1, 1)))
            glow = (0.55 * np.exp(-g / 2.2) * self.sun_vis + 0.30 * np.exp(-g / 9) + 0.15 * np.exp(-g / 30)) * vis * (1 - 0.7 * ov)
            sky = sky + glow[..., None] * keys(GLOW_COL, sa)
        bank = np.clip(2 * (1 - pud), 0, 1)[..., None] * (pud > 0.3)[..., None]   # red 0.5: the far bank's reflection
        p = np.clip(pud * 1.6, 0, 1)
        if not np.isscalar(buried):
            p *= 1 - buried[:, :xw]
        p = p[..., None]
        here = col[:, :xw]
        sky = sky * 0.8 + sky.mean(-1, keepdims=True) * 0.2        # muddy water: a little greyer than the sky
        water = sky * 0.6 + here * 0.4
        water = water * (1 - 0.75 * bank) + here * 0.55 * 0.75 * bank
        if self.wx.frost > 0.3 and self.wx.temp_c < 0.5:     # frozen over: pale, lit like the ground
            water = water * 0.45 + np.array((196, 204, 212), np.float32) * L[:, :xw] * 0.55
        col[:, :xw] = here * (1 - p) + water * p
