#!/usr/bin/env python3
"""The Listening Point: one scene, rendered once for every hour of the day.

A small stone observatory on a headland above the sea, with a tree, a bench for
two, a lamp, a pier, and a lighthouse across the bay. The sun, the full moon and
the real bright stars are placed for Budapest's latitude at the September
equinox, so the sky keeps time; the clock on the tower says it plainly.

usage: listening_point.py OUT_DIR [--scale 1.0] [--hours 0-23] [--jobs 2] [--sheet]

Renders HH.jpg for each requested hour at 3840x2400 * scale.
"""
import argparse
import functools
import math
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

LAT = math.radians(47.5)
VH = 0.58            # horizon, as a fraction of frame height
ALT_TOP = 70.0       # altitude (deg) at the top edge of the frame
AZ_SPAN = 220.0      # azimuth (deg) across the frame; the view faces south
KF = 0.30            # foreshortening of ground distances toward the viewer
SS = 2               # supersampling for vector-drawn shapes
FONT = "/System/Library/Fonts/Supplemental/Georgia.ttf"

# ---------------------------------------------------------------- palettes ---
# (sun altitude in degrees, colour)
SKY_ZEN = [(-90, (4, 6, 14)), (-18, (5, 7, 18)), (-12, (9, 13, 34)), (-8, (18, 26, 62)),
           (-4, (34, 50, 104)), (0, (50, 78, 138)), (4, (62, 104, 172)), (10, (56, 114, 192)),
           (25, (46, 110, 198)), (45, (40, 104, 198))]
SKY_MID = [(-90, (6, 9, 22)), (-18, (8, 12, 28)), (-12, (17, 23, 54)), (-8, (38, 46, 94)),
           (-4, (78, 88, 148)), (0, (118, 128, 172)), (4, (140, 168, 208)), (10, (128, 178, 222)),
           (25, (108, 168, 228)), (45, (98, 162, 228))]
SKY_HOR = [(-90, (10, 14, 30)), (-18, (16, 22, 42)), (-12, (36, 40, 74)), (-8, (80, 70, 108)),
           (-4, (150, 110, 124)), (0, (200, 150, 132)), (4, (225, 190, 160)), (10, (222, 212, 198)),
           (25, (192, 214, 232)), (45, (186, 210, 232))]
GLOW_COL = [(-12, (80, 50, 80)), (-6, (190, 90, 70)), (-1, (255, 120, 60)), (3, (255, 165, 95)),
            (10, (255, 215, 170)), (30, (255, 245, 228))]
SUN_DISK = [(-1, (255, 140, 70)), (3, (255, 185, 115)), (10, (255, 232, 195)), (30, (255, 252, 244))]
SUN_COL = [(-3, (.95, .40, .21)), (2, (.95, .55, .32)), (8, (.92, .72, .52)), (20, (.88, .81, .70)),
           (40, (.86, .83, .79))]
AMB = [(-90, (.035, .045, .08)), (-18, (.04, .05, .09)), (-10, (.08, .09, .15)), (-4, (.19, .17, .25)),
       (0, (.30, .27, .33)), (6, (.38, .38, .44)), (15, (.43, .46, .54)), (40, (.46, .50, .58))]
CLOUD_LIT = [(-18, (34, 40, 60)), (-10, (62, 56, 84)), (-5, (196, 104, 112)), (-1, (255, 138, 90)),
             (3, (255, 180, 130)), (8, (255, 224, 198)), (20, (250, 250, 252)), (45, (255, 255, 255))]
CLOUD_SHADE = [(-18, (12, 15, 26)), (-10, (26, 26, 44)), (-5, (78, 58, 88)), (0, (136, 96, 116)),
               (5, (166, 146, 156)), (15, (186, 194, 208)), (45, (196, 204, 218))]
MOON_COL = np.array([.60, .70, 1.0], np.float32)
WATER = np.array([18, 54, 76], np.float32)
WARM = np.array([1.0, .72, .42], np.float32)

# ------------------------------------------------------------------ layout ---
HILL = [(-0.01, 0.600), (0.10, 0.602), (0.20, 0.607), (0.30, 0.617), (0.38, 0.630), (0.46, 0.648),
        (0.53, 0.668), (0.575, 0.690), (0.61, 0.725), (0.64, 0.775), (0.67, 0.815), (0.71, 0.845),
        (0.77, 0.868), (0.84, 0.884), (0.92, 0.896), (1.02, 0.905)]
TOWER = dict(cx=0.300, yb=0.656, yt=0.445, r=146)
CLOCK = dict(y=0.487, R=70)
TREE_BASE = (0.447, 0.707)
CANOPY = (0.452, 0.440, 336, 262)
BENCH = (0.492, 0.724)
LAMP = (0.548, 0.738, 300)
PIER = [(0.700, 0.862), (0.858, 0.786), (0.861, 0.777), (0.709, 0.842)]  # near root, near end, far end, far root
LH_X = 0.768
MOORED = (0.895, 0.800)
BOAT_DAY = {7: (0.885, 0.795), 8: (0.930, 0.740), 9: (0.930, 0.680), 10: (0.860, 0.645),
            11: (0.780, 0.628), 12: (0.690, 0.624), 13: (0.615, 0.636), 14: (0.600, 0.665),
            15: (0.680, 0.700), 16: (0.790, 0.750), 17: (0.870, 0.785)}

# ------------------------------------------------------------------- stars ---
W_, BW, YW, OR, RD = (1, 1, 1), (.85, .93, 1.1), (1.05, 1, .9), (1.15, .92, .72), (1.2, .8, .62)
STARS = [
    ("Sirius", 6.752, -16.72, -1.46, BW), ("Betelgeuse", 5.919, 7.41, 0.50, OR),
    ("Rigel", 5.242, -8.20, 0.13, BW), ("Bellatrix", 5.419, 6.35, 1.64, BW),
    ("Mintaka", 5.533, -0.30, 2.23, BW), ("Alnilam", 5.604, -1.20, 1.69, BW),
    ("Alnitak", 5.679, -1.94, 1.77, BW), ("Saiph", 5.796, -9.67, 2.07, BW),
    ("Meissa", 5.585, 9.93, 3.39, BW), ("Mirzam", 6.378, -17.96, 1.98, BW),
    ("Adhara", 6.977, -28.97, 1.50, BW), ("Wezen", 7.140, -26.39, 1.83, YW),
    ("Aludra", 7.402, -29.30, 2.45, BW), ("Procyon", 7.655, 5.22, 0.34, YW),
    ("Gomeisa", 7.453, 8.29, 2.89, BW), ("Castor", 7.577, 31.89, 1.58, W_),
    ("Pollux", 7.755, 28.03, 1.14, OR), ("Alhena", 6.629, 16.40, 1.93, W_),
    ("Mebsuta", 6.732, 25.13, 3.06, YW), ("Aldebaran", 4.599, 16.51, 0.86, OR),
    ("Elnath", 5.438, 28.61, 1.65, BW), ("Ain", 4.477, 19.18, 3.53, OR),
    ("HyadumI", 4.330, 15.63, 3.65, OR), ("HyadumII", 4.382, 17.54, 3.76, OR),
    ("Chamukuy", 4.477, 15.87, 3.40, W_), ("Tianguan", 5.627, 21.14, 3.00, BW),
    ("Alcyone", 3.791, 24.105, 2.87, BW), ("Atlas", 3.819, 24.053, 3.62, BW),
    ("Electra", 3.747, 24.113, 3.70, BW), ("Maia", 3.763, 24.368, 3.87, BW),
    ("Merope", 3.772, 23.948, 4.18, BW), ("Taygeta", 3.753, 24.467, 4.30, BW),
    ("Pleione", 3.819, 24.137, 5.05, BW), ("Capella", 5.278, 46.00, 0.08, YW),
    ("Menkalinan", 5.992, 44.95, 1.90, W_), ("Mirfak", 3.405, 49.86, 1.79, YW),
    ("Algol", 3.136, 40.96, 2.12, BW), ("Hamal", 2.120, 23.46, 2.00, OR),
    ("Sheratan", 1.911, 20.81, 2.64, W_), ("Alpheratz", 0.140, 29.09, 2.06, BW),
    ("Mirach", 1.162, 35.62, 2.05, OR), ("Almach", 2.065, 42.33, 2.10, OR),
    ("DeltaAnd", 0.656, 30.86, 3.27, OR), ("Markab", 23.079, 15.21, 2.48, BW),
    ("Scheat", 23.063, 28.08, 2.42, OR), ("Algenib", 0.221, 15.18, 2.83, BW),
    ("Enif", 21.736, 9.88, 2.39, OR), ("Homam", 22.691, 10.83, 3.40, BW),
    ("Matar", 22.717, 30.22, 2.94, YW), ("Diphda", 0.727, -17.99, 2.02, OR),
    ("Menkar", 3.038, 4.09, 2.54, OR), ("Fomalhaut", 22.961, -29.62, 1.16, W_),
    ("Sadalsuud", 21.526, -5.57, 2.87, YW), ("Sadalmelik", 22.096, -0.32, 2.95, YW),
    ("DenebAlgedi", 21.784, -16.13, 2.85, W_), ("Dabih", 20.350, -14.78, 3.05, YW),
    ("Altair", 19.846, 8.87, 0.77, W_), ("Tarazed", 19.771, 10.61, 2.72, OR),
    ("Alshain", 19.922, 6.41, 3.71, YW), ("Vega", 18.616, 38.78, 0.03, BW),
    ("Sheliak", 18.835, 33.36, 3.52, BW), ("Sulafat", 18.982, 32.69, 3.25, BW),
    ("Deneb", 20.690, 45.28, 1.25, BW), ("Sadr", 20.370, 40.26, 2.23, YW),
    ("Gienah", 20.770, 33.97, 2.48, OR), ("Fawaris", 19.750, 45.13, 2.87, BW),
    ("Albireo", 19.512, 27.96, 3.08, OR), ("KausAustralis", 18.403, -34.38, 1.85, BW),
    ("Nunki", 18.921, -26.30, 2.05, BW), ("KausMedia", 18.350, -29.83, 2.70, OR),
    ("KausBorealis", 18.466, -25.42, 2.81, OR), ("Ascella", 19.044, -29.88, 2.60, W_),
    ("Alnasl", 18.097, -30.42, 2.99, OR), ("PhiSgr", 18.761, -26.99, 3.17, BW),
    ("TauSgr", 19.116, -27.67, 3.32, OR), ("Antares", 16.490, -26.43, 1.06, RD),
    ("Rasalhague", 17.582, 12.56, 2.08, W_), ("Arcturus", 14.261, 19.18, -0.05, OR),
    ("Spica", 13.420, -11.16, 0.97, BW), ("Regulus", 10.140, 11.97, 1.35, BW),
    ("Denebola", 11.818, 14.57, 2.13, W_), ("Algieba", 10.333, 19.84, 2.08, OR),
    ("Alphard", 9.460, -8.66, 1.98, OR), ("Alphecca", 15.578, 26.71, 2.22, W_),
]
LINES = [
    ("Betelgeuse", "Meissa"), ("Meissa", "Bellatrix"), ("Betelgeuse", "Alnitak"), ("Bellatrix", "Mintaka"),
    ("Mintaka", "Alnilam"), ("Alnilam", "Alnitak"), ("Alnitak", "Saiph"), ("Mintaka", "Rigel"),
    ("Mirzam", "Sirius"), ("Sirius", "Wezen"), ("Wezen", "Adhara"), ("Wezen", "Aludra"),
    ("Procyon", "Gomeisa"), ("Castor", "Pollux"), ("Castor", "Mebsuta"), ("Pollux", "Alhena"),
    ("HyadumI", "HyadumII"), ("HyadumII", "Ain"), ("Ain", "Elnath"), ("HyadumI", "Chamukuy"),
    ("Chamukuy", "Aldebaran"), ("Aldebaran", "Tianguan"), ("Capella", "Menkalinan"), ("Mirfak", "Algol"),
    ("Hamal", "Sheratan"), ("Alpheratz", "DeltaAnd"), ("DeltaAnd", "Mirach"), ("Mirach", "Almach"),
    ("Alpheratz", "Scheat"), ("Scheat", "Markab"), ("Markab", "Algenib"), ("Algenib", "Alpheratz"),
    ("Markab", "Homam"), ("Homam", "Enif"), ("Scheat", "Matar"), ("Tarazed", "Altair"),
    ("Altair", "Alshain"), ("Vega", "Sheliak"), ("Sheliak", "Sulafat"), ("Sulafat", "Vega"),
    ("Deneb", "Sadr"), ("Sadr", "Albireo"), ("Gienah", "Sadr"), ("Sadr", "Fawaris"),
    ("Vega", "Altair"), ("Altair", "Deneb"), ("Deneb", "Vega"),
    ("KausMedia", "KausBorealis"), ("KausBorealis", "PhiSgr"), ("PhiSgr", "KausMedia"),
    ("KausMedia", "KausAustralis"), ("KausAustralis", "Ascella"), ("Ascella", "PhiSgr"),
    ("PhiSgr", "Nunki"), ("Nunki", "TauSgr"), ("TauSgr", "Ascella"), ("Alnasl", "KausMedia"),
    ("Alnasl", "KausAustralis"), ("Regulus", "Algieba"), ("Algieba", "Denebola"),
    ("Denebola", "Regulus"), ("Dabih", "DenebAlgedi"), ("Sadalsuud", "Sadalmelik"),
]
GAL = np.array([[-0.0548755604, -0.8734370902, -0.4838350155],
                [0.4941094279, -0.4448296300, 0.7469822445],
                [-0.8676661490, -0.1980763734, 0.4559837762]])


def _catalog():
    rng = np.random.default_rng(2024)
    n = 7000
    ra = rng.uniform(0, 24, n)
    dec = np.degrees(np.arcsin(rng.uniform(-1, 1, n)))
    mag = 6.6 - 3.2 * rng.random(n) ** 2.6
    # a second population hugging the galactic plane, so the Milky Way reads as stars
    m = 2600
    l = np.radians(rng.uniform(-180, 180, m))
    b = np.radians(rng.normal(0, 7, m))
    g = np.stack([np.cos(b) * np.cos(l), np.cos(b) * np.sin(l), np.sin(b)])
    eq = GAL.T @ g
    ra = np.concatenate([ra, (np.degrees(np.arctan2(eq[1], eq[0])) / 15) % 24])
    dec = np.concatenate([dec, np.degrees(np.arcsin(eq[2]))])
    mag = np.concatenate([mag, rng.uniform(5.2, 6.9, m)])
    t = rng.random(n + m)
    tint = np.where(t[:, None] < .25, BW, np.where(t[:, None] < .85, W_, np.where(t[:, None] < .97, YW, OR)))
    ra = np.concatenate([[s[1] for s in STARS], ra])
    dec = np.concatenate([[s[2] for s in STARS], dec])
    mag = np.concatenate([[s[3] for s in STARS], mag])
    tint = np.concatenate([np.array([s[4] for s in STARS], float), tint])
    return ra, dec, mag, tint.astype(np.float32)


