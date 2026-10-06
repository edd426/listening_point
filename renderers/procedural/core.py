"""Shared constants, palettes, layout, helpers and the frame's lighting core."""
import functools
import math

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

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
AMB = [(-90, (.06, .075, .13)), (-18, (.065, .08, .14)), (-10, (.10, .11, .18)), (-4, (.19, .17, .25)),
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
# The pier is built in world units where the camera stands 1 unit above the sea (about 15 m):
# x to the right (west), z ahead (south), y up. It runs west from the shore on the right.
PIER3 = dict(root=(1.073, 1.086), dir=(0.8283, -0.5602), length=1.185, width=0.16, deck=0.050, thick=0.014)
LH_X = 0.768
MOORED = (0.886, 0.789)



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


@functools.lru_cache(None)
def hill_edge():
    """The silhouette of the foreground hill against the sea: (x, y) as fractions of the frame."""
    xd = np.linspace(-0.01, 1.02, 5000)
    yd = np.interp(xd, *zip(*HILL))
    yd = ndi.gaussian_filter1d(yd, 30, mode="nearest")
    yd += 0.0035 * np.interp(np.linspace(0, 1, 5000), np.linspace(0, 1, 1024), fnoise(4, 1024, 1.8, 1, 17)[0])
    yd += 0.005 * sm(0.56, 0.62, xd) * np.interp(np.linspace(0, 1, 5000), np.linspace(0, 1, 2048), fnoise(4, 2048, 2.2, 1, 18)[0])
    yd += 0.0007 * sm(0.56, 0.62, xd) * np.interp(np.linspace(0, 1, 5000), np.linspace(0, 1, 2048), fnoise(4, 2048, 1.2, 1, 19)[0])
    return xd, yd


def shore_band(xn):
    """Height of the beach between the low-water line (the hill's edge) and the grass, as a fraction of the frame."""
    xn = np.asarray(xn, np.float32)
    var = 1 + 0.25 * np.interp(xn, np.linspace(0, 1, 256), fnoise(4, 256, 2.0, 1, 26)[0])
    return (0.026 + 0.030 * sm(0.68, 1.0, xn)) * sm(0.565, 0.62, xn) * var


def water_line(xn, tide):
    """Where the sea meets the beach at this tide (0 low water, 1 high water), as a fraction of the frame."""
    return hill_edge_y(xn) + 0.5 * tide * shore_band(xn)


def hill_edge_y(xn):
    return np.interp(xn, *hill_edge())


def enu(alt, az):
    a, z = math.radians(alt), math.radians(az)
    return np.array([math.cos(a) * math.sin(z), math.cos(a) * math.cos(z), math.sin(a)], np.float32)


def to_screen(alt, az):
    return 0.5 + (np.asarray(az) - 180.0) / AZ_SPAN, VH - np.asarray(alt) / ALT_TOP * VH


def upsample(a, shape):
    """Bilinear resize of a float image (h, w) or (h, w, c) to shape (H, W)."""
    a = np.asarray(a, np.float32)
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a, "F").resize((shape[1], shape[0]), Image.BILINEAR), np.float32)
    return np.stack([upsample(a[..., i], shape) for i in range(a.shape[2])], -1)


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

    def arrays_rows(self, r0, r1):
        """Like arrays(), for rows r0..r1 of the layer only."""
        w = self.x1 - self.x0
        im = self.img.crop((0, r0 * SS, w * SS, r1 * SS)).resize((w, r1 - r0), Image.BOX)
        a = np.asarray(im, np.float32)
        return a[..., :3], a[..., 3:] / 255.0

    def composite(self, allow=None):
        if not self.ok:
            return
        rgb, al = self.arrays()
        if allow is not None:
            al = al * allow[..., None]
        self.fr.over(self.y0, self.y1, self.x0, self.x1, rgb, al)




