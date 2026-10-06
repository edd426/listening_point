"""What the time of year does to the scene: the tree, the grass, the flowers, and who is about.

Everything is a smooth function of the day of the year, so the scene drifts from one day to the
next instead of jumping on the first of the month.
"""
import math

import numpy as np


def ramp(d, a, b):
    """0 before day a, 1 after day b, smooth in between (days of the year, may wrap past 365)."""
    t = min(1.0, max(0.0, (d - a) / (b - a)))
    return t * t * (3 - 2 * t)


def bump(d, a, b, c, e):
    """Rises over a..b, holds, falls over c..e; handles windows that wrap over New Year."""
    if e > 365 and d < a:
        d += 365
    return ramp(d, a, b) * (1 - ramp(d, c, e))


# wildflowers by season: (first day, peak start, peak end, last day, colour)
FLOWERS = [
    (60, 80, 120, 150, (246, 232, 150)),     # primroses
    (70, 95, 280, 320, (242, 240, 230)),     # daisies, nearly all year
    (110, 130, 170, 195, (240, 206, 70)),    # buttercups
    (130, 150, 200, 225, (230, 120, 150)),   # red campion and clover
    (150, 160, 185, 205, (214, 52, 40)),     # poppies
    (165, 185, 235, 260, (176, 146, 214)),   # knapweed
    (175, 195, 240, 265, (120, 140, 220)),   # harebells
    (190, 205, 255, 280, (236, 232, 222)),   # yarrow
    (240, 255, 290, 310, (168, 124, 200)),   # asters
]


class Season:
    def __init__(self, date):
        d = date.timetuple().tm_yday
        self.date, self.doy = date, d
        # the tree: bud burst in early April, full by mid-May, colour from late September,
        # bare by the end of November
        self.leaf_out = ramp(d, 93, 132)
        self.young = ramp(d, 93, 110) * (1 - ramp(d, 135, 165))
        self.autumn = ramp(d, 270, 306)
        self.drop = ramp(d, 288, 330)
        self.leaves = self.leaf_out * (1 - self.drop)
        # litter under the tree: builds through October, rots away over the winter
        self.fallen = ramp(d, 275, 305) * (1 - 0.5 * ramp(d, 330, 365)) if d >= 200 else 0.5 * (1 - ramp(d, 0, 75))
        # grass: lush in spring, sun-dried in high summer, dull and flattened in winter
        self.lush = bump(d, 70, 105, 160, 190)
        self.dry = bump(d, 170, 200, 240, 275)
        self.winter = bump(d, 320, 345, 365 + 45, 365 + 80)
        self.flowers = [(c, bump(d, a, b, e, f)) for a, b, e, f, c in FLOWERS if bump(d, a, b, e, f) > 0.02]
        self.flower_density = min(1.0, sum(w for _, w in self.flowers) / 2.2)
        # who is about
        self.lambs = 74 <= d <= 152          # mid-March to the end of May
        self.shorn = 152 <= d <= 196         # June to mid-July, before the fleece grows back
        self.fireflies = bump(d, 158, 168, 195, 205)
        self.bats = bump(d, 90, 105, 290, 305)
        self.swallows = bump(d, 110, 125, 235, 255)
        self.geese = bump(d, 60, 70, 85, 95) + bump(d, 280, 290, 305, 315)
        self.boating = bump(d, 95, 115, 290, 305)
        # the sea is greyer and choppier in winter
        self.sea_winter = 0.5 + 0.5 * math.cos(2 * math.pi * (d - 15) / 365)

    def flower_palette(self, rng, n):
        """n flower colours drawn in proportion to what is in bloom."""
        if not self.flowers:
            return np.zeros((0, 3), np.float32)
        cols = np.array([c for c, _ in self.flowers], np.float32)
        w = np.array([w for _, w in self.flowers], np.float64)
        return cols[rng.choice(len(cols), n, p=w / w.sum())]