STAR_RA, STAR_DEC, STAR_MAG, STAR_TINT = _catalog()
STAR_IDX = {s[0]: i for i, s in enumerate(STARS)}


# ----------------------------------------------------------------- helpers ---
def sm(a, b, x):
    t = np.clip((np.asarray(x, np.float32) - a) / (b - a), 0, 1)
    t = t * t * (3 - 2 * t)
    return float(t) if t.ndim == 0 else t


def keys(table, x):
    xs = [k[0] for k in table]
    cs = np.array([k[1] for k in table], np.float32)
    return np.array([np.interp(x, xs, cs[:, i]) for i in range(3)], np.float32)


def rgba(c, a=1.0):
    return tuple(int(max(0, min(255, round(float(v))))) for v in c) + (int(max(0, min(255, round(a * 255)))),)


def hash2(a, b):
    v = np.sin(np.asarray(a, np.float64) * 12.9898 + np.asarray(b, np.float64) * 78.233) * 43758.5453
    return (v - np.floor(v)).astype(np.float32)


@functools.lru_cache(None)
def fnoise(h, w, beta, aniso=1.0, seed=0):
    """Periodic 1/f^beta noise, zero mean and unit variance."""
    rng = np.random.default_rng(seed)
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    f = np.sqrt((fx * aniso) ** 2 + fy ** 2)
    f[0, 0] = 1.0
    spec = (rng.standard_normal((h, w // 2 + 1)) + 1j * rng.standard_normal((h, w // 2 + 1))) / f ** (beta / 2)
    spec[0, 0] = 0
    n = np.fft.irfft2(spec, s=(h, w))
    return ((n - n.mean()) / n.std()).astype(np.float32)


def sample(tex, r, c):
    return ndi.map_coordinates(tex, np.stack([r, c]).astype(np.float32), order=1, mode="grid-wrap",
                               prefilter=False)


def altaz(ra_h, dec_d, lst_h):
    H = np.radians((lst_h - np.asarray(ra_h)) * 15.0)
    d = np.radians(dec_d)
    e = -np.cos(d) * np.sin(H)
    n = np.sin(d) * math.cos(LAT) - np.cos(d) * np.cos(H) * math.sin(LAT)
    u = np.sin(d) * math.sin(LAT) + np.cos(d) * np.cos(H) * math.cos(LAT)
    return np.degrees(np.arcsin(np.clip(u, -1, 1))), np.degrees(np.arctan2(e, n)) % 360.0


def enu(alt, az):
    a, z = math.radians(alt), math.radians(az)
    return np.array([math.cos(a) * math.sin(z), math.cos(a) * math.cos(z), math.sin(a)], np.float32)


def to_screen(alt, az):
    return 0.5 + (np.asarray(az) - 180.0) / AZ_SPAN, VH - np.asarray(alt) / ALT_TOP * VH


def hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out
    lo, hi = half(pts), half(reversed(pts))
    return lo[:-1] + hi[:-1]


def normalize(v):
    v = np.asarray(v, np.float32)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-6)


class Layer:
    """A supersampled RGBA drawing surface covering a pixel box of the frame."""

    def __init__(self, fr, x0, y0, x1, y1):
        self.fr = fr
        self.x0, self.y0 = max(0, int(math.floor(x0))), max(0, int(math.floor(y0)))
        self.x1, self.y1 = min(fr.W, int(math.ceil(x1))), min(fr.H, int(math.ceil(y1)))
        self.ok = self.x1 > self.x0 and self.y1 > self.y0
        size = (max(1, self.x1 - self.x0) * SS, max(1, self.y1 - self.y0) * SS)
        self.img = Image.new("RGBA", size, (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def P(self, x, y):
        return ((x - self.x0) * SS, (y - self.y0) * SS)

    def poly(self, pts, col, a=1.0):
        self.d.polygon([self.P(*p) for p in pts], fill=rgba(col, a))

    def ellipse(self, cx, cy, rx, ry, col, a=1.0):
        (x0, y0), (x1, y1) = self.P(cx - rx, cy - ry), self.P(cx + rx, cy + ry)
        if x1 > x0 and y1 > y0:
            self.d.ellipse([x0, y0, x1, y1], fill=rgba(col, a))

    def line(self, pts, col, w, a=1.0):
        self.d.line([self.P(*p) for p in pts], fill=rgba(col, a), width=max(1, int(round(w * SS))), joint="curve")

    def text(self, x, y, s, font, col, a=1.0):
        self.d.text(self.P(x, y), s, font=font, fill=rgba(col, a), anchor="mm")

    def arrays(self):
        im = self.img.resize((self.x1 - self.x0, self.y1 - self.y0), Image.BOX)
        a = np.asarray(im, np.float32)
        return a[..., :3], a[..., 3:] / 255.0

    def composite(self, allow=None):
        if not self.ok:
            return
        rgb, al = self.arrays()
        if allow is not None:
            al = al * allow[..., None]
        t = self.fr.c[self.y0:self.y1, self.x0:self.x1]
        t *= 1 - al
        t += rgb * al


# ------------------------------------------------------------------- frame ---
class Frame:
    def __init__(self, hour, scale=1.0):
        self.h = hour
        self.W, self.H = int(round(3840 * scale)), int(round(2400 * scale))
        self.s = self.W / 3840
        self.hz = int(round(VH * self.H))
        self.c = np.zeros((self.H, self.W, 3), np.float32)
        self.rng = np.random.default_rng(1000 + hour)
        sa, saz = altaz(12.0, 0.0, hour)
        ma, maz = altaz(0.0, 0.0, hour)
        self.sun_alt, self.sun_az = float(sa), float(saz)
        self.moon_alt, self.moon_az = float(ma), float(maz)
        self.sunv, self.moonv = enu(self.sun_alt, self.sun_az), enu(self.moon_alt, self.moon_az)
        sa = self.sun_alt
        self.sun_str = sm(-2.5, 6, sa)
        self.sun_col = keys(SUN_COL, sa)
        self.amb = keys(AMB, sa)
        self.night = sm(-3, -10, sa)
        self.dark = sm(-8, -15, sa)
        self.moon_str = 0.30 * sm(0, 12, self.moon_alt) * sm(-3, -12, sa)
        self.lights_on = sm(2, -4, sa)
        self.observing = sa < -9
        self.hor_col = keys(SKY_HOR, sa)
        self.emitters = []   # (x, y, colour, strength, water_y) for reflections on the sea
        # ground-level light pools at night: (source x, y, ground y, colour, radius, strength)
        self.pools = []
        s = self.s
        T = TOWER
        self.tw = dict(cx=T["cx"] * self.W, yb=T["yb"] * self.H, yt=T["yt"] * self.H, r=T["r"] * s)
        if self.lights_on > 0:
            lx, ly = LAMP[0] * self.W, LAMP[1] * self.H - LAMP[2] * s * 0.96
            self.pools.append((lx, ly, LAMP[1] * self.H, WARM, 150 * s, 0.6 * self.lights_on))
            dx, dy = self.tw["cx"] + 62 * s, self.tw["yb"] - 92 * s
            self.pools.append((dx, dy, self.tw["yb"] + 14 * s, WARM, 110 * s, 0.45 * self.lights_on))
        # edge of the foreground hill
        xd = np.linspace(-0.01, 1.02, 5000)
        yd = np.interp(xd, *zip(*HILL))
        yd = ndi.gaussian_filter1d(yd, 30, mode="nearest")
        yd += 0.0035 * np.interp(np.linspace(0, 1, 5000), np.linspace(0, 1, 1024), fnoise(4, 1024, 1.8, 1, 17)[0])
        yd += 0.006 * sm(0.56, 0.62, xd) * np.interp(np.linspace(0, 1, 5000), np.linspace(0, 1, 2048), fnoise(4, 2048, 1.3, 1, 18)[0])
        self._edge = (xd, yd)

    def edge(self, xn):
        return np.interp(xn, *self._edge)

    # ------------------------------------------------------------ lighting --
    def light(self, nrm, shade=None, ao=None):
        nrm = np.asarray(nrm, np.float32)
        ds = np.clip(nrm @ self.sunv, 0, None)
        dm = np.clip(nrm @ self.moonv, 0, None)
        if shade is not None:
            ds = ds * (1 - shade)
            dm = dm * (1 - shade)
        amb = self.amb if ao is None else self.amb * np.asarray(ao, np.float32)[..., None]
        return amb + np.asarray(ds)[..., None] * self.sun_col * self.sun_str + np.asarray(dm)[..., None] * MOON_COL * self.moon_str

    def local(self, X, Y, ground=False):
        out = 0.0
        for (lx, ly, gy, col, rad, k) in self.pools:
            if ground:
                d2 = ((X - lx) / rad) ** 2 + ((Y - gy) / (rad * KF * 1.6)) ** 2
            else:
                d2 = ((X - lx) ** 2 + (Y - ly) ** 2) / (rad * 0.8) ** 2
            out = out + np.exp(-d2)[..., None] * col * k
        return out

    def lit(self, albedo, nrm, x=None, y=None, ao=1.0):
        L = self.light(normalize(nrm)) * ao
        if x is not None and self.pools:
            L = L + self.local(np.float32(x), np.float32(y))
        return np.asarray(albedo, np.float32) * L

    def glow(self, x, y, r, col, k, tail=0.0):
        R = r * (3.0 if tail == 0 else 7.0)
        x0, x1 = int(max(0, x - R)), int(min(self.W, x + R + 1))
        y0, y1 = int(max(0, y - R)), int(min(self.H, y + R + 1))
        if x0 >= x1 or y0 >= y1 or k <= 0:
            return
        X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - x
        Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - y
        d2 = (X * X + Y * Y) / (r * r)
        g = np.exp(-d2)
        if tail:
            g = g + tail / (1 + d2 * 3) * sm((R / r) ** 2, 0.5 * (R / r) ** 2, d2)
        self.c[y0:y1, x0:x1] += g[..., None] * np.asarray(col, np.float32) * k

    # ----------------------------------------------------------------- sky --
    def sky(self):
        W, H, hz, sa = self.W, self.H, self.hz, self.sun_alt
        y = (np.arange(hz, dtype=np.float32) + 0.5) / H
        x = (np.arange(W, dtype=np.float32) + 0.5) / W
        alt = np.ascontiguousarray(np.broadcast_to(((VH - y) / VH * ALT_TOP)[:, None], (hz, W)))
        az = np.ascontiguousarray(np.broadcast_to((180 + (x - 0.5) * AZ_SPAN)[None, :], (hz, W)))
        ar, zr = np.radians(alt), np.radians(az)
        ca = np.cos(ar)
        e, n, u = ca * np.sin(zr), ca * np.cos(zr), np.sin(ar)
        self.sky_alt, self.sky_az = alt, az

        zen, mid, hor = keys(SKY_ZEN, sa), keys(SKY_MID, sa), keys(SKY_HOR, sa)
        tu = sm(6, 60, alt)[..., None]
        col = mid * (1 - tu) + zen * tu
        wh = np.exp(-np.maximum(alt, 0) / 7.0)[..., None]
        col = col * (1 - wh) + hor * wh

        self.sun_glow = None
        vis = sm(-14, -1, sa)
        if vis > 0:
            g = np.degrees(np.arccos(np.clip(e * self.sunv[0] + n * self.sunv[1] + u * self.sunv[2], -1, 1)))
            self.sun_glow = (0.55 * np.exp(-g / 2.2) + 0.30 * np.exp(-g / 9) + 0.15 * np.exp(-g / 30)) * vis
            col += self.sun_glow[..., None] * keys(GLOW_COL, sa)
            daz = np.abs((az - self.sun_az + 180) % 360 - 180)
            band = np.exp(-np.maximum(alt, 0) / 4.5) * np.exp(-(daz / 50) ** 2) * sm(-15, -2, sa) * sm(14, 1, sa)
            col += band[..., None] * np.array([255, 115, 55], np.float32) * 0.5
        # the Belt of Venus and the Earth's shadow, opposite a low sun
        ba = sm(-8, -3, sa) * sm(3, -0.5, sa)
        if ba > 0:
            anti = -self.sunv
            ga = np.degrees(np.arccos(np.clip(e * anti[0] + n * anti[1] + u * anti[2], -1, 1)))
            w = np.exp(-(ga / 75) ** 2) * ba
            pink = (np.exp(-((alt - 10) / 6) ** 2) * w * 0.4)[..., None]
            col = col * (1 - pink) + np.array([214, 150, 175], np.float32) * pink
            shad = (sm(6, 0, alt) * w * 0.35)[..., None]
            col = col * (1 - shad) + np.array([70, 80, 122], np.float32) * shad
        # moonlight
        ms = sm(-2, 15, self.moon_alt) * self.night
        self.moon_sky = ms
        if ms > 0:
            col += np.array([14, 20, 38], np.float32) * ms * (0.6 + 0.4 * sm(40, 0, alt))[..., None]
            gm = np.degrees(np.arccos(np.clip(e * self.moonv[0] + n * self.moonv[1] + u * self.moonv[2], -1, 1)))
            col += (0.5 * np.exp(-gm / 1.6) + 0.22 * np.exp(-gm / 7) + 0.08 * np.exp(-gm / 25))[..., None] \
                * np.array([190, 205, 235], np.float32) * ms

        self.milky_way(col, e, n, u)
        del ar, zr, ca, e, n, u
        self.stars(col)
        self.sun_disk(col)
        self.moon_disk(col)
        self.clouds(col)
        self.c[:hz] = col

    def milky_way(self, col, e, n, u):
        vis = sm(-10, -17, self.sun_alt) * (1 - 0.4 * sm(0, 25, self.moon_alt))
        if vis < 0.01:
            return
        sp, cp = math.sin(LAT), math.cos(LAT)
        cH = u * cp - n * sp
        sH = -e
        L = math.radians(self.h * 15)
        X = math.cos(L) * cH + math.sin(L) * sH
        Y = math.sin(L) * cH - math.cos(L) * sH
        Z = u * sp + n * cp
        gx = GAL[0, 0] * X + GAL[0, 1] * Y + GAL[0, 2] * Z
        gy = GAL[1, 0] * X + GAL[1, 1] * Y + GAL[1, 2] * Z
        gz = GAL[2, 0] * X + GAL[2, 1] * Y + GAL[2, 2] * Z
        l = np.degrees(np.arctan2(gy, gx)).astype(np.float32)
        b = np.degrees(np.arcsin(np.clip(gz, -1, 1))).astype(np.float32)
        rows, cols = (b + 45) * 4, (l + 180) / 360 * 2048
        t1 = sample(fnoise(360, 2048, 1.7, 1.0, 41), rows, cols)
        t2 = sample(fnoise(360, 2048, 2.3, 1.0, 42), rows, cols)
        core = np.exp(-(l / 50) ** 2)
        width = 6 + 6 * core
        band = np.exp(-((b + 0.8 * t2) / width) ** 2)
        clump = np.clip(0.6 + 0.35 * t1, 0, None)
        rift = np.exp(-((b - 1.0 + 1.2 * t2) / 2.4) ** 2) * sm(-5, 15, l) * sm(95, 70, l)
        mw = band * clump * (0.4 + 0.6 * core) * (1 - 0.7 * rift)
        mcol = np.array([150, 160, 198], np.float32) + np.array([72, 40, -26], np.float32) * core[..., None]
        col += mw[..., None] * mcol * (0.20 * vis)

    def stars(self, col):
        W, H, hz, s = self.W, self.H, self.hz, self.s
        vis = sm(-4, -11, self.sun_alt) * (1 - 0.15 * sm(0, 25, self.moon_alt))
        if vis < 0.01:
            return
        alt, az = altaz(STAR_RA, STAR_DEC, self.h)
        x, y = to_screen(alt, az)
        X, Y = x * W, y * H
        ok = (alt > 0.4) & (X >= 0) & (X < W) & (Y >= 0) & (Y < hz - 1)
        tw = 1 + 0.12 * self.rng.standard_normal(len(STAR_MAG))
        sig = max(0.55, 1.15 * s)
        peak = np.minimum(255 * 10 ** (-0.17 * (STAR_MAG + 0.5)), 360) * vis * tw * (0.35 + 0.65 * sm(0, 14, alt))
        energy = (peak * 2 * math.pi * sig * sig).astype(np.float32)
        layer = np.zeros((hz, W, 3), np.float32)
        xi, yi = X[ok].astype(int), Y[ok].astype(int)
        for ch in range(3):
            np.add.at(layer[..., ch], (yi, xi), energy[ok] * STAR_TINT[ok, ch])
            layer[..., ch] = ndi.gaussian_filter(layer[..., ch], sig)
        col += layer
        big = ok & (STAR_MAG < 1.6)
        for i in np.nonzero(big)[0]:
            self._add(col, X[i], Y[i], 6 * s, np.array([200, 215, 255], np.float32) * STAR_TINT[i], 0.16 * peak[i] / 255)
        # faint constellation figures: connecting the dots
        lv = vis * (1 - 0.35 * sm(0, 25, self.moon_alt))
        im = Image.new("L", (W * SS, hz * SS), 0)
        d = ImageDraw.Draw(im)
        gap = 10 * s
        for a, bname in LINES:
            i, j = STAR_IDX[a], STAR_IDX[bname]
            if alt[i] < 1.5 or alt[j] < 1.5:
                continue
            p, q = np.array([X[i], Y[i]]), np.array([X[j], Y[j]])
            L = np.linalg.norm(q - p)
            if L < 3 * gap or not (ok[i] or ok[j]):
                continue
            dv = (q - p) / L
            p2, q2 = (p + dv * gap) * SS, (q - dv * gap) * SS
            d.line([tuple(p2), tuple(q2)], fill=255, width=max(1, int(round(1.3 * s * SS))))
        m = np.asarray(im.resize((W, hz), Image.BOX), np.float32) / 255
        col += m[..., None] * np.array([150, 170, 230], np.float32) * 0.13 * lv

    def _add(self, arr, x, y, r, colr, k):
        R = r * 3
        x0, x1 = int(max(0, x - R)), int(min(arr.shape[1], x + R + 1))
        y0, y1 = int(max(0, y - R)), int(min(arr.shape[0], y + R + 1))
        if x0 >= x1 or y0 >= y1:
            return
        X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - x
        Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - y
        arr[y0:y1, x0:x1] += np.exp(-(X * X + Y * Y) / (r * r))[..., None] * colr * k

    def sun_disk(self, col):
        if self.sun_alt < -2:
            return
        x, y = to_screen(self.sun_alt, self.sun_az)
        x, y, R = x * self.W, y * self.H, 30 * self.s
        B = R * 4
        x0, x1 = int(max(0, x - B)), int(min(self.W, x + B))
        y0, y1 = int(max(0, y - B)), int(min(self.hz, y + B))
        if x0 >= x1 or y0 >= y1:
            return
        X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - x
        Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - y
        d = np.sqrt(X * X + Y * Y)
        sc = keys(SUN_DISK, self.sun_alt)
        disk = np.clip(R - d + 0.5, 0, 1)[..., None]
        reg = col[y0:y1, x0:x1]
        reg[:] = reg * (1 - disk) + sc * (1 - 0.12 * (d / R) ** 2)[..., None] * disk
        reg += sc * 0.45 * np.exp(-(d / (R * 1.7)) ** 2)[..., None]

    def moon_disk(self, col):
        if self.moon_alt < -2:
            return
        x, y = to_screen(self.moon_alt, self.moon_az)
        x, y, R = x * self.W, y * self.H, 26 * self.s
        x0, x1 = int(max(0, x - R - 2)), int(min(self.W, x + R + 3))
        y0, y1 = int(max(0, y - R - 2)), int(min(self.hz, y + R + 3))
        if x0 >= x1 or y0 >= y1:
            return
        X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - x
        Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - y
        d = np.sqrt(X * X + Y * Y)
        tex = fnoise(128, 128, 3.2, 1.0, 77)
        mar = sample(tex, (Y / R * 0.5 + 0.5) * 60 + 30 + 0 * X, (X / R * 0.5 + 0.5) * 60 + 30 + 0 * Y)
        m = sm(0.1, 1.1, mar)
        crat = sample(fnoise(128, 128, 1.2, 1.0, 78), (Y / R) * 40 + 0 * X, (X / R) * 40 + 0 * Y)
        limb = 1 - 0.2 * (d / R) ** 2
        base = np.array([238, 234, 220], np.float32) * ((1 - 0.30 * m) * (1 + 0.05 * crat) * limb)[..., None]
        a = (np.clip(R - d + 0.5, 0, 1) * (0.45 + 0.55 * self.night))[..., None]
        reg = col[y0:y1, x0:x1]
        reg[:] = reg * (1 - a) + base * a

    def clouds(self, col):
        sa = self.sun_alt
        alt, az = self.sky_alt, self.sky_az
        a = np.radians(np.maximum(alt, 0.8))
        zr = np.radians(az)
        u, ca = np.sin(a), np.cos(a)
        Xp, Zp = ca * np.sin(zr) / u, -ca * np.cos(zr) / u
        tex = fnoise(512, 2048, 2.8, 2.0, 5)
        K = 55.0
        rows, cols = Zp * K, Xp * K + self.h / 24.0 * 2048
        n0 = sample(tex, rows, cols)
        lv = self.sunv if sa > -12 else self.moonv
        ld = np.array([lv[0], -lv[1]], np.float32)
        ld /= np.linalg.norm(ld) + 1e-6
        n1 = sample(tex, rows + ld[1] * 5, cols + ld[0] * 5)
        th = 0.45 + 0.5 * self.dark - 0.2 * math.exp(-(sa / 6) ** 2) + 0.15 * sm(20, 40, sa)
        th = th + 0.55 * sample(fnoise(256, 512, 3.0, 1.5, 6), rows * 0.12, cols * 0.12 + self.h * 7)
        dens = sm(th, th + 1.0, n0) * sm(2.5, 10, alt) * sm(65, 42, alt)
        lit = np.clip(0.62 + (n0 - n1) * 1.4, 0, 1)[..., None]
        lc, sc = keys(CLOUD_LIT, sa), keys(CLOUD_SHADE, sa)
        lc = lc + np.array([46, 52, 70], np.float32) * self.moon_sky
        cc = sc + (lc - sc) * lit
        if self.sun_glow is not None:
            cc += (self.sun_glow * (1 - 0.6 * dens))[..., None] * keys(GLOW_COL, sa) * 0.9
        hm = (np.exp(-alt / 9) * 0.55)[..., None]
        cc = cc * (1 - hm) + self.hor_col * hm
        al = (dens * 0.93)[..., None]
        col *= 1 - al
        col += cc * al

    def sky_extras(self):
        s, W, H = self.s, self.W, self.H
        if 8 <= self.h <= 16:   # gulls
            r = np.random.default_rng(500 + self.h)
            L = Layer(self, 0.45 * W, 0.08 * H, W, 0.45 * H)
            gc = np.array([70, 72, 82], np.float32) * (0.7 + 0.3 * self.amb / self.amb.max())
            for _ in range(r.integers(3, 7)):
                gx, gy, sz = r.uniform(0.52, 0.95) * W, r.uniform(0.12, 0.40) * H, r.uniform(9, 20) * s
                f = r.uniform(-0.6, 1.2)
                pts = [(gx - sz, gy - 0.1 * sz * f), (gx - 0.5 * sz, gy - 0.45 * sz * f), (gx, gy),
                       (gx + 0.5 * sz, gy - 0.45 * sz * f), (gx + sz, gy - 0.1 * sz * f)]
                L.line(pts, gc, 2.0 * s)
            L.composite()
        meteors = {2: ((0.20, 0.10), (0.29, 0.19)), 22: ((0.73, 0.07), (0.65, 0.16))}
        if self.h in meteors:
            (ax, ay), (bx, by) = meteors[self.h]
            L = Layer(self, min(ax, bx) * W - 10, min(ay, by) * H - 10, max(ax, bx) * W + 10, max(ay, by) * H + 10)
            for i in range(40):
                t0, t1 = i / 40, (i + 1) / 40
                L.line([((ax + (bx - ax) * t0) * W, (ay + (by - ay) * t0) * H),
                        ((ax + (bx - ax) * t1) * W, (ay + (by - ay) * t1) * H)],
                       (235, 240, 255), (0.6 + 2.2 * t1) * s, a=t1 ** 1.6 * 0.9)
            L.composite()
            self.glow(bx * W, by * H, 5 * s, (220, 230, 255), 0.6)

    # ----------------------------------------------------------- headland --
    def headland(self):
        W, H, s, sa = self.W, self.H, self.s, self.sun_alt
        x0, x1 = 0.585, 0.815
        t = np.linspace(0, 1, 900)
        bumps = np.interp(t, np.linspace(0, 1, 1024), fnoise(4, 1024, 1.5, 1, 21)[0])
        hgt = 0.020 * sm(0, 0.2, t) + 0.009 * sm(0.3, 0.7, t) + 0.0015 * bumps * sm(0, 0.1, t)
        hgt = hgt * sm(1.0, 0.955, t)
        self.hd = (x0, x1, t, hgt)
        top = VH - hgt
        pts = [((x0 + (x1 - x0) * ti) * W, yi * H) for ti, yi in zip(t, top)] + [(x1 * W, VH * H + 1), (x0 * W, VH * H + 1)]
        L = Layer(self, x0 * W - 2, (VH - 0.04) * H, x1 * W + 2, VH * H + 2)
        L.poly(pts, (255, 255, 255))
        _, al = L.arrays()
        X = (np.arange(L.x0, L.x1, dtype=np.float32) + 0.5) / W
        Y = (np.arange(L.y0, L.y1, dtype=np.float32) + 0.5) / H
        tc = ((X - x0) / (x1 - x0))[None, :]
        tex = fnoise(L.y1 - L.y0, L.x1 - L.x0, 1.8, 0.6, 22)
        land = np.array([70, 88, 62], np.float32) * (1 + 0.12 * tex)[..., None]
        cliff = np.maximum(sm(0.92, 0.965, tc), sm(0.07, 0.02, tc))[..., None] * np.ones_like(land[..., :1])
        rock = np.array([152, 140, 120], np.float32) * (1 + 0.15 * tex)[..., None]
        alb = land * (1 - cliff) + rock * cliff
        nl = self.light(normalize([0, 0.25, 0.97]))
        nc = self.light(normalize([-0.9, 0.3, 0.3]))
        col = alb * (nl * (1 - cliff) + nc * cliff)
        haze = 0.5 - 0.15 * self.night
        col = col * (1 - haze) + self.hor_col * haze * (0.9 + 0.1 * (Y[:, None] - VH + 0.04) / 0.04)[..., None]
        reg = self.c[L.y0:L.y1, L.x0:L.x1]
        reg[:] = reg * (1 - al) + col * al

        # a scatter of white houses; their windows light up after dusk
        r = np.random.default_rng(23)
        houses = []
        for _ in range(16):
            ti = r.uniform(0.07, 0.62)
            hy = VH - np.interp(ti, t, hgt) * r.uniform(0.18, 0.7)
            houses.append(((x0 + (x1 - x0) * ti) * W, hy * H, r.uniform(4, 7) * s))
        L = Layer(self, x0 * W, (VH - 0.04) * H, x1 * W, VH * H)
        treec = self.lit((44, 62, 40), (0, 0.5, 0.9)) * (1 - haze * 0.7) + self.hor_col * haze * 0.7
        for _ in range(70):
            ti = r.uniform(0.12, 0.88)
            if abs(ti - (LH_X - x0) / (x1 - x0)) < 0.05:
                continue
            ty_ = (VH - np.interp(ti, t, hgt)) * H + 1.5 * s
            L.ellipse((x0 + (x1 - x0) * ti) * W, ty_, r.uniform(3, 7) * s, r.uniform(3, 6) * s, treec)
        wall = self.lit((226, 220, 206), (0, 1, 0.2)) * (1 - haze * 0.6) + self.hor_col * haze * 0.6
        roof = self.lit((150, 70, 50), (0, 0.6, 0.8)) * (1 - haze * 0.6) + self.hor_col * haze * 0.6
        for hx, hy, hs in houses:
            L.poly([(hx - hs, hy), (hx + hs, hy), (hx + hs, hy - hs * 0.8), (hx - hs, hy - hs * 0.8)], wall)
            L.poly([(hx - hs * 1.1, hy - hs * 0.8), (hx + hs * 1.1, hy - hs * 0.8), (hx, hy - hs * 1.4)], roof)
        L.composite()
        if self.lights_on > 0:
            for i, (hx, hy, hs) in enumerate(houses):
                if i % 4 == 3:
                    continue
                k = self.lights_on * (0.6 + 0.4 * r.random())
                self.glow(hx + r.uniform(-0.4, 0.4) * hs, hy - 0.35 * hs, 1.8 * s, (255, 200, 120), 1.4 * k)
                self.glow(hx, hy - 0.35 * hs, 7 * s, (255, 170, 90), 0.12 * k)
                self.emitters.append((hx, hy, np.array([255, 190, 110], np.float32), 0.35 * k, self.hz))

        # the lighthouse
        tl = (LH_X - x0) / (x1 - x0)
        by = (VH - np.interp(tl, t, hgt)) * H + 2 * s
        lx = LH_X * W
        hgt_l = 0.050 * H

        def lh_albedo(sv, v, X, Y, r):
            red = ((v > 0.18) & (v < 0.32)) | ((v > 0.52) & (v < 0.66))
            a = np.where(red[..., None], np.array([178, 52, 44], np.float32), np.array([238, 236, 230], np.float32))
            return a * (1 - 0.12 * sv ** 2)[..., None]
        self.cylinder(lx, by - hgt_l, by, 8 * s, 11 * s, lh_albedo, haze=haze * 0.8, local=False)
        ty = by - hgt_l
        L = Layer(self, lx - 20 * s, ty - 30 * s, lx + 20 * s, ty + 4 * s)
        dark = self.lit((40, 38, 40), (0, 1, 0)) * (1 - haze * 0.5) + self.hor_col * haze * 0.5
        L.poly([(lx - 11 * s, ty + 1 * s), (lx + 11 * s, ty + 1 * s), (lx + 11 * s, ty - 2 * s), (lx - 11 * s, ty - 2 * s)], dark)
        glass = (self.lit((70, 80, 92), (0, 1, 0.3)) * (1 - self.night) + np.array([255, 236, 200]) * self.night)
        L.poly([(lx - 6 * s, ty - 2 * s), (lx + 6 * s, ty - 2 * s), (lx + 6 * s, ty - 13 * s), (lx - 6 * s, ty - 13 * s)], glass)
        L.poly([(lx - 8 * s, ty - 13 * s), (lx + 8 * s, ty - 13 * s), (lx, ty - 21 * s)], dark)
        L.composite()
        self.lamp_lh = (lx, ty - 7.5 * s)

    def far_coast(self):
        W, H, s = self.W, self.H, self.s
        x0, x1 = 0.15, 0.52
        t = np.linspace(0, 1, 600)
        hgt = (0.006 + 0.004 * np.interp(t, np.linspace(0, 1, 1024), fnoise(4, 1024, 2.2, 1, 25)[1])) * sm(0, 0.15, t) * sm(1, 0.8, t)
        pts = [((x0 + (x1 - x0) * ti) * W, (VH - hi) * H) for ti, hi in zip(t, hgt)] + [(x1 * W, VH * H + 1), (x0 * W, VH * H + 1)]
        L = Layer(self, x0 * W, (VH - 0.02) * H, x1 * W, VH * H + 2)
        land = self.lit((70, 84, 70), (0, 0.3, 0.95))
        haze = 0.72 - 0.2 * self.night
        L.poly(pts, land * (1 - haze) + self.hor_col * haze)
        L.composite()

    def beams(self):
        if self.sun_alt > -2.5:
            return
        k = sm(-2.5, -9, self.sun_alt)
        s, W, H = self.s, self.W, self.H
        lx, ly = self.lamp_lh
        phi = math.radians((self.h * 47 + 30) % 360)
        colr = np.array([255, 206, 160], np.float32)
        for p in (phi, phi + math.pi):
            dx, dy = math.cos(p), 0.05 * math.sin(p)
            nrm = math.hypot(dx, dy)
            dx, dy = dx / nrm, dy / nrm
            reach = 0.30 * W * (0.25 + 0.75 * abs(math.cos(p)))
            ex = lx + dx * reach * 2.5
            x0, x1 = int(max(0, min(lx, ex) - 20 * s)), int(min(W, max(lx, ex) + 20 * s))
            y0, y1 = int(max(0, ly - 0.08 * H)), int(min(self.hz, ly + 0.05 * H))
            X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - lx
            Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - ly
            along = X * dx + Y * dy
            perp = np.abs(-X * dy + Y * dx)
            width = 3 * s + np.maximum(along, 0) * 0.035
            I = np.exp(-(perp / width) ** 2) * np.exp(-np.maximum(along, 0) / reach) * sm(0, 25 * s, along)
            self.c[y0:y1, x0:x1] += I[..., None] * colr * 0.28 * k
        toward = abs(math.sin(phi)) ** 3
        self.glow(lx, ly, 3.5 * s, (255, 240, 215), 1.6 * k)
        self.glow(lx, ly, 26 * s, colr, (0.18 + 0.5 * toward) * k, tail=0.3)
        self.emitters.append((lx, ly, colr, (0.9 + 0.8 * toward) * k, self.hz))

    # ---------------------------------------------------------------- sea --
    def plan_emitters(self):
        s, W, H = self.s, self.W, self.H
        if self.lights_on > 0:
            px, py = self.pier_lantern()
            self.emitters.append((px, py, np.array([255, 196, 120], np.float32), 1.2 * self.lights_on, self.pier_water_y()))
        if self.h >= 18 or self.h <= 6:
            bx, by = MOORED[0] * W, MOORED[1] * H
            sz = 170 * s
            if self.night > 0:
                self.emitters.append((bx + 0.05 * sz, by - 1.22 * sz, np.array([230, 235, 255], np.float32), 0.5 * self.night, by + 0.1 * sz))

    def pier_lantern(self):
        (ax, ay), (bx, by) = PIER[0], PIER[1]
        x, y = bx * self.W - 4 * self.s, by * self.H - 64 * self.s * 0.45
        return x, y

    def pier_water_y(self):
        return PIER[1][1] * self.H + 10 * self.s

    def sea(self):
        W, H, hz, s = self.W, self.H, self.hz, self.s
        rows = np.arange(hz, H, dtype=np.float32) + 0.5
        ad = (rows - VH * H) / (VH * H) * ALT_TOP
        Z = 1.0 / np.tan(np.radians(np.maximum(ad, 0.05)))
        xa = ((np.arange(W, dtype=np.float32) + 0.5) / W - 0.5) * math.radians(AZ_SPAN)
        Xw = Z[:, None] * xa[None, :]
        R, C = np.repeat(Z[:, None] * 30.0, W, 1), Xw * 30.0
        fade = sm(0.2, 3.0, ad)[:, None]
        w = sample(fnoise(512, 2048, 2.6, 5.0, 9), R, C) * fade
        rp = sample(fnoise(512, 2048, 1.4, 2.5, 10), R * 3.6, C * 3.6) * fade
        spark = np.clip(rp - 0.9, 0, None) ** 1.5 * 2.0
        off = w * (1.0 + ad[:, None] * 2.0) * s * 1.5
        xj = np.clip((np.arange(W)[None, :] + (w * 2 + rp * (1 + ad[:, None] * 0.25)) * s * 2).astype(np.int32), 0, W - 1)
        refl = 0
        for k in (0.5, 1.0, 1.7):
            ri = np.clip((2 * VH * H - rows[:, None] - off * k).astype(np.int32), 0, hz - 1)
            refl = refl + self.c[ri, xj] / 3
        f = (0.1 + 0.85 * np.exp(-ad / 5.5))[:, None, None]
        body = WATER * (self.amb + 0.35 * self.sun_col * self.sun_str + 0.2 * MOON_COL * self.moon_str)
        sea = refl * f * 0.95 + body * (1 - f)
        sea *= (1 + 0.10 * w)[..., None]
        spark = np.clip(rp - 0.9, 0, None) ** 1.5 * 2.0
        Xs = np.arange(W, dtype=np.float32)[None, :]

        def path(src_alt, src_x, colr, k, wm):
            sig = (5 + ad[:, None] * 2.8) * s * wm * (1 + max(src_alt, 0) / 18)
            horiz = np.exp(-((Xs - src_x) / sig) ** 2)
            ctr, spread = max(src_alt, 0.6), 2.5 + 0.55 * max(src_alt, 0)
            vert = np.exp(-((ad[:, None] - ctr) / spread) ** 2) + 0.25 * np.exp(-ad[:, None] / (3 + ctr))
            return (horiz * vert * (0.25 + spark) * k)[..., None] * np.asarray(colr, np.float32)

        if self.sun_alt > -1:
            sx = to_screen(self.sun_alt, self.sun_az)[0] * W
            sea += path(self.sun_alt, sx, keys(SUN_DISK, self.sun_alt),
                        1.2 * sm(-1, 3, self.sun_alt) * (1.2 - 0.5 * sm(10, 40, self.sun_alt)), 1.0)
        if self.moon_alt > -1 and self.night > 0:
            mx = to_screen(self.moon_alt, self.moon_az)[0] * W
            sea += path(self.moon_alt, mx, (225, 230, 245), 0.65 * self.night * sm(-1, 6, self.moon_alt), 0.8)
        for (ex, ey, ecol, es, wy) in self.emitters:
            r0 = int(wy) - hz
            length = max(12 * s, (wy - ey) * 1.8) + 30 * s
            c0, c1 = int(max(0, ex - 60 * s)), int(min(W, ex + 60 * s))
            ra, rb = max(0, r0), int(min(H - hz, r0 + length * 5))
            if c0 >= c1 or ra >= rb:
                continue
            rr = np.arange(ra, rb, dtype=np.float32)[:, None] - r0
            prof = np.exp(-rr / length)
            sigx = 2.5 * s + rr * 0.03
            hx = np.exp(-((np.arange(c0, c1, dtype=np.float32)[None, :] - ex) / sigx) ** 2)
            sea[ra:rb, c0:c1] += (prof * hx * (0.35 + spark[ra:rb, c0:c1] * 1.5) * es)[..., None] * ecol
        self.c[hz:] = sea
        self.wave = w

    def mist(self):
        m = 0.9 * math.exp(-((self.h - 6) / 1.3) ** 2) + 0.4 * math.exp(-((self.h - 19.5) / 1.0) ** 2)
        if m < 0.03:
            return
        H, W, hz = self.H, self.W, self.hz
        y0, y1 = int(hz - 0.05 * H), int(min(H, hz + 0.09 * H))
        rows = np.arange(y0, y1, dtype=np.float32)[:, None]
        prof = np.exp(-((rows - hz) / (0.025 * H)) ** 2)
        tex = fnoise(256, 2048, 2.2, 4.0, 31)
        n = sample(tex, np.repeat((rows - y0) * 256 / (y1 - y0), W, 1), np.repeat(np.arange(W, dtype=np.float32)[None, :] * 2048 / W, y1 - y0, 0))
        a = (prof * sm(-0.8, 1.2, n) * 0.55 * m)[..., None]
        mc = self.hor_col * 0.6 + np.array([225, 225, 235], np.float32) * 0.4 * (0.4 + 0.6 * self.amb.mean() / 0.5)
        reg = self.c[y0:y1]
        reg[:] = reg * (1 - a) + mc * a

    # --------------------------------------------------------------- boats --
    def boat(self, cx, cy, size, facing, sails, masthead=False):
        s = self.s
        L = Layer(self, cx - size * 0.8, cy - size * 1.35, cx + size * 0.8, cy + size * 0.3)
        f = facing

        def P(x, y):
            return (cx + f * x * size, cy + y * size)
        side = normalize([0, 1, 0.2])
        seacol = self.c[min(self.H - 1, int(cy + 0.12 * size)), int(np.clip(cx, 0, self.W - 1))]
        L.poly([P(-0.40, 0.10), P(0.42, 0.10), P(0.32, 0.17), P(-0.30, 0.17)], seacol * 0.6, a=0.6)
        L.poly([P(-0.46, -0.05), P(0.56, -0.07), P(0.40, 0.10), P(-0.38, 0.09)], self.lit((228, 226, 220), side))
        L.poly([P(-0.44, 0.00), P(0.50, -0.01), P(0.47, 0.025), P(-0.43, 0.035)], self.lit((40, 52, 84), side))
        L.poly([P(-0.20, -0.05), P(0.10, -0.06), P(0.08, -0.13), P(-0.17, -0.13)], self.lit((214, 208, 196), [0, .8, .6]))
        L.line([P(0.05, -0.06), P(0.05, -1.20)], self.lit((70, 62, 55), side), max(1.0, size * 0.018))
        if sails:
            back = max(0.0, -float(self.sunv[1])) * self.sun_str * 0.35
            sail = self.lit((240, 236, 222), [-f * 0.3, 0.8, 0.3]) + np.array([255, 220, 170]) * back * self.sun_col
            L.poly([P(0.035, -1.16), P(0.035, -0.13), P(-0.40, -0.13)], sail)
            L.poly([P(0.07, -1.05), P(0.55, -0.09), P(0.07, -0.10)], sail * 0.94)
            L.line([P(0.05, -0.12), P(-0.42, -0.12)], self.lit((70, 62, 55), side), max(1.0, size * 0.014))
        else:
            L.line([P(0.05, -0.16), P(-0.36, -0.14)], self.lit((200, 196, 186), side), max(1.0, size * 0.03))
        L.composite()
        if masthead and self.night > 0:
            x, y = P(0.05, -1.22)
            self.glow(x, y, 2.2 * s, (235, 240, 255), 1.4 * self.night)
            self.glow(x, y, 9 * s, (200, 215, 255), 0.18 * self.night)

    def boats(self):
        s, W, H = self.s, self.W, self.H
        if self.h in BOAT_DAY:
            x, y = BOAT_DAY[self.h]
            nxt = BOAT_DAY.get(self.h + 1, MOORED)
            facing = 1 if nxt[0] >= x else -1
            size = 170 * s * (y - VH) / (MOORED[1] - VH)
            self.boat(x * W, y * H, size, facing, True)

    def moored_boat(self):
        if self.h in BOAT_DAY:
            return
        self.boat(MOORED[0] * self.W, MOORED[1] * self.H, 170 * self.s, -1, False, masthead=True)

    # --------------------------------------------------------------- hill --
    def casters(self):
        s, W, H = self.s, self.W, self.H
        tw = self.tw
        out = []
        foot = [(tw["cx"] + tw["r"] * math.cos(a), tw["yb"] + tw["r"] * 0.22 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 24)]
        out.append((foot, tw["yb"] - tw["yt"] + tw["r"] * 1.1))
        bx, by = BENCH[0] * W, BENCH[1] * H
        out.append(([(bx - 96 * s, by), (bx + 96 * s, by), (bx + 96 * s, by - 8 * s), (bx - 96 * s, by - 8 * s)], 70 * s))
        lx, ly = LAMP[0] * W, LAMP[1] * H
        out.append(([(lx - 4 * s, ly), (lx + 4 * s, ly), (lx, ly - 3 * s)], LAMP[2] * s))
        tx, ty = TREE_BASE[0] * W, TREE_BASE[1] * H
        out.append(([(tx - 16 * s, ty), (tx + 16 * s, ty), (tx, ty - 5 * s)], ty - (CANOPY[1] * H + CANOPY[3] * s * 0.6)))
        return out

    def shadow_masks(self):
        W, H, s = self.W, self.H, self.s
        q = 4
        sw, sh = W // q + 1, H // q + 1
        sim, aim = Image.new("L", (sw, sh), 0), Image.new("L", (sw, sh), 0)
        ds, da = ImageDraw.Draw(sim), ImageDraw.Draw(aim)
        src = None
        if self.sun_alt > 1:
            src = (self.sun_alt, self.sun_az, 0.82)
        elif self.moon_alt > 4 and self.sun_alt < -6:
            src = (self.moon_alt, self.moon_az, 0.6)
        tw = self.tw
        # contact shadows (ambient occlusion)
        tx, ty = TREE_BASE[0] * W, TREE_BASE[1] * H
        for (cx, cy, rx, ry, v) in [(tw["cx"], tw["yb"] + 4 * s, tw["r"] * 1.15, tw["r"] * 0.2, 150),
                                    (tx, ty, 40 * s, 10 * s, 150), (BENCH[0] * W, BENCH[1] * H, 100 * s, 9 * s, 110),
                                    (LAMP[0] * W, LAMP[1] * H, 14 * s, 4 * s, 120)]:
            da.ellipse([(cx - rx) / q, (cy - ry) / q, (cx + rx) / q, (cy + ry) / q], fill=v)
        if src:
            alt, az, k = src
            cot = min(1 / math.tan(math.radians(alt)), 3.0)
            sx, sy = math.sin(math.radians(az)) * cot, -math.cos(math.radians(az)) * cot * KF
            for foot, h in self.casters():
                pts = foot + [(x + sx * h, y + sy * h) for x, y in foot]
                ds.polygon([(x / q, y / q) for x, y in hull(pts)], fill=int(255 * k))
            # the canopy
            Rx, Ry = CANOPY[2] * s, CANOPY[3] * s
            hc = ty - CANOPY[1] * H
            cx, cy = tx + sx * hc, ty + sy * hc
            rx = Rx * (1 + 0.35 * min(abs(sx), 2))
            ry = Rx * KF * 1.4 * (1 + 0.35 * min(abs(sy) / KF, 2))
            cim = Image.new("L", (sw, sh), 0)
            ImageDraw.Draw(cim).ellipse([(cx - rx) / q, (cy - ry) / q, (cx + rx) / q, (cy + ry) / q], fill=int(255 * k * 0.72))
            can = np.asarray(cim, np.float32) / 255
            dap = fnoise(sh, sw, 1.4, 1.0, 55)
            can *= np.clip(0.7 + 0.4 * dap, 0, 1)
            shade = np.maximum(np.asarray(sim, np.float32) / 255, can)
        else:
            shade = np.zeros((sh, sw), np.float32)
        shade = ndi.gaussian_filter(shade, 1.6)
        ao = ndi.gaussian_filter(np.asarray(aim, np.float32) / 255, 2.5)
        up = lambda a: np.asarray(Image.fromarray(a).resize((W, H), Image.BILINEAR), np.float32)
        return up(shade), up(ao)

    def bezier(self, p0, p1, p2, p3, n=120):
        t = np.linspace(0, 1, n)[:, None]
        P = [np.array(p) for p in (p0, p1, p2, p3)]
        return (1 - t) ** 3 * P[0] + 3 * (1 - t) ** 2 * t * P[1] + 3 * (1 - t) * t ** 2 * P[2] + t ** 3 * P[3]

    def ribbon(self, pts, w0, w1):
        d = np.gradient(pts, axis=0)
        d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-6
        nrm = np.stack([-d[:, 1], d[:, 0]], 1)
        w = np.linspace(w0, w1, len(pts))[:, None]
        left, right = pts + nrm * w, pts - nrm * w
        return [tuple(p) for p in left] + [tuple(p) for p in right[::-1]]

    def hill(self):
        W, H, s = self.W, self.H, self.s
        xd, yd = self._edge
        x1 = W
        y0 = int((yd.min() - 0.012) * H)
        hh, hw = H - y0, x1
        r = np.random.default_rng(31)
        xs = np.arange(0, x1, 1.0 * s + 0.5)
        ex = self.edge(xs / W) * H
        poly = [(0, H + 2), (0, ex[0])] + list(zip(xs, ex)) + [(x1, H + 2)]
        M = Layer(self, 0, y0, x1, H)
        M.poly(poly, (255, 255, 255))
        A = Layer(self, 0, y0, x1, H)   # albedo overlay (path, flowers, blades ...)

        def persp(y):
            return 0.35 + 1.3 * np.clip((y / H - 0.6) / 0.4, 0, 1)

        # the path to the door, and a worn trail to the bench
        tw = self.tw
        p = self.bezier((0.10 * W, 1.03 * H), (0.15 * W, 0.80 * H), (0.27 * W, 0.71 * H), (tw["cx"], tw["yb"] + 10 * s))
        A.poly(self.ribbon(p, 0.038 * W, 0.009 * W), (150, 128, 98))
        q = self.bezier((0.205 * W, 0.80 * H), (0.30 * W, 0.755 * H), (0.40 * W, 0.735 * H), (BENCH[0] * W, BENCH[1] * H + 6 * s))
        A.poly(self.ribbon(q, 0.007 * W, 0.004 * W), (126, 124, 84), a=0.35)
        for _ in range(900):   # pebbles
            i = r.integers(0, len(p))
            t = i / len(p)
            w = (0.038 - 0.029 * t) * W
            px, py = p[i] + r.uniform(-w * 0.9, w * 0.9, 2) * np.array([1, 0.35])
            rr = r.uniform(1.0, 3.2) * s * persp(py)
            A.ellipse(px, py, rr, rr * 0.6, np.array([150, 128, 98]) * r.uniform(0.75, 1.25))
        # rocks by the shore and the path
        for (rx, ry, rs) in [(0.612, 0.768, 18), (0.628, 0.79, 11), (0.66, 0.86, 22), (0.69, 0.93, 16),
                             (0.09, 0.93, 26), (0.205, 0.83, 12), (0.36, 0.69, 9), (0.80, 0.93, 30), (0.93, 0.95, 22)]:
            cx, cy, rs = rx * W, ry * H, rs * s
            A.ellipse(cx, cy, rs, rs * 0.62, (112, 110, 104))
            A.ellipse(cx - rs * 0.15, cy - rs * 0.18, rs * 0.75, rs * 0.4, (150, 146, 138))
        # boulders along the waterline
        def band(xn):
            return 0.030 * H * sm(0.57, 0.66, xn)
        x = 0.575 * W
        while x < 1.0 * W:
            x += r.choice([4, 6, 9, 14, 30, 55]) * s
            e = self.edge(x / W) * H
            if e > H + 20 * s:
                continue
            by_ = e + r.uniform(0.0, 0.9) * band(x / W)
            rs = (r.uniform(20, 36) if r.random() < 0.12 else r.uniform(5, 14)) * s * persp(by_)
            dark = np.array([72, 68, 64]) * r.uniform(0.8, 1.2)
            for lay in (A, M):
                lay.ellipse(x, by_, rs, rs * 0.7, dark if lay is A else (255, 255, 255))
            A.ellipse(x - rs * 0.18, by_ - rs * 0.22, rs * 0.72, rs * 0.42, dark * 1.4)
            A.ellipse(x - rs * 0.3, by_ - rs * 0.34, rs * 0.3, rs * 0.16, dark * 1.7)
        # fallen leaves under the tree: it is late September
        tx, ty = TREE_BASE[0] * W, TREE_BASE[1] * H
        for _ in range(160):
            lx, ly = tx + r.normal(0, 70 * s), ty + abs(r.normal(0, 22 * s)) - 6 * s
            c = [(196, 150, 58), (205, 112, 48), (170, 90, 40), (150, 130, 50)][r.integers(0, 4)]
            A.ellipse(lx, ly, 2.6 * s, 1.4 * s, c)
        # wildflowers, in drifts
        fl = fnoise(64, 128, 2.0, 1.0, 33)
        n = 0
        while n < 1500:
            fx, fy = r.uniform(0, 1.0), r.uniform(0.61, 1.0)
            if fy * H < self.edge(fx) * H + 4 * s + band(fx) or fl[int((fy - 0.6) / 0.4 * 63), int(fx * 127)] < 0.4:
                continue
            c = [(242, 240, 230), (240, 206, 70), (176, 146, 214), (230, 120, 150)][r.integers(0, 4) if r.random() < 0.8 else 0]
            rr = r.uniform(1.2, 2.4) * s * persp(fy * H)
            A.ellipse(fx * W, fy * H, rr, rr, c)
            n += 1
        # a dry-stone wall across the lower field, open where the path crosses
        for seg in (self.bezier((-0.02 * W, 0.742 * H), (0.04 * W, 0.76 * H), (0.10 * W, 0.79 * H), (0.148 * W, 0.812 * H), 70),
                    self.bezier((0.196 * W, 0.826 * H), (0.25 * W, 0.845 * H), (0.30 * W, 0.88 * H), (0.34 * W, 0.95 * H), 70)):
            d = np.cumsum(np.r_[0, np.linalg.norm(np.diff(seg, axis=0), axis=1)])
            for row in range(4):
                u = r.uniform(0, 8) * s
                while u < d[-1]:
                    x, y = np.interp(u, d, seg[:, 0]), np.interp(u, d, seg[:, 1])
                    hgt = 26 * s * persp(y)
                    sw_ = r.uniform(7, 13) * s * persp(y)
                    yy = y - hgt * (row + 0.5) / 4
                    c = np.array([128, 124, 114]) * r.uniform(0.7, 1.2) * (0.8 + 0.08 * row)
                    A.ellipse(x, yy, sw_ * 0.55, hgt * 0.16, c)
                    u += sw_ * r.uniform(0.8, 1.05)
            for u in np.arange(0, d[-1], 9 * s):   # capstones, lit from above
                x, y = np.interp(u, d, seg[:, 0]), np.interp(u, d, seg[:, 1])
                hgt = 26 * s * persp(y)
                A.ellipse(x, y - hgt, 6 * s * persp(y), 3 * s * persp(y), np.array([150, 146, 136]) * r.uniform(0.85, 1.15))
        # tufts across the slope
        for _ in range(int(9000)):
            gx, gy = r.uniform(0, x1), r.uniform(y0, H)
            if gy < self.edge(gx / W) * H + 3 * s + band(gx / W):
                continue
            ln = r.uniform(4, 11) * s * persp(gy)
            c = np.array([[58, 90, 40], [84, 112, 48], [108, 124, 60], [146, 136, 80]][r.integers(0, 4)]) * r.uniform(0.8, 1.15)
            for k in range(3):
                lean = r.uniform(-0.5, 0.5) * ln
                A.line([(gx + k * 1.5 * s, gy), (gx + k * 1.5 * s + lean, gy - ln)], c, 1.1 * s)
        # blades along the crest, against the sea
        for x in np.arange(0, 0.60 * W, 2.2 * s):
            y = self.edge(x / W) * H + 2 * s
            ln = r.uniform(4, 14) * s * persp(y)
            lean = r.uniform(-4, 4) * s
            c = np.array([[52, 84, 38], [74, 104, 44], [98, 118, 54], [140, 132, 76]][r.integers(0, 4)]) * r.uniform(0.85, 1.1)
            A.line([(x, y), (x + lean, y - ln)], c, 1.3 * s)
            M.line([(x, y), (x + lean, y - ln)], (255, 255, 255), 1.3 * s)
        _, mask = M.arrays()
        orgb, oal = A.arrays()

        g1 = fnoise(hh, hw, 2.4, 1.6, 101)
        g2 = fnoise(hh, hw, 1.0, 1.0, 102)
        g3 = fnoise(hh, hw, 1.6, 0.25, 103)
        dry = sm(0.1, 1.4, fnoise(hh, hw, 2.8, 1.3, 104))[..., None] * 0.75
        alb = np.array([58, 80, 40], np.float32) + np.array([46, 34, 18], np.float32) * sm(-1.5, 1.5, g1)[..., None]
        alb = alb * (1 - dry) + np.array([156, 142, 92], np.float32) * dry
        alb *= (1 + 0.07 * g2 + 0.09 * g3)[..., None]
        Yg = np.arange(y0, H, dtype=np.float32)[:, None] + 0.5
        xn = np.arange(x1, dtype=np.float32) / W
        shore = sm(0.0, 0.4, 1 - (Yg - self.edge(xn)[None, :] * H) / (band(xn)[None, :] + 1e-3)) * sm(0.56, 0.60, xn)[None, :]
        sand = np.array([112, 104, 90], np.float32) * (1 + 0.12 * g2 + 0.08 * g1)[..., None]
        alb = alb * (1 - shore[..., None]) + sand * shore[..., None]
        alb = alb * (1 - oal) + orgb * oal
        gy, gx = np.gradient(g1)
        k = 0.15 / (np.std(gx) + 1e-6)
        nrm = normalize(np.stack([-gx * k, -0.34 + gy * k, np.full_like(gx, 0.94)], -1))
        shade, ao = self.shade[y0:H, :x1], self.ao[y0:H, :x1]
        L = self.light(nrm, shade, 1 - 0.55 * ao)
        if self.pools:
            X = np.arange(x1, dtype=np.float32)[None, :] + 0.5
            Y = np.arange(y0, H, dtype=np.float32)[:, None] + 0.5
            L = L + self.local(X, Y, ground=True)
        col = alb * L
        Y = (np.arange(y0, H, dtype=np.float32)[:, None] + 0.5)
        crest = (sm(0.05 * H, 0, Y - self.edge(np.arange(x1) / W)[None, :] * H) * 0.12)[..., None]
        col = col * (1 - crest) + self.hor_col * crest
        reg = self.c[y0:H, :x1]
        reg[:] = reg * (1 - mask) + col * mask

    def foam(self):
        W, H, s = self.W, self.H, self.s
        r = np.random.default_rng(41)
        L = Layer(self, 0.5 * W, 0.6 * H, W, H)
        fc = self.lit((225, 232, 235), (0, 0.3, 1))
        for x in np.arange(0.52 * W, 1.0 * W, 3 * s):
            y = self.edge(x / W) * H
            if r.random() < 0.35:
                continue
            L.line([(x, y - r.uniform(1, 5) * s), (x + r.uniform(4, 14) * s, y - r.uniform(0, 4) * s)], fc, 1.4 * s, a=r.uniform(0.3, 0.8))
        L.composite()

    # -------------------------------------------------------------- tower --
    def cylinder(self, cx, yt, yb, rt, rb, albedo_fn, haze=0.0, local=True, ell_k=1.2):
        rmax = max(rt, rb)
        et = ell_k * (yt / self.H - VH) * rt
        eb = ell_k * (yb / self.H - VH) * rb
        x0, x1 = int(max(0, cx - rmax - 2)), int(min(self.W, cx + rmax + 3))
        y0, y1 = int(max(0, yt - abs(et) - 3)), int(min(self.H, yb + abs(eb) + 3))
        X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
        Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
        v0 = np.clip((Y - yt) / (yb - yt), 0, 1)
        r = rt + (rb - rt) * v0
        dx = X - cx
        sv = np.clip(dx / r, -1, 1)
        cv = np.sqrt(1 - sv ** 2)
        top, bot = yt + et * cv, yb + eb * cv
        cov = np.clip(r - np.abs(dx) + 0.5, 0, 1) * np.clip(Y - top + 0.5, 0, 1) * np.clip(bot - Y + 0.5, 0, 1)
        v = np.clip((Y - top) / (bot - top), 0, 1)
        alb = albedo_fn(sv, v, X, Y, r)
        nrm = np.stack([-sv, cv, np.zeros_like(sv)], -1)
        L = self.light(nrm) * (0.8 + 0.2 * cv)[..., None]
        if local and self.pools:
            L = L + self.local(X, Y)
        col = alb * L
        if haze:
            col = col * (1 - haze) + self.hor_col * haze
        a = cov[..., None]
        reg = self.c[y0:y1, x0:x1]
        reg[:] = reg * (1 - a) + col * a

    def tower(self):
        s, W, H = self.s, self.W, self.H
        tw = self.tw
        cx, yb, yt, r = tw["cx"], tw["yb"], tw["yt"], tw["r"]
        tex = fnoise(512, 512, 2.0, 1.0, 71)
        tex2 = fnoise(512, 512, 1.4, 1.0, 72)

        def stone(sv, v, X, Y, rr):
            arc = np.arcsin(sv) * rr
            hp = v * (yb - yt)
            ch, sw = 21 * s, 46 * s
            ci = np.floor(hp / ch)
            fy = hp / ch - ci
            sx = (arc + hash2(ci, 7) * sw) / sw
            si = np.floor(sx)
            fx = sx - si
            tint = hash2(ci, si)
            ep = np.minimum(np.minimum(fy, 1 - fy) * ch, np.minimum(fx, 1 - fx) * sw * np.sqrt(1 - sv ** 2) + 1e-3)
            mort = sm(2.2 * s, 0.7 * s, ep)[..., None]
            n1 = sample(tex, Y * 0.5 / s + 0 * X, X * 0.5 / s + 0 * Y)
            n2 = sample(tex2, Y * 1.5 / s + 0 * X, X * 1.5 / s + 0 * Y)
            base = np.array([150, 140, 124], np.float32) + np.array([36, 36, 32], np.float32) * tint[..., None]
            base = base * (1 + 0.07 * n1 + 0.05 * n2)[..., None] * (1 + 0.06 * (0.5 - fy))[..., None]
            col = base * (1 - mort) + np.array([112, 104, 92], np.float32) * mort
            moss = (sm(0.72, 1.0, v) * sm(-0.2, 0.9, n1) * 0.5)[..., None]
            col = col * (1 - moss) + np.array([78, 98, 54], np.float32) * moss
            under = (0.72 + 0.28 * sm(0, 0.05, v))[..., None]
            return col * under
        self.cylinder(cx, yt, yb, r, r * 1.03, stone)
        # dome, then the cornice ring that it sits on
        cy = yt - 16 * s
        self.dome(cx, cy, r * 0.99)

        def cornice(sv, v, X, Y, rr):
            arc = np.arcsin(sv) * rr
            fx = (arc / (16 * s)) % 1.0
            dent = ((fx < 0.35) & (v > 0.62))[..., None]
            base = np.array([198, 190, 172], np.float32) * (1 - 0.1 * (v > 0.55))[..., None]
            return np.where(dent, base * 0.55, base)
        self.cylinder(cx, cy, yt + 8 * s, r * 1.08, r * 1.08, cornice)
        self.telescope(cx, cy, r * 0.99)
        self.tower_details()

    def dome(self, cx, cy, R):
        s = self.s
        x0, x1 = int(cx - R - 2), int(cx + R + 3)
        y0, y1 = int(cy - R - 2), int(cy + 0.35 * R)
        X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
        Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
        sx, sy = [np.ascontiguousarray(a) for a in np.broadcast_arrays((X - cx) / R, (cy - Y) / R)]
        rho = np.sqrt(sx ** 2 + sy ** 2)
        cov = np.clip((1 - rho) * R + 0.5, 0, 1) * (sy > -0.3)
        z = np.sqrt(np.clip(1 - rho ** 2, 0, 1))
        nrm = np.stack([-sx, z, sy], -1)
        lon = np.degrees(np.arctan2(sx, z))
        lat = np.arcsin(np.clip(sy, -1, 1))
        streak = sample(fnoise(256, 256, 2.0, 0.12, 61), Y * 0.6 / s + 0 * X, X * 0.6 / s + 0 * Y)
        alb = np.array([80, 142, 120], np.float32) * (1 + 0.13 * streak)[..., None]
        ribd = np.abs(((lon + 11.25) % 22.5) - 11.25) * math.pi / 180 * R * np.cos(lat)
        rib = sm(1.6 * s, 0.4 * s, ribd)[..., None]
        alb = alb * (1 - 0.45 * rib)
        spec_dir = normalize(self.sunv + np.array([0, 1, 0], np.float32))
        spec = np.clip(nrm @ spec_dir, 0, 1) ** 40 * self.sun_str * 0.5
        col = alb * self.light(nrm) + spec[..., None] * 255 * self.sun_col
        if self.observing:
            mx, my = to_screen(self.moon_alt, self.moon_az)
            th = math.atan2(cy - my * self.H, mx * self.W - cx)
            th = min(max(th, math.radians(25)), math.radians(155))
            self.scope_theta = th
            phi = np.arctan2(sy, sx)
            dphi = np.degrees(np.abs((phi - th + math.pi) % (2 * math.pi) - math.pi))
            wedge = sm(5.0, 3.8, dphi) * (rho > 0.1)
            inner = np.array([18, 6, 5], np.float32) + np.array([100, 26, 18], np.float32) * np.clip(1 - rho, 0, 1)[..., None] ** 0.7
            col = col * (1 - wedge[..., None]) + inner * wedge[..., None]
            self.slit = (x0, y0, x1, y1, wedge, rho)
        else:
            self.scope_theta = None
            seam = sm(1.4 * s, 0.3 * s, np.abs(np.abs(sx) - 0.1 * z) * R)[..., None] * (sy > 0)[..., None]
            col = col * (1 - 0.35 * seam)
        a = cov[..., None]
        reg = self.c[y0:y1, x0:x1]
        reg[:] = reg * (1 - a) + col * a
        L = Layer(self, cx - 12 * s, cy - R - 26 * s, cx + 12 * s, cy - R + 4 * s)
        brass = self.lit((176, 136, 64), (0, 0.6, 0.8))
        L.line([(cx, cy - R + 2 * s), (cx, cy - R - 22 * s)], brass * 0.8, 2.2 * s)
        L.ellipse(cx, cy - R - 6 * s, 5.5 * s, 5.5 * s, brass)
        L.composite()

    def telescope(self, cx, cy, R):
        th = self.scope_theta
        if th is None:
            return
        s = self.s
        ux, uy = math.cos(th), -math.sin(th)
        px, py = -uy, ux
        a0, a1 = 0.05 * R, 1.04 * R
        w = 0.085 * R
        L = Layer(self, cx - 1.5 * R, cy - 1.5 * R, cx + 1.5 * R, cy + 0.3 * R)
        brass = self.lit((120, 124, 134), (ux * 0.3, 0.5, 0.8)) + np.array([14, 4, 3])
        L.poly([(cx + ux * a0 + px * w, cy + uy * a0 + py * w), (cx + ux * a1 + px * w, cy + uy * a1 + py * w),
                (cx + ux * a1 - px * w, cy + uy * a1 - py * w), (cx + ux * a0 - px * w, cy + uy * a0 - py * w)], brass)
        a2 = a1 + 0.16 * R
        w2 = w * 1.25
        L.poly([(cx + ux * a1 + px * w2, cy + uy * a1 + py * w2), (cx + ux * a2 + px * w2, cy + uy * a2 + py * w2),
                (cx + ux * a2 - px * w2, cy + uy * a2 - py * w2), (cx + ux * a1 - px * w2, cy + uy * a1 - py * w2)], brass * 0.8)
        ring = self.lit((150, 132, 96), (ux * 0.3, 0.5, 0.8)) + np.array([60, 66, 84]) * self.moon_str
        am = a1 - 0.25 * R
        L.poly([(cx + ux * am + px * w * 1.1, cy + uy * am + py * w * 1.1), (cx + ux * (am + 0.05 * R) + px * w * 1.1, cy + uy * (am + 0.05 * R) + py * w * 1.1),
                (cx + ux * (am + 0.05 * R) - px * w * 1.1, cy + uy * (am + 0.05 * R) - py * w * 1.1), (cx + ux * am - px * w * 1.1, cy + uy * am - py * w * 1.1)], ring)
        L.line([(cx + ux * a0 + px * w * 0.5, cy + uy * a0 + py * w * 0.5), (cx + ux * a1 + px * w * 0.5, cy + uy * a1 + py * w * 0.5)],
               brass * 1.4 + np.array([60, 66, 84]) * self.moon_str, 1.4 * s)
        # visible through the open slit, or where it pokes out beyond the dome
        X = np.arange(L.x0, L.x1, dtype=np.float32)[None, :] + 0.5
        Y = np.arange(L.y0, L.y1, dtype=np.float32)[:, None] + 0.5
        rho = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) / R
        allow = np.clip((rho - 1) * R + 0.5, 0, 1)
        x0, y0, x1, y1, wedge, _ = self.slit
        ax0, ay0 = max(L.x0, x0), max(L.y0, y0)
        ax1, ay1 = min(L.x1, x1), min(L.y1, y1)
        allow[ay0 - L.y0:ay1 - L.y0, ax0 - L.x0:ax1 - L.x0] = np.maximum(
            allow[ay0 - L.y0:ay1 - L.y0, ax0 - L.x0:ax1 - L.x0], wedge[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0])
        allow *= (Y < cy + 2 * s)
        L.composite(allow=allow)

    def tower_details(self):
        s, W, H, h = self.s, self.W, self.H, self.h
        tw = self.tw
        cx, yb, yt, r = tw["cx"], tw["yb"], tw["yt"], tw["r"]
        on = self.lights_on
        L = Layer(self, cx - r * 1.1, yt - 10 * s, cx + r * 1.1, yb + 30 * s)
        front = normalize([0, 1, 0.1])
        stone_hi = self.lit((200, 192, 176), front, cx, yb - 60 * s)
        # windows
        wins = []
        for sv, wy in ((-0.52, 0.548), (0.52, 0.548)):
            k = math.sqrt(1 - sv * sv)
            nrm = normalize([-sv, k, 0.05])
            wx, wy = cx + sv * r, wy * H
            ww, wh = 13 * s * k, 40 * s
            surround = self.lit((196, 188, 170), nrm, wx, wy)
            L.poly([(wx - ww - 6 * s * k, wy + wh + 5 * s), (wx + ww + 6 * s * k, wy + wh + 5 * s),
                    (wx + ww + 6 * s * k, wy - wh), (wx - ww - 6 * s * k, wy - wh)], surround)
            L.ellipse(wx, wy - wh, ww + 6 * s * k, ww + 6 * s * k, surround)
            glass = self.lit((42, 50, 62), nrm) + self.amb * 30
            glass = glass * (1 - on) + np.array([255, 190, 112], np.float32) * on
            L.poly([(wx - ww, wy + wh), (wx + ww, wy + wh), (wx + ww, wy - wh), (wx - ww, wy - wh)], glass)
            L.ellipse(wx, wy - wh, ww, ww, glass)
            mull = self.lit((60, 52, 44), nrm)
            L.line([(wx, wy - wh - ww), (wx, wy + wh)], mull, 2.2 * s)
            L.line([(wx - ww, wy + 2 * s), (wx + ww, wy + 2 * s)], mull, 2.2 * s)
            L.poly([(wx - ww - 8 * s * k, wy + wh + 4 * s), (wx + ww + 8 * s * k, wy + wh + 4 * s),
                    (wx + ww + 8 * s * k, wy + wh + 9 * s), (wx - ww - 8 * s * k, wy + wh + 9 * s)], surround * 1.08)
            wins.append((wx, wy))
        # a small plant on the left sill, a silhouette when the lamp is lit inside
        wx, wy = wins[0]
        plant = np.array([30, 40, 26], np.float32) * (0.4 + 0.6 * (1 - on)) + self.amb * 20
        L.poly([(wx - 7 * s, wy + 40 * s), (wx + 5 * s, wy + 40 * s), (wx + 4 * s, wy + 31 * s), (wx - 6 * s, wy + 31 * s)], plant)
        for a in (-0.9, -0.4, 0.1, 0.6):
            L.ellipse(wx - 1 * s + 9 * s * math.sin(a), wy + 25 * s - 6 * s * math.cos(a), 4 * s, 7 * s, plant)
        # clock
        self.clock(L, cx, CLOCK["y"] * H, CLOCK["R"] * s)
        # door
        dw, dh = 34 * s, 128 * s
        dyb = yb + 12 * s
        arch = self.lit((190, 182, 164), front, cx, dyb - dh)
        L.poly([(cx - dw - 12 * s, dyb), (cx + dw + 12 * s, dyb), (cx + dw + 12 * s, dyb - dh + dw), (cx - dw - 12 * s, dyb - dh + dw)], arch)
        L.ellipse(cx, dyb - dh + dw, dw + 12 * s, dw + 12 * s, arch)
        for a in np.linspace(0.15, math.pi - 0.15, 7):
            L.line([(cx + (dw + 1 * s) * math.cos(a), dyb - dh + dw - (dw + 1 * s) * math.sin(a)),
                    (cx + (dw + 12 * s) * math.cos(a), dyb - dh + dw - (dw + 12 * s) * math.sin(a))], arch * 0.75, 1.2 * s)
        wood = self.lit((96, 58, 36), front, cx, dyb - dh * 0.5)
        L.poly([(cx - dw, dyb), (cx + dw, dyb), (cx + dw, dyb - dh + dw), (cx - dw, dyb - dh + dw)], wood)
        L.ellipse(cx, dyb - dh + dw, dw, dw, wood)
        for i in range(1, 6):
            x = cx - dw + i * 2 * dw / 6
            L.line([(x, dyb), (x, dyb - dh + dw - math.sqrt(max(0, dw * dw - (x - cx) ** 2)) + 2 * s)], wood * 0.62, 1.4 * s)
        iron = self.lit((34, 32, 32), front)
        for yy in (dyb - 0.25 * dh, dyb - 0.7 * dh):
            L.line([(cx - dw, yy), (cx + dw * 0.7, yy)], iron, 3.2 * s)
        L.ellipse(cx + dw * 0.55, dyb - 0.47 * dh, 5 * s, 5 * s, iron)
        L.ellipse(cx + dw * 0.55, dyb - 0.47 * dh, 3 * s, 3 * s, wood)
        step = self.lit((176, 168, 150), [0, 0.5, 0.9], cx, dyb)
        L.poly([(cx - 50 * s, dyb + 9 * s), (cx + 50 * s, dyb + 9 * s), (cx + 46 * s, dyb - 1 * s), (cx - 46 * s, dyb - 1 * s)], step)
        # the lintel: carved over the door, for whoever looks closely
        ly = dyb - dh - 30 * s
        L.poly([(cx - 72 * s, ly - 12 * s), (cx + 72 * s, ly - 12 * s), (cx + 72 * s, ly + 12 * s), (cx - 72 * s, ly + 12 * s)], stone_hi)
        font = ImageFont.truetype(FONT, max(8, int(14 * s * SS)))
        txt = "L O O K   C L O S E R"
        L.text(cx, ly + 1.0 * s, txt, font, stone_hi * 1.15)
        L.text(cx, ly, txt, font, stone_hi * 0.45)
        # wall lantern
        lx, lyy = cx + 62 * s, yb - 92 * s
        L.line([(cx + dw + 13 * s, lyy - 14 * s), (lx, lyy - 14 * s)], iron, 2.5 * s)
        L.poly([(lx - 6 * s, lyy - 10 * s), (lx + 6 * s, lyy - 10 * s), (lx + 5 * s, lyy + 8 * s), (lx - 5 * s, lyy + 8 * s)],
               self.lit((150, 150, 140), front) * (1 - on) + np.array([255, 205, 130]) * on)
        L.poly([(lx - 8 * s, lyy - 10 * s), (lx + 8 * s, lyy - 10 * s), (lx, lyy - 17 * s)], iron)
        # ivy up the lower left of the tower
        rg = np.random.default_rng(51)
        t = np.linspace(0, 1, 90)
        vx = cx - r * (0.97 - 0.30 * t + 0.05 * np.sin(t * 14))
        vy = yb + 8 * s - t * (0.105 * H)
        L.line(list(zip(vx, vy)), self.lit((60, 48, 36), front), 2.0 * s)
        for i in range(300):
            j = rg.integers(0, len(t))
            lx2, ly2 = vx[j] + rg.normal(0, 14 * s), vy[j] + rg.normal(0, 8 * s)
            sv = float(np.clip((lx2 - cx) / r, -0.99, 0.99))
            nrm = normalize([-sv + rg.normal(0, 0.3), math.sqrt(1 - sv * sv), rg.uniform(0, 0.6)])
            c = self.lit(np.array([48, 84, 36]) * rg.uniform(0.75, 1.25), nrm, lx2, ly2)
            L.ellipse(lx2, ly2, rg.uniform(3.0, 5.5) * s, rg.uniform(2.2, 4.0) * s, c)
        L.composite()
        self.win_pos = wins
        self.door_lantern = (lx, lyy)

    def clock(self, L, x, y, R):
        s, h = self.s, self.h
        on = self.lights_on
        front = normalize([0, 1, 0.1])
        L.ellipse(x, y, R * 1.2, R * 1.2, self.lit((196, 188, 170), front, x, y))
        L.ellipse(x, y, R * 1.07, R * 1.07, self.lit((170, 128, 58), front))
        L.ellipse(x, y, R * 0.99, R * 0.99, self.lit((120, 90, 40), front))
        face = self.lit((234, 226, 204), front) * (1 - 0.6 * on) + np.array([255, 238, 200], np.float32) * 0.92 * on
        L.ellipse(x, y, R * 0.96, R * 0.96, face)
        ink = np.array([38, 32, 28], np.float32) * (0.6 + 0.4 * self.amb.mean() / 0.5)
        for i in range(60):
            a = math.radians(i * 6)
            if i % 5:
                px, py = x + R * 0.88 * math.sin(a), y - R * 0.88 * math.cos(a)
                L.ellipse(px, py, 1.1 * s, 1.1 * s, ink)
            else:
                L.line([(x + R * 0.80 * math.sin(a), y - R * 0.80 * math.cos(a)),
                        (x + R * 0.92 * math.sin(a), y - R * 0.92 * math.cos(a))], ink, 3.0 * s)
        font = ImageFont.truetype(FONT, max(6, int(R * 0.21 * SS)))
        for i, numeral in enumerate(["XII", "I", "II", "III", "IIII", "V", "VI", "VII", "VIII", "IX", "X", "XI"]):
            a = math.radians(i * 30)
            L.text(x + R * 0.64 * math.sin(a), y - R * 0.64 * math.cos(a), numeral, font, ink)

        def hand(angle, length, width, tail):
            a = math.radians(angle)
            ux, uy = math.sin(a), -math.cos(a)
            px, py = -uy, ux
            pts = [(x - ux * tail + px * width, y - uy * tail + py * width), (x + ux * length * 0.82 + px * width * 0.6, y + uy * length * 0.82 + py * width * 0.6),
                   (x + ux * length, y + uy * length), (x + ux * length * 0.82 - px * width * 0.6, y + uy * length * 0.82 - py * width * 0.6),
                   (x - ux * tail - px * width, y - uy * tail - py * width)]
            L.poly(pts, ink * 0.8)
        hand((h % 12) * 30, R * 0.52, R * 0.055, R * 0.12)
        hand(0, R * 0.80, R * 0.035, R * 0.14)
        L.ellipse(x, y, R * 0.065, R * 0.065, self.lit((180, 140, 64), front) + 30 * on)

    # --------------------------------------------------------------- tree --
    def tree(self):
        s, W, H = self.s, self.W, self.H
        r = np.random.default_rng(7)
        bx, by = TREE_BASE[0] * W, TREE_BASE[1] * H
        ccx, ccy = CANOPY[0] * W, CANOPY[1] * H
        Rx, Ry = CANOPY[2] * s, CANOPY[3] * s
        segs, tips = [], []
        fx, fy = 0.452 * W, 0.575 * H
        pts = [(bx + (fx - bx) * t + 6 * s * math.sin(t * 5), by + (fy - by) * t) for t in np.linspace(0, 1, 6)]
        widths = np.linspace(26, 15, 6) * s
        for i in range(5):
            segs.append((*pts[i], *pts[i + 1], widths[i], widths[i + 1], 0))

        def grow(x, y, ang, length, w, depth):
            mx, my = x + 0.5 * length * math.cos(ang), y - 0.5 * length * math.sin(ang)
            ang2 = ang + r.normal(0, 0.18)
            ex, ey = mx + 0.5 * length * math.cos(ang2), my - 0.5 * length * math.sin(ang2)
            we = w * 0.7
            segs.append((x, y, mx, my, w, (w + we) / 2, depth))
            segs.append((mx, my, ex, ey, (w + we) / 2, we, depth))
            if depth >= 4 or length < 34 * s:
                tips.append((ex, ey))
                return
            for i in range(2 if r.random() < 0.6 else 3):
                a = ang2 + r.uniform(-0.55, 0.55) + (0.3, -0.3, 0)[i]
                a = 0.82 * a + 0.18 * math.pi / 2
                grow(ex, ey, a, length * r.uniform(0.62, 0.78), we * 0.82, depth + 1)
        for a, ln in ((2.25, 175), (1.62, 165), (0.95, 170)):
            grow(fx, fy, a + r.normal(0, 0.08), ln * s, 12 * s, 1)

        clusters = [(tx, ty, r.uniform(26, 40) * s, r.uniform(-0.6, 0.8)) for tx, ty in tips]
        while len(clusters) < len(tips) + 280:
            u, v = r.uniform(-1, 1, 2)
            th = math.atan2(v, u)
            env = 1 + 0.10 * math.sin(3 * th + 0.7) + 0.07 * math.sin(5 * th + 2.1) + 0.05 * math.sin(8 * th)
            rho = math.hypot(u, v)
            if rho > env * 0.93:
                continue
            z = math.sqrt(max(0.0, 1 - (rho / env) ** 2)) * r.uniform(-1, 1)
            clusters.append((ccx + u * Rx, ccy + v * Ry, r.uniform(30, 54) * s, z))
        clusters.sort(key=lambda c: c[3])

        L = Layer(self, ccx - Rx * 1.35, ccy - Ry * 1.35, ccx + Rx * 1.35, by + 20 * s)
        greens = [(62, 98, 42), (74, 112, 46), (56, 88, 40), (88, 120, 52), (70, 104, 40)]
        autumn = [(150, 140, 56), (170, 128, 52), (128, 120, 50)]
        back_sun = max(0.0, -float(self.sunv[1])) * self.sun_str
        pools = self.local(np.float32(bx), np.float32(by - 120 * s)) if self.pools else 0

        def draw_clusters(sel):
            for (cx, cy, cr, cz) in sel:
                nx, ny = (cx - ccx) / Rx, (ccy - cy) / Ry
                edge = min(1.0, math.hypot(nx, ny))
                pal = autumn if r.random() < 0.05 else greens
                ao_c = 0.55 + 0.45 * (cz + 1) / 2
                mass_n = normalize([-nx * 0.8, cz * 0.5 + 0.5, ny * 0.8 + 0.2])
                L.ellipse(cx, cy + cr * 0.1, cr * 0.6, cr * 0.55,
                          np.array([50, 78, 36], np.float32) * (self.light(mass_n) * ao_c * 0.7 + pools))
                for _ in range(int(26 + cr / s * 0.7)):
                    ox, oy = np.clip(r.normal(0, cr * 0.5, 2), -cr * 1.1, cr * 1.1)
                    lx, ly = cx + ox, cy + oy
                    nrm = normalize([-(nx * 0.7 + ox / cr * 0.5) + r.normal(0, 0.25),
                                     cz * 0.5 + 0.5 + r.normal(0, 0.2),
                                     ny * 0.7 - oy / cr * 0.5 + 0.25 + r.normal(0, 0.2)])
                    alb = np.array(pal[r.integers(0, len(pal))], np.float32) * r.uniform(0.82, 1.15)
                    ao = ao_c * (1 - 0.25 * max(0.0, oy / cr))
                    c = alb * (self.light(nrm) * ao + pools)
                    c = c + alb * np.array([1.2, 1.35, 0.6]) * self.sun_col * back_sun * 0.45 * edge ** 2
                    ls, a = r.uniform(6.5, 11) * s, r.uniform(0, math.pi)
                    ca, sa_ = math.cos(a), math.sin(a)
                    pts = [(lx + ls * ca, ly + ls * sa_), (lx - 0.45 * ls * sa_ * 0.9 + 0.1 * ls * ca, ly + 0.45 * ls * ca * 0.9 + 0.1 * ls * sa_),
                           (lx - 0.6 * ls * ca, ly - 0.6 * ls * sa_), (lx + 0.45 * ls * sa_ * 0.9 + 0.1 * ls * ca, ly - 0.45 * ls * ca * 0.9 + 0.1 * ls * sa_)]
                    L.poly(pts, c)

        draw_clusters([c for c in clusters if c[3] < -0.15])
        bark = np.array([78, 64, 52], np.float32)
        for (x0, y0, x1, y1, w0, w1, depth) in segs:
            dx, dy = x1 - x0, y1 - y0
            ln = math.hypot(dx, dy) + 1e-6
            px, py = -dy / ln, dx / ln
            edges = np.linspace(-1, 1, 6 if depth == 0 else 4)
            for a, b in zip(edges[:-1], edges[1:]):
                m = (a + b) / 2
                c = bark * (self.light(normalize([-m, math.sqrt(1 - min(0.99, m * m)), 0.15])) + pools)
                L.poly([(x0 + px * w0 * a, y0 + py * w0 * a), (x1 + px * w1 * a, y1 + py * w1 * a),
                        (x1 + px * w1 * b, y1 + py * w1 * b), (x0 + px * w0 * b, y0 + py * w0 * b)], c)
            L.ellipse(x1, y1, w1, w1, bark * (self.light(normalize([0, 1, 0.15])) + pools))
        # root flare and bark furrows on the trunk
        base_c = bark * (self.light(normalize([0, 1, 0.2])) + pools)
        L.poly([(bx - 46 * s, by + 5 * s), (bx + 46 * s, by + 5 * s), (bx + 22 * s, by - 34 * s), (bx - 22 * s, by - 34 * s)], base_c * 0.9)
        for _ in range(26):
            off = r.uniform(-0.8, 0.8)
            t0 = r.uniform(0, 0.7)
            t1 = min(1, t0 + r.uniform(0.1, 0.3))
            ya, yb_ = by + (fy - by) * t0, by + (fy - by) * t1
            wa = 26 * s - 11 * s * t0
            L.line([(bx + (fx - bx) * t0 + off * wa + 6 * s * math.sin(t0 * 5), ya),
                    (bx + (fx - bx) * t1 + off * (26 * s - 11 * s * t1) + 6 * s * math.sin(t1 * 5), yb_)], base_c * 0.55, 1.4 * s)
        draw_clusters([c for c in clusters if c[3] >= -0.15])
        L.composite()

    def sheep(self):
        s, W, H = self.s, self.W, self.H
        r = np.random.default_rng(900 + self.h)
        day = 7 <= self.h <= 18
        if day:
            spots = [(r.uniform(0.03, 0.27), r.uniform(0.70, 0.84)) for _ in range(4)]
        else:
            spots = [(0.050, 0.772), (0.078, 0.782), (0.064, 0.790), (0.100, 0.797)]
        spots.sort(key=lambda p: p[1])
        nrm = normalize([0, 0.5, 0.85])
        for i, (x, y) in enumerate(spots):
            x, y = x * W, y * H
            if abs(y - (0.80 * H + (x / W - 0.15) * -1.2 * H)) < 0:
                continue
            p = 0.35 + 1.3 * min(1, max(0, (y / H - 0.6) / 0.4))
            k = 30 * s * p
            f = 1 if r.random() < 0.5 else -1
            wool = self.lit((228, 224, 212), nrm, x, y)
            face = self.lit((42, 38, 36), nrm, x, y)
            L = Layer(self, x - 2 * k, y - 2 * k, x + 2 * k, y + k)
            L.ellipse(x, y + 0.1 * k, 1.1 * k, 0.25 * k, np.array([30, 40, 24]) * (self.amb + 0.2), a=0.45)
            lift = 0.0 if not day else 0.55 * k
            if day:
                for lx in (-0.6, -0.3, 0.35, 0.65):
                    L.line([(x + lx * k, y - lift), (x + lx * k, y)], face, 0.16 * k)
            by = y - lift - 0.45 * k
            L.ellipse(x, by, 1.0 * k, 0.55 * k, wool * 0.92)
            for dx, dy in ((-0.5, -0.25), (0.0, -0.4), (0.45, -0.25), (-0.2, -0.1), (0.3, -0.05)):
                L.ellipse(x + dx * k, by + dy * k, 0.42 * k, 0.36 * k, wool * (1.0 - 0.1 * dy))
            grazing = day and r.random() < 0.6
            hx, hy = x + f * 0.95 * k, by + (0.35 * k if grazing else -0.15 * k)
            L.ellipse(hx, hy, 0.32 * k, 0.24 * k, face)
            L.ellipse(hx - f * 0.18 * k, hy - 0.18 * k, 0.14 * k, 0.07 * k, face)
            L.composite()

    # --------------------------------------------------------- small things --
    def bench(self):
        s, W, H = self.s, self.W, self.H
        bx, gy = BENCH[0] * W, BENCH[1] * H
        L = Layer(self, bx - 110 * s, gy - 95 * s, bx + 110 * s, gy + 10 * s)
        wood_n, iron_n = normalize([0, 0.8, 0.6]), normalize([0, 1, 0.2])
        wood = self.lit((128, 86, 54), wood_n, bx, gy - 40 * s)
        iron = self.lit((36, 36, 40), iron_n, bx, gy - 40 * s)
        L.poly([(bx - 92 * s, gy - 42 * s), (bx + 92 * s, gy - 42 * s), (bx + 92 * s, gy - 36 * s), (bx - 92 * s, gy - 36 * s)], wood * 0.75)
        for yy in (-78, -64, -50):
            L.poly([(bx - 94 * s, gy + (yy - 0) * s), (bx + 94 * s, gy + yy * s), (bx + 94 * s, gy + (yy + 9) * s), (bx - 94 * s, gy + (yy + 9) * s)], wood)
            L.line([(bx - 94 * s, gy + yy * s + 0.8 * s), (bx + 94 * s, gy + yy * s + 0.8 * s)], wood * 1.25, 1.2 * s)
        for sx in (-1, 1):
            x = bx + sx * 97 * s
            L.line([(x, gy), (x, gy - 82 * s)], iron, 5 * s)
            L.line([(x - sx * 4 * s, gy - 6 * s), (x - sx * 4 * s, gy - 34 * s)], iron, 4 * s)
            L.line([(x, gy - 44 * s), (x + sx * 12 * s, gy - 48 * s), (x + sx * 16 * s, gy - 56 * s)], iron, 4 * s)
            L.ellipse(x + sx * 16 * s, gy - 58 * s, 4 * s, 4 * s, iron)
        L.poly([(bx - 9 * s, gy - 61 * s), (bx + 9 * s, gy - 61 * s), (bx + 9 * s, gy - 56 * s), (bx - 9 * s, gy - 56 * s)],
               self.lit((196, 156, 70), wood_n) + 20 * self.sun_str)
        L.composite()

    def lamp(self):
        s, W, H = self.s, self.W, self.H
        lx, gy, hgt = LAMP[0] * W, LAMP[1] * H, LAMP[2] * s
        on = self.lights_on
        L = Layer(self, lx - 30 * s, gy - hgt - 40 * s, lx + 30 * s, gy + 6 * s)
        iron = self.lit((34, 34, 38), normalize([0, 1, 0.2]), lx, gy - hgt * 0.5)
        L.poly([(lx - 9 * s, gy), (lx + 9 * s, gy), (lx + 6 * s, gy - 16 * s), (lx - 6 * s, gy - 16 * s)], iron)
        L.poly([(lx - 3.6 * s, gy - 14 * s), (lx + 3.6 * s, gy - 14 * s), (lx + 2.6 * s, gy - hgt), (lx - 2.6 * s, gy - hgt)], iron)
        L.line([(lx - 14 * s, gy - hgt * 0.86), (lx + 14 * s, gy - hgt * 0.86)], iron, 2.4 * s)
        ty = gy - hgt
        glass = self.lit((170, 180, 190), normalize([0, 1, 0.3])) * (1 - on) + np.array([255, 222, 160], np.float32) * on
        L.poly([(lx - 9 * s, ty), (lx + 9 * s, ty), (lx + 12 * s, ty - 30 * s), (lx - 12 * s, ty - 30 * s)], glass)
        L.line([(lx, ty), (lx, ty - 30 * s)], iron, 1.5 * s)
        L.line([(lx - 9 * s, ty), (lx + 9 * s, ty)], iron, 2.5 * s)
        L.poly([(lx - 15 * s, ty - 30 * s), (lx + 15 * s, ty - 30 * s), (lx, ty - 42 * s)], iron)
        L.ellipse(lx, ty - 43 * s, 2.5 * s, 2.5 * s, iron)
        L.composite()
        self.lamp_pos = (lx, ty - 15 * s)

    def pier(self):
        s, W, H = self.s, self.W, self.H
        (ax, ay), (bx, by), (cx, cy), (dx, dy) = [(x * W, y * H) for x, y in PIER]
        L = Layer(self, ax - 20 * s, cy - 90 * s, bx + 30 * s, ay + 40 * s)
        top = self.lit((126, 108, 88), [0, 0.2, 1])
        side = self.lit((88, 74, 60), [0, 1, 0])
        post = self.lit((70, 58, 48), [0, 1, 0.1])
        n = 14
        for i in range(n + 1):   # posts
            t = i / n
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            p = 1 - 0.65 * t
            L.poly([(px - 4 * s * p, py), (px + 4 * s * p, py), (px + 4 * s * p, py + 26 * s * p), (px - 4 * s * p, py + 26 * s * p)], post)
            L.ellipse(px, py + 26 * s * p, 7 * s * p, 1.8 * s * p, self.lit((200, 210, 214), [0, 0.3, 1]), a=0.6)
        L.poly([(ax, ay), (bx, by), (bx, by + 5 * s * 0.35), (ax, ay + 7 * s)], side)
        L.poly([(ax, ay), (bx, by), (cx, cy), (dx, dy)], top)
        for i in range(1, 40):
            t = i / 40
            L.line([(ax + (bx - ax) * t, ay + (by - ay) * t), (dx + (cx - dx) * t, dy + (cy - dy) * t)], top * 0.7, 1.0 * s)
        # end post with its lantern, and a gull to keep it company by day
        px, py = bx - 4 * s, by
        L.poly([(px - 3 * s, py), (px + 3 * s, py), (px + 3 * s, py - 64 * s * 0.45), (px - 3 * s, py - 64 * s * 0.45)], post)
        on = self.lights_on
        lxp, lyp = self.pier_lantern()
        L.poly([(lxp - 4 * s, lyp + 4 * s), (lxp + 4 * s, lyp + 4 * s), (lxp + 4 * s, lyp - 5 * s), (lxp - 4 * s, lyp - 5 * s)],
               self.lit((160, 160, 150), [0, 1, 0.2]) * (1 - on) + np.array([255, 205, 130]) * on)
        L.poly([(lxp - 6 * s, lyp - 5 * s), (lxp + 6 * s, lyp - 5 * s), (lxp, lyp - 10 * s)], post)
        mid = int(n * 0.55)
        gx, gy = ax + (bx - ax) * mid / n, ay + (by - ay) * mid / n
        if 7 <= self.h <= 17:
            gs = 7 * s
            white = self.lit((236, 236, 232), [0, 0.8, 0.6])
            L.ellipse(gx, gy - gs * 0.9, gs, gs * 0.55, white)
            L.ellipse(gx + gs * 0.8, gy - gs * 1.5, gs * 0.42, gs * 0.38, white)
            L.poly([(gx - gs * 0.6, gy - gs * 1.2), (gx + gs * 0.5, gy - gs * 1.3), (gx - gs * 1.5, gy - gs * 0.8)], self.lit((120, 124, 132), [0, 0.8, 0.6]))
            L.line([(gx + gs * 1.15, gy - gs * 1.5), (gx + gs * 1.6, gy - gs * 1.45)], (230, 180, 60), 1.4 * s)
        L.composite()

    # ------------------------------------------------------------- night --
    def night_lights(self):
        s, on = self.s, self.lights_on
        if on <= 0:
            return
        for wx, wy in self.win_pos:
            self.glow(wx, wy - 10 * s, 26 * s, (255, 176, 96), 0.28 * on, tail=0.25)
        self.glow(self.tw["cx"], CLOCK["y"] * self.H, CLOCK["R"] * s * 1.15, (255, 222, 170), 0.16 * on, tail=0.2)
        dx, dy = self.door_lantern
        self.glow(dx, dy, 5 * s, (255, 226, 170), 1.2 * on)
        self.glow(dx, dy, 55 * s, (255, 176, 96), 0.28 * on, tail=0.3)
        lx, ly = self.lamp_pos
        self.glow(lx, ly, 9 * s, (255, 232, 180), 1.4 * on)
        self.glow(lx, ly, 90 * s, (255, 180, 100), 0.30 * on, tail=0.35)
        px, py = self.pier_lantern()
        self.glow(px, py, 4 * s, (255, 226, 170), 1.3 * on)
        self.glow(px, py, 40 * s, (255, 176, 96), 0.25 * on, tail=0.3)
        r = np.random.default_rng(80 + self.h)
        for _ in range(3):   # moths around the lamp
            mx, my = lx + r.normal(0, 22 * s), ly + r.normal(0, 18 * s)
            self.glow(mx, my, 1.6 * s, (255, 230, 190), 0.9 * on)
        if self.observing:
            cx, cy, R = self.tw["cx"], self.tw["yt"] - 16 * s, self.tw["r"]
            th = self.scope_theta
            self.glow(cx + math.cos(th) * R * 0.6, cy - math.sin(th) * R * 0.6, 20 * s, (200, 50, 36), 0.25)
        if self.dark > 0.5 and (self.h >= 20 or self.h <= 3):   # fireflies
            for _ in range(18):
                fx, fy = r.uniform(0.36, 0.64), r.uniform(0.66, 0.84)
                if fy < self.edge(fx) + 0.01:
                    continue
                self.glow(fx * self.W, fy * self.H, 1.8 * s, (210, 255, 130), 1.3)
                self.glow(fx * self.W, fy * self.H, 9 * s, (170, 230, 100), 0.18)

    def grade(self):
        H, W = self.H, self.W
        yy = (np.arange(H, dtype=np.float32)[:, None] + 0.5) / H
        xx = (np.arange(W, dtype=np.float32)[None, :] + 0.5) / W
        v = 1 - 0.38 * (((xx - 0.5) * 1.1) ** 2 + ((yy - 0.52) * 1.3) ** 2)
        c = self.c * v[..., None]
        c = np.where(c > 200, 200 + 55 * np.tanh((c - 200) / 55), c)
        c += self.rng.normal(0, 1.4, c.shape[:2]).astype(np.float32)[..., None]
        return np.clip(c + 0.5, 0, 255).astype(np.uint8)

    def render(self):
        self.sky()
        self.sky_extras()
        self.far_coast()
        self.headland()
        self.beams()
        self.plan_emitters()
        self.sea()
        self.mist()
        self.boats()
        self.foam()
        self.shade, self.ao = self.shadow_masks()
        self.hill()
        self.sheep()
        self.moored_boat()
        self.pier()
        self.tower()
        self.tree()
        self.bench()
        self.lamp()
        self.night_lights()
        return Image.fromarray(self.grade())


def job(args):
    hour, scale, out = args
    Frame(hour, scale).render().save(out, quality=93)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--hours", default="0-23")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--sheet", action="store_true")
    a = ap.parse_args()
    hours = []
    for part in a.hours.split(","):
        lo, _, hi = part.partition("-")
        hours += list(range(int(lo), int(hi or lo) + 1))
    os.makedirs(a.out, exist_ok=True)
    tasks = [(h, a.scale, os.path.join(a.out, f"{h:02d}.jpg")) for h in hours]
    with ProcessPoolExecutor(a.jobs) as ex:
        for out in ex.map(job, tasks):
            print(out, flush=True)
    if a.sheet:   # a contact sheet of small thumbnails
        w, h = 480, 300
        ims = [Image.open(t[2]).resize((w, h), Image.LANCZOS) for t in tasks]
        cols = min(6, len(ims))
        rows = (len(ims) + cols - 1) // cols
        sheet = Image.new("RGB", (w * cols, h * rows))
        for i, im in enumerate(ims):
            sheet.paste(im, ((i % cols) * w, (i // cols) * h))
        sheet.save(os.path.join(a.out, "sheet.jpg"), quality=88)


if __name__ == "__main__":
    main()