class FrameBase:
    def __init__(self, day, minute, scale=1.0, sun=None):
        self.day, self.m = day, int(minute)
        self.t = self.m / 60.0                  # local clock time in hours
        self.h = (self.m // 60) % 24
        self.season = day.season
        self.wx = day.at(self.m)
        self.W, self.H = int(round(3840 * scale)), int(round(2400 * scale))
        self.s = self.W / 3840
        self.hz = int(round(VH * self.H))
        self.c = np.zeros((self.H, self.W, 3), np.float32)
        self.a = None                           # coverage, only while drawing a transparent layer
        self.rng = np.random.default_rng([day.date.toordinal(), self.m])
        m = min(self.m, 1440)
        self.sun_alt, self.sun_az = float(day.sun_alt[m]), float(day.sun_az[m])
        self.moon_alt, self.moon_az = float(day.moon_alt[m]), float(day.moon_az[m])
        self.moon_frac = float(day.moon_frac[m])
        self.jd, self.lst = float(day.jd[m]), float(day.lst[m])
        self.tide = float(day.tide[m])
        self.sunv, self.moonv = enu(self.sun_alt, self.sun_az), enu(self.moon_alt, self.moon_az)
        sa = self.sun_alt
        # clouds: the sun gets through when nothing is in front of it; a sky of cloud makes the light
        # flatter, greyer and dimmer, and rain darker still
        self.sun_vis = (1.0 if sun == "on" else 0.0) if sun else self.sun_visibility()
        wx = self.wx
        cov = min(1.0, 0.9 * wx.cloud_low + 0.6 * wx.cloud_mid + 0.15 * wx.cloud_high + 0.6 * wx.fog)
        self.overcast = cov
        self.sun_str = sm(-2.5, 6, sa) * self.sun_vis
        self.sun_col = keys(SUN_COL, sa)
        amb = keys(AMB, sa)
        grey = amb.mean()
        self.amb = (amb * (1 - 0.6 * cov) + grey * 0.6 * cov) * (1 - 0.15 * cov) * (1 - 0.25 * max(wx.rain, wx.snow))
        self.night = sm(-3, -10, sa)
        self.dark = sm(-8, -15, sa)
        # moonlight follows the phase law: a half moon gives about a tenth of the full moon's light
        phase = math.degrees(math.acos(max(-1.0, min(1.0, 2 * self.moon_frac - 1))))
        self.moon_bright = 10 ** (-0.4 * (0.026 * phase + 4e-9 * phase ** 4))
        self.moon_str = 0.30 * sm(0, 12, self.moon_alt) * sm(-3, -12, sa) * self.moon_bright * (1 - 0.85 * cov)
        self.lights_on = sm(2, -4, sa)
        self.bounce = np.array([0.30, 0.34, 0.22], np.float32) * (self.sun_col * self.sun_str * 0.9 + MOON_COL * self.moon_str * 0.5)
        # the observer works clear nights and keeps ordinary hours otherwise
        self.clear_night = self.overcast < 0.45 and wx.fog < 0.25 and wx.rain < 0.05 and wx.snow < 0.05 and wx.drizzle < 0.1
        self.observing = sa < -9 and self.clear_night
        self.windows_lit = self.lights_on * (1.0 if (self.observing or day.events.awake(self.t)) else 0.0)
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
            if self.windows_lit > 0:
                for sv in (-0.52, 0.52):
                    wx_ = self.tw["cx"] + sv * self.tw["r"] * 1.3
                    self.pools.append((wx_, 0.548 * self.H, self.tw["yb"] + 40 * s, WARM, 90 * s, 0.22 * self.windows_lit))
        self._edge = hill_edge()
        self.lamp_pos = (LAMP[0] * self.W, LAMP[1] * self.H - LAMP[2] * s - 15 * s)

    def edge(self, xn):
        return np.interp(xn, *self._edge)

    def proj(self, X, Y, Z):
        """World point (camera 1 unit above the sea, x right, z ahead, y up) to frame pixels."""
        X, Y, Z = np.asarray(X, np.float64), np.asarray(Y, np.float64), np.asarray(Z, np.float64)
        az = np.degrees(np.arctan2(X, Z))
        D = np.hypot(X, Z)
        alt = np.degrees(np.arctan2(Y - 1.0, D))
        return (0.5 + az / AZ_SPAN) * self.W, (VH - alt / ALT_TOP * VH) * self.H

    def proj_local(self, X, Y, Z, centre):
        """Pinhole projection aimed at world point `centre`, matched to the panorama there, so straight
        edges stay straight (the panorama bends long straight things like the pier)."""
        X, Y, Z = np.asarray(X, np.float64), np.asarray(Y, np.float64), np.asarray(Z, np.float64)
        cX, cY, cZ = centre
        az0 = math.atan2(cX, cZ)
        alt0 = math.atan2(cY - 1.0, math.hypot(cX, cZ))
        xc, yc = self.proj(cX, cY, cZ)
        daz = np.arctan2(X, Z) - az0
        alt = np.arctan2(Y - 1.0, np.hypot(X, Z))
        u = np.tan(daz)
        v = np.tan(alt) / np.cos(daz)
        kx = self.W / math.radians(AZ_SPAN)
        ky = VH * self.H / math.radians(ALT_TOP) * math.cos(alt0) ** 2
        return xc + kx * u, yc - ky * (v - math.tan(alt0))

    def pproj(self, X, Y, Z):
        """Projection for the pier and things on it."""
        return self.proj_local(X, Y, Z, tuple(float(c) for c in self.pier_pt(0.5, 0.5, PIER3["deck"])))

    def pier_pt(self, u, v, y):
        """A point on the pier: u along it (0 at the shore, 1 at the end), v across (0 near side, 1 far side)."""
        P = PIER3
        (rx, rz), (dx, dz) = P["root"], P["dir"]
        L, w = P["length"], P["width"]
        X = rx + np.asarray(u) * L * dx - np.asarray(v) * w * dz
        Z = rz + np.asarray(u) * L * dz + np.asarray(v) * w * dx
        return X, np.asarray(y, np.float64) + 0 * X, Z

    def over(self, y0, y1, x0, x1, rgb, al):
        """Composite rgb with coverage al (H, W, 1) over the frame, tracking coverage if asked."""
        t = self.c[y0:y1, x0:x1]
        t *= 1 - al
        t += rgb * al
        if self.a is not None:
            a = self.a[y0:y1, x0:x1]
            a *= 1 - al[..., 0]
            a += al[..., 0]

    # ------------------------------------------------------------ lighting --
    def light(self, nrm, shade=None, ao=None):
        """Sun and moon (Lambert, with shadow), sky light that favours upward faces, and warm-green
        light bounced off the sunlit ground onto sideways and downward faces."""
        nrm = np.asarray(nrm, np.float32)
        ds = np.clip(nrm @ self.sunv, 0, None)
        dm = np.clip(nrm @ self.moonv, 0, None)
        if shade is not None:
            ds = ds * (1 - shade)
            dm = dm * (1 - shade)
        up = np.asarray(nrm[..., 2])
        amb = self.amb * (0.72 + 0.28 * up)[..., None] + self.bounce * (0.5 * (1 - up))[..., None]
        if ao is not None:
            amb = amb * np.asarray(ao, np.float32)[..., None]
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

    def _add(self, arr, x, y, r, colr, k):
        R = r * 3
        x0, x1 = int(max(0, x - R)), int(min(arr.shape[1], x + R + 1))
        y0, y1 = int(max(0, y - R)), int(min(arr.shape[0], y + R + 1))
        if x0 >= x1 or y0 >= y1:
            return
        X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - x
        Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - y
        arr[y0:y1, x0:x1] += np.exp(-(X * X + Y * Y) / (r * r))[..., None] * colr * k
