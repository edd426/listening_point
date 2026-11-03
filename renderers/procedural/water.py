"""The water (v3 phase 4, part 1): light on the sea, and the marks in the bay.

- Cloud shadows on the sea, cast along the light by the very cloud layers the sky draws this minute
  (sky.cloud_layer), so they drift with the wind as the clouds do (`sea_shadow`).
- The wind on the water (`sea_wind`): glassy calm with cat's paws in light airs, wind lanes in a breeze,
  scattered whitecaps only in a real blow (`whitecaps`).
- Glitter that answers the wind (`glitter`): the sun's and moon's paths narrow and bright on a calm sea,
  wide and broken on a rough one, and cut where a cloud shadows the water.
- Marks (`beacon`, `sea_marks`): two mooring buoys by the moored boat, a short string of lobster-pot
  floats, a port-hand beacon on the approach to the island with a steady red light, and a skerry that
  covers and uncovers with the tide (`skerry`).

None of it runs in reference mode, so the shore kit's reference frames stay byte-identical, and none of it
draws from the frame's shared generator (`self.rng`); each thing has its own seed.

World units are those of core.FrameBase.proj: the camera stands 1 unit (about 15 m) above mean sea
level; x to the right (west), z ahead (south), y up. The sea is drawn as a fixed plane (y = 0), and the
boats and the floats ride on it; the tide shows where the water stands against fixed things: the beacon
and the skerry are drawn with the water at (tide - 0.5) * TR, so it climbs them and leaves them again.
"""
import functools
import math

import numpy as np
from scipy import ndimage as ndi

from core import *  # noqa: F401,F403
from sky import CLOUD_LAYERS

UNIT_KM = 0.015         # one world unit in km
TR = 0.10               # the tide's range on the marks, in world units (about 1.5 m)
SHADOW_G = 24.0         # cloud shadows: the sea's distances stretched this much, so the shadows of clouds a
                        # kilometre up fall across the bay in patches instead of all at once
SHADOW_STEP = 6         # cloud shadows are worked out on every 6th pixel of the sea (they are soft)
SHADOW_K = (0.25, 0.85, 0.97)   # how much direct light each layer stops (as sky.sun_visibility)
WIND_STEP = 3           # the wind's patterns on every 3rd pixel
SLOW = 0.04             # the wind's patterns drift downwind at this fraction of the wind's own run

# Where the marks meet the water at mean sea level, as fractions of the frame (x, y).
BEACON = (0.594, 0.630)         # a port-hand beacon on the approach to the island's harbour
BUOYS = (                       # (x, y, albedo, radius in world units): two mooring buoys
    (0.809, 0.725, (222, 98, 40), 0.026),      # orange, beyond the pier's end
    (0.951, 0.800, (232, 230, 222), 0.030),    # white, right of the moored boat
)
POTS = ((0.655, 0.738), (0.671, 0.745), (0.688, 0.752), (0.705, 0.758), (0.720, 0.764))   # the first is the dahn
SKERRY = (0.785, 0.686)         # the middle of the skerry
SKERRY_HALF = (0.66, 0.32)      # its half-length across the view and half-depth along it, world units
POT_R, DAHN_H = 0.017, 0.15     # a pot float's radius; the dahn's pole above its float
BEACON_TOP = 0.42               # the beacon's post top above mean sea level; its can topmark sits above


def sea_point(xn, yn):
    """The world point (X, Z) of the sea surface at frame fractions (xn, yn), and its distance."""
    D = 1.0 / math.tan(math.radians((yn - VH) / VH * ALT_TOP))
    az = math.radians((xn - 0.5) * AZ_SPAN)
    return D * math.sin(az), D * math.cos(az), D


@functools.lru_cache(None)
def sea_grid(W, H, step):
    """Every step-th pixel of the sea (the rows below the horizon): the distance D, the world X and Z,
    and the dip below the horizon (deg), each (rows, cols)."""
    hz = int(round(VH * H))
    y = np.arange(hz, H, step, dtype=np.float32) + 0.5 * step
    x = np.arange(0, W, step, dtype=np.float32) + 0.5 * step
    ad = np.maximum((y - VH * H) / (VH * H) * ALT_TOP, 0.05)
    D = (1 / np.tan(np.radians(ad))).astype(np.float32)
    az = np.radians((x / W - 0.5) * AZ_SPAN).astype(np.float32)
    D2 = np.repeat(D[:, None], len(x), 1)
    return D2, D2 * np.sin(az)[None, :], D2 * np.cos(az)[None, :], np.repeat(ad[:, None], len(x), 1)


@functools.lru_cache(None)
def skerry_field(na=150, nb=60):
    """The skerry's height above mean sea level (world units) on a grid (nb, na): a across the view
    (-1..1, to the right) and b along it (-1 near .. 1 far); and a 0..1 field for its weed and crust."""
    a = np.linspace(-1, 1, na, dtype=np.float32)[None, :]
    b = np.linspace(-1, 1, nb, dtype=np.float32)[:, None]
    tex = fnoise(64, 256, 2.2, 1.0, 4410)
    nz = sample(tex, (b + 1) * 14 + 0 * a, (a + 1) * 60 + 0 * b)
    nz2 = sample(fnoise(64, 256, 1.6, 1.0, 4411), (b + 1) * 20 + 0 * a, (a + 1) * 90 + 0 * b)

    def at(tide):          # the height the water reaches at this state of the tide
        return (tide - 0.5) * TR

    def dome(a0, b0, ra, rb, top, foot=at(-0.3)):
        r2 = ((a - a0) / ra) ** 2 + ((b - b0) / rb) ** 2
        return foot + (top - foot) * np.exp(-r2 ** 1.3 * 1.6)
    # a low whaleback shelf that dries at about a third of the tide, and three knobs on it, the highest
    # covered only for the top of the tide (and not at all on a neap)
    r = np.sqrt((a / 1.0) ** 2 + ((b - 0.05) / 0.9) ** 2)
    shelf = at(-0.4) + (at(0.38) - at(-0.4)) * (1 - sm(0.55, 1.05, r))
    h = np.maximum.reduce([shelf,
                           dome(-0.28, 0.18, 0.38, 0.55, at(0.80)),
                           dome(0.27, 0.02, 0.30, 0.45, at(0.62)),
                           dome(0.68, 0.22, 0.20, 0.30, at(0.48))])
    h = h + 0.06 * TR * nz
    # bedding: ledges where the rock splits along its layers
    q = np.floor(h / (0.13 * TR)) * (0.13 * TR)
    h = (0.65 * h + 0.35 * q).astype(np.float32)
    return h, nz2.astype(np.float32)


def ripple_rows(n, y0, s, amp):
    """Horizontal offsets (px) for n rows of a reflection starting at frame row y0: the ripples break it up."""
    rows = np.arange(n, dtype=np.float32) + y0
    return amp * (np.sin(rows * 0.9 / s + 1.3) + 0.55 * np.sin(rows * 0.37 / s + 0.4))


class WaterMixin:
    # ------------------------------------------------------------ light --
    def sea_shadow(self, src="sun"):
        """How much direct light from the sun (or the moon) reaches each pixel of the sea through this
        minute's clouds: (sea rows, W), or None when no cloud is about. Each layer's shadow is cast along
        the light onto the sea from the layer the sky draws, so the patches drift with the clouds; at the
        foot of the frame it matches what the land gets (sun_visibility)."""
        alt, az = (self.sun_alt, self.sun_az) if src == "sun" else (self.moon_alt, self.moon_az)
        if alt < -1:
            return None
        if max([self.layer_cover(i) for i in range(3)] + [self.wx.cloud_low]) < 0.01:
            return None
        W, H, hz = self.W, self.H, self.hz
        D, X, Z, _ = sea_grid(W, H, SHADOW_STEP)
        k = UNIT_KM * SHADOW_G * np.minimum(D, 60.0) / D
        shift = (-X * k, -Z * k)                        # km east and north of the camera
        a = np.full(D.shape, max(alt, 0.5), np.float32)
        z = np.full(D.shape, az, np.float32)
        through = np.ones(D.shape, np.float32)
        for i in range(3):
            d = self.cloud_layer(i, a, z, shift=shift)
            if d is not None:
                through *= 1 - SHADOW_K[i] * d
        through = ndi.gaussian_filter(through, 1.0, mode="nearest")     # a soft edge, and no speckle far off
        return upsample(through, (H - hz, W)) * (1 - 0.85 * self.wx.fog)

    def sea_wind(self, rows):
        """The wind's marks on the water: a roughness (sea rows, W) about 1 that scales the waves, and
        the lift (px) it gives the reflection: rough water mirrors the sky from higher up, so it reads
        darker than glassy water. Light airs leave glassy water with cat's paws drifting on it; a breeze
        draws lanes and slicks along the wind; a blow roughens it all. Far off, where the water's own
        pattern would be finer than the pixels, the same patches lie as long bands along the horizon."""
        W, H, hz, s = self.W, self.H, self.hz, self.s
        D, X, Z, adg = sea_grid(W, H, max(2, int(round(WIND_STEP * s / 0.75))))
        v = self.wx.wind_ms
        th = math.radians(self.wx.wind_dir_deg + 180)          # where it blows to
        dx, dz = -math.sin(th), -math.cos(th)                  # that way in world x (west) and z (south)
        m = min(self.m, 1440)
        de, dn = float(self.day.drift_e[m]), float(self.day.drift_n[m])
        Xs, Zs = X + de * SLOW / UNIT_KM, Z + dn * SLOW / UNIT_KM
        ph = 2 * math.pi * self.m / 29.0
        cp, sp = math.cos(ph), math.sin(ph)
        cat = sm(3.5, 2.2, v)            # light airs: cat's paws; above about 3 m/s, lanes
        near = D[::3, ::3] < 16
        frac = 0.08 + 0.42 * sm(0.4, 2.8, v)
        glassy = 0.38 + 0.5 * sm(0.5, 3.5, v)
        blow = sm(8.0, 12.0, v)
        lr = 0.0
        if cat > 0:
            # cat's paws: patches of ripple a few tens of metres across, slowly changing shape
            tp = fnoise(256, 256, 2.4, 1.0, 81)
            paw_n = sample(tp, Zs * 5.0, Xs * 5.0) * cp + sample(tp, Zs * 5.0 + 97, Xs * 5.0 + 131) * sp
            # how much of the water the paws take: a few in the faintest airs, about half at 3 m/s; the
            # level is set from the water in view, as the clouds' is from the sky in view (sky.layer_threshold)
            view = paw_n[::3, ::3][near]
            thr = float(np.quantile(view, 1 - frac)) if view.size else 1.0
            paw = sm(thr - 0.35, thr + 0.45, paw_n)
            lr = lr + cat * (glassy + (1.35 - glassy) * paw)
        if cat < 1:
            # lanes: long streaks along the wind, rippled lanes between smooth slicks
            u, w = Xs * dx + Zs * dz, -Xs * dz + Zs * dx
            ln_n = sample(fnoise(256, 1024, 1.5, 5.0, 83), w * 3.0, u * 1.0)
            view = ln_n[::3, ::3][near]
            thr = float(np.quantile(view, 0.35)) if view.size else 0.0     # about a third of it slicks
            lane = sm(thr - 0.35, thr + 0.35, ln_n)
            lr = lr + (1 - cat) * ((0.7 + 0.65 * lane) * (1 - blow) + (1.15 + 0.25 * lane) * blow)
        mean = (glassy + (1.35 - glassy) * frac) * cat + ((0.7 + 0.65 * 0.6) * (1 - blow) + (1.15 + 0.25 * 0.6) * blow) * (1 - cat)
        # far off, where those patterns would be finer than the pixels, the same water shows as soft
        # bands along the horizon (log distance and azimuth), and toward the horizon it all evens out
        az = np.arctan2(X, Z)
        qf, cf = np.log(D) * 4.0 + dn * 0.02, az * 70.0 + de * 0.02
        tf = fnoise(256, 512, 2.2, 4.0, 85)          # long along the horizon
        nf = sample(tf, qf, cf) * cp + sample(tf, qf + 61, cf + 173) * sp
        lr_far = mean + (0.22 * cat + 0.12 * (1 - cat)) * np.clip(nf, -2, 2)
        far = sm(7.0, 16.0, D)
        lr = lr * (1 - far) + lr_far * far
        lr = mean + (lr - mean) * sm(0.15, 1.5, adg)
        lr = ndi.gaussian_filter(lr, 0.7, mode="nearest")
        lr = upsample(lr.astype(np.float32), (H - hz, W))
        dy = (rows - VH * H)[:, None]
        bias = (lr - 1) * (3 * s + 0.4 * dy) * sm(0, 6 * s, dy)
        return lr, bias

    def glitter(self, src_alt, src_x, colr, k, wm, ad, rp, lr, T):
        """A glitter path (sun or moon) on the sea, by the wind: narrow, bright and nearly whole on a calm
        sea, wide and broken into glints on a rough one; cut where a cloud shadows the water."""
        s, v = self.s, self.wx.wind_ms
        W = self.W
        w0 = min(1.8, 0.55 + 0.11 * v)               # as wide as before at about 4 m/s
        # only the columns the path can reach
        reach = 3.2 * (5 + float(ad.max()) * 2.8) * s * wm * (1 + max(src_alt, 0) / 18) * w0 * (0.7 + 0.3 * float(lr.max()))
        c0, c1 = int(max(0, src_x - reach)), int(min(W, src_x + reach + 1))
        out = np.zeros((len(ad), W, 3), np.float32)
        if c1 <= c0:
            return out
        lr, rp = lr[:, c0:c1], rp[:, c0:c1]
        T = None if T is None else T[:, c0:c1]
        Xs = np.arange(c0, c1, dtype=np.float32)[None, :]
        wide = w0 * (0.7 + 0.3 * lr)
        sig = (5 + ad[:, None] * 2.8) * s * wm * (1 + max(src_alt, 0) / 18) * wide
        horiz = np.exp(-((Xs - src_x) / sig) ** 2)
        ctr = max(src_alt, 0.6)
        spread = (2.5 + 0.55 * max(src_alt, 0)) * min(1.4, 0.8 + 0.05 * v)
        vert = np.exp(-((ad[:, None] - ctr) / spread) ** 2) + 0.25 * np.exp(-ad[:, None] / (3 + ctr))
        calm, rough = sm(3.0, 0.6, v), sm(5, 12, v)
        sp = np.clip(rp - (0.9 - 0.3 * rough), 0, None) ** 1.5 * 2.0
        I = horiz * vert * ((0.25 + 0.45 * calm - 0.15 * rough) + (1.0 - 0.45 * calm + 0.3 * rough) * sp) * k
        if T is not None:
            I = I * T ** 1.5
        out[:, c0:c1] = I[..., None] * np.asarray(colr, np.float32)
        return out

    def whitecaps(self):
        """White horses in a real blow (from about 8 m/s): short crests with a little foam behind them,
        scattered over the bay. Each lasts a few minutes, fading in and out, and drifts downwind, so the
        sea changes from minute to minute without flashing."""
        v = self.wx.wind_ms
        c = min(1.0, max(0.0, (v - 7.5) / 6.0))
        if c <= 0:
            return
        W, H, hz, s = self.W, self.H, self.hz, self.s
        n = int(round(340 * c ** 1.1))
        th = math.radians(self.wx.wind_dir_deg + 180)
        ex = -math.sin(th)               # the wind's screen-x sense (east is left)
        T = getattr(self, "sea_T", None)
        ybot = int(min(H, 0.93 * H))
        L = Layer(self, 0.24 * W, hz, W, ybot)
        seed = self.day.date.toordinal()
        P = 4
        for i in range(n):
            ph = int(hash2(i, 7.3) * P)
            cyc, age = divmod(self.m + ph, P)
            r = np.random.default_rng([seed, 4400, i, cyc])
            xn, q, size, bend, wob = r.random(), r.random(), r.uniform(0.6, 1.4), r.uniform(-0.3, 0.4), r.uniform(0, 6.3)
            dabs = r.uniform(-0.5, 0.5, (6, 3))
            xn = 0.24 + 0.76 * xn
            ad = 0.25 + 35.0 * q ** 1.9                          # more of them far off, where the sea is denser
            y = hz + ad / ALT_TOP * VH * H
            if y >= water_line(np.array([xn]), self.tide)[0] * H - 6 * s:
                continue
            D = 1 / math.tan(math.radians(ad))
            k = 1000.0 * s / D                                   # px per world unit
            life = (age + 0.5) / P
            al = math.sin(math.pi * life) ** 0.8 * (0.6 + 0.4 * c)
            x = xn * W + ex * life * 0.05 * k * (0.5 + c)
            ln = max(1.6 * s, 0.14 * size * k * (0.6 + 0.5 * c))
            if ln > 55 * s:
                continue
            tk = max(0.5 * s, min(2.2 * s, 0.085 * ln))
            shade = None
            if T is not None:
                t = float(T[int(min(T.shape[0] - 1, y - hz)), int(min(W - 1, max(0, x)))])
                shade = 1 - t / max(self.sun_vis, 0.02) if self.sun_str > 0 else None
            fc = self.lit((232, 238, 240), (0, 0.35, 1), shade=shade)
            # the crest: a short, bent, bright stroke
            pts = [(x + (t - 0.5) * ln, y - tk * (0.9 * math.sin(math.pi * t) * (1 + bend) + 0.35 * math.sin(7 * t + wob)))
                   for t in np.linspace(0, 1, 7)]
            L.line(pts, fc, tk, a=al)
            # the foam it spills: a few broken dabs below it, drifting downwind and spreading as it ages
            if ln > 4 * s:
                spread = 0.6 + 0.8 * life
                for du, dv, dl in dabs[:2 + min(4, int(ln / (6 * s)))]:
                    fx = x + du * ln * spread - ex * 0.25 * ln * life
                    fy = y + (1.2 + 2.2 * (dv + 0.5)) * tk * spread
                    half = (0.12 + 0.12 * (dl + 0.5)) * ln
                    L.line([(fx - half, fy), (fx + half, fy + 0.2 * tk * dl)], fc * 0.94, 0.8 * tk, a=al * (0.5 - 0.3 * (dv + 0.5)))
        L.composite()

    # ------------------------------------------------------------ marks --
    def tide_flow(self):
        """The tidal stream now, -1..1: positive on the flood (rising), 0 at slack water."""
        tide, m = self.day.tide, min(self.m, 1439)
        a, b = max(0, m - 5), min(len(tide) - 1, m + 5)
        return float(np.clip((tide[b] - tide[a]) / (b - a) / 0.0042, -1, 1))

    def set_on(self):
        """Where the water pushes things now, in world (x, z): the tidal stream sets west (to the right) into
        the bay on the flood and back east on the ebb; the wind adds its own push downwind."""
        th = math.radians(self.wx.wind_dir_deg + 180)
        v = self.wx.wind_ms
        f = self.tide_flow()
        return 0.55 * f - 0.045 * v * math.sin(th), -0.045 * v * math.cos(th)

    def water_level(self):
        return (self.tide - 0.5) * TR

    def local_shade(self, x, y):
        """`shade` for self.lit at a point on the sea: its own cloud shadow, against the light the land gets."""
        y = int(min(self.H - 1, max(self.hz, y))) - self.hz
        x = int(min(self.W - 1, max(0, x)))
        if self.sun_str > 0:
            T = getattr(self, "sea_T", None)
            return None if T is None else 1 - float(T[y, x]) / max(self.sun_vis, 0.02)
        T = getattr(self, "sea_Tm", None)
        if T is None or self.moon_str <= 0:
            return None
        return 1 - float(T[y, x]) / max(1 - 0.85 * self.overcast, 0.05)

    def refl_amp(self):
        """How far the ripples break up a reflection (px), and how strong it is."""
        v = self.wx.wind_ms
        return (0.5 + 2.4 * sm(0.5, 9, v)) * self.s, (0.55 - 0.38 * sm(1.0, 9, v)) * (1 - 0.35 * self.night)

    def reflect(self, R):
        """Composite a layer of mirrored shapes as their reflection, broken up by the ripples."""
        if not R.ok:
            return
        rgb, al = R.arrays()
        if al.max() <= 0:
            return
        amp, k = self.refl_amp()
        off = ripple_rows(al.shape[0], R.y0, self.s, amp)[:, None]
        rows = np.arange(al.shape[0], dtype=np.float32)[:, None]
        cols = np.arange(al.shape[1], dtype=np.float32)[None, :] + off
        rgb = np.stack([ndi.map_coordinates(rgb[..., c], [rows + 0 * cols, cols], order=1, mode="nearest") for c in range(3)], -1)
        al = ndi.map_coordinates(al[..., 0], [rows + 0 * cols, cols], order=1, mode="nearest")[..., None]
        al = ndi.gaussian_filter(al, (0.7 * self.s, 0.3 * self.s, 0)) * k
        self.over(R.y0, R.y1, R.x0, R.x1, rgb, al)

    def ball(self, L, R, x, yw, r, alb, sub=0.4, shade=None, gloss=0.25):
        """A floating ball of radius r px with its waterline at frame point (x, yw), sunk by sub of its
        diameter, lit as a sphere by the scene's own lights, with its reflection drawn into R."""
        n = int(math.ceil(r * SS)) + 2
        g = (np.arange(-n, n, dtype=np.float32) + 0.5) / (r * SS)
        U, V = np.meshgrid(g, g)
        rr = np.sqrt(U * U + V * V)
        inside = np.clip((1 - rr) * r * SS + 0.5, 0, 1)
        nz = np.sqrt(np.clip(1 - rr * rr, 0, 1))
        nrm = np.stack([-U, nz, -V], -1)                       # east, north (toward us), up
        col = np.asarray(alb, np.float32) * self.light(nrm, shade)
        if self.pools:
            col = col + np.asarray(alb, np.float32) * self.local(np.float32(x), np.float32(yw))
        # a wet gloss: the sky on the upper face, the light on its own side
        col = col + gloss * self.hor_col * (sm(0.2, 0.9, -V) * nz * 0.5)[..., None]
        cy = yw - r * (1 - 2 * sub)
        top = cy - n / SS
        ys = top + (np.arange(2 * n, dtype=np.float32)[:, None] + 0.5) / SS
        a = inside * np.clip((yw - ys) * SS + 0.5, 0, 1)
        L.blit(x - n / SS, top, col, a)
        if R is not None:
            # its reflection: what shows above the water, mirrored about the waterline, darker
            mirror_top = 2 * yw - (top + 2 * n / SS)
            R.blit(x - n / SS, mirror_top, (col * 0.55)[::-1], a[::-1])
        # the wet line and a little wash where it sits in the water
        L.ellipse(x, yw, r * math.sqrt(max(0.0, 1 - (1 - 2 * sub) ** 2)) * 1.05, max(0.5, 0.18 * r),
                  self.lit((44, 52, 46), (0, 0.6, 0.8), shade=shade), a=0.55)

    def beacon(self):
        """A port-hand beacon (IALA A: a red post and a red can topmark) on the approach to the island's
        harbour, with a steady red light from dusk to dawn. It stands on the bottom: the water climbs its
        weedy foot with the tide."""
        W, H, s = self.W, self.H, self.s
        X, Z, D = sea_point(*BEACON)
        wl = self.water_level()
        k = VH * H / math.radians(ALT_TOP) / D                 # px per world unit
        x = float(self.proj(X, 0, Z)[0])

        def Y(h):
            return float(self.proj(X, h, Z)[1])
        yw, hw, top = Y(wl), Y(0.5 * TR), Y(BEACON_TOP)
        hp = 0.027 * k
        L = Layer(self, x - 12 * hp, Y(BEACON_TOP + 0.2) - 4 * s, x + 12 * hp, yw + 4 * s)
        R = Layer(self, x - 12 * hp, yw - 2 * s, x + 12 * hp, yw + (yw - Y(BEACON_TOP + 0.2)) + 6 * s)
        shade = self.local_shade(x, yw)
        sides = [(0.8, 0.55, 0.1), (0.0, 1.0, 0.1), (-0.8, 0.55, 0.1)]

        def column(R_, x0, x1, y0, y1, alb, a=1.0):
            for i, nrm in enumerate(sides):
                c = self.lit(alb, nrm, x, y0, shade=shade)
                u0, u1 = x0 + (x1 - x0) * i / 3, x0 + (x1 - x0) * (i + 1) / 3
                R_.poly([(u0, y0), (u1, y0), (u1, y1), (u0, y1)], c, a=a)
        red, weed, crust = (164, 42, 36), (60, 56, 36), (150, 146, 132)
        # the post: weed and barnacles below high water, red above
        column(L, x - hp, x + hp, yw, max(hw, top), weed) if yw > hw else None
        if yw > hw:
            L.line([(x - hp, hw), (x + hp, hw)], self.lit(crust, (0, 1, 0.3), shade=shade), max(0.6 * s, 0.25 * hp))
        column(L, x - hp, x + hp, min(yw, hw), top, red)
        # the lantern housing, then the can topmark on its short stalk
        lh0, lh1 = top, Y(BEACON_TOP + 0.045)
        column(L, x - 0.8 * hp, x + 0.8 * hp, lh0, lh1, (40, 40, 42))
        on = self.lights_on
        gl = self.lit((120, 60, 56), (0, 1, 0.2), shade=shade) * (1 - on) + np.array([255, 90, 70]) * on
        L.poly([(x - 0.55 * hp, lh0 - 0.25 * (lh0 - lh1)), (x + 0.55 * hp, lh0 - 0.25 * (lh0 - lh1)),
                (x + 0.55 * hp, lh0 - 0.75 * (lh0 - lh1)), (x - 0.55 * hp, lh0 - 0.75 * (lh0 - lh1))], gl)
        st = Y(BEACON_TOP + 0.075)
        L.line([(x, lh1), (x, st)], self.lit((40, 40, 42), (0, 1, 0.2), shade=shade), max(0.6 * s, 0.5 * hp))
        cw, ct = 1.7 * hp, Y(BEACON_TOP + 0.165)
        column(L, x - cw, x + cw, st, ct, red)
        L.ellipse(x, ct, cw, max(0.5 * s, 0.22 * cw), self.lit(np.array(red) * 1.1, (0, 0.3, 0.95), shade=shade))
        # a little wash where the stream runs past its foot
        f = self.tide_flow()
        sx = 1 if self.set_on()[0] >= 0 else -1
        foam = self.lit((220, 228, 230), (0, 0.4, 1), shade=shade)
        L.ellipse(x, yw + 0.3 * s, 1.6 * hp, max(0.5 * s, 0.25 * hp), foam, a=0.25 + 0.3 * abs(f))
        if abs(f) > 0.15:
            L.line([(x + sx * hp, yw + 0.2 * s), (x + sx * (hp + 6 * hp * abs(f)), yw + 0.6 * s)], foam, max(0.5 * s, 0.4 * hp), a=0.35 * abs(f))
        # the reflection: the post and its can, mirrored about the waterline
        def mir(y):
            return 2 * yw - y
        column(R, x - hp, x + hp, yw, mir(top), np.array(red) * 0.6)
        column(R, x - cw, x + cw, mir(st), mir(ct), np.array(red) * 0.6)
        self.reflect(R)
        L.composite()

    def beacon_glow(self):
        """The beacon's steady red light, drawn after the far fog (render): through fog it dims with the
        distance and spreads into a halo, as the lamps on shore do."""
        on = self.lights_on
        if on <= 0:
            return
        s = self.s
        X, Z, D = sea_point(*BEACON)
        x, ly = self.proj(X, BEACON_TOP + 0.022, Z)
        x, ly = float(x), float(ly)
        wx = self.wx
        through = 1.0
        if wx.fog >= 0.02 or wx.visibility_m <= 15000:
            through = math.exp(-3.9 / max(wx.visibility_m, 60.0) * D * UNIT_KM * 1000)
        self.glow(x, ly, 1.3 * s, (255, 70, 56), 1.3 * on * (0.25 + 0.75 * through))
        self.glow(x, ly, (5 + 9 * (1 - through)) * s, (255, 60, 50), (0.14 + 0.1 * (1 - through)) * on)

    def beacon_light(self):
        """The beacon's light as an emitter, so the sea mirrors it (plan_emitters)."""
        X, Z, D = sea_point(*BEACON)
        x, ly = self.proj(X, BEACON_TOP + 0.022, Z)
        yw = self.proj(X, self.water_level(), Z)[1]
        return float(x), float(ly), float(yw)

    def mark_positions(self):
        """Where each floating mark is now: [(kind, index, x, waterline y, distance, radius, albedo)], in frame
        pixels and world units. They float on the sea's surface (the frame's fixed plane, as the boats do)
        and swing round their moorings with the stream and the wind, wider at low water (more slack)."""
        W, H = self.W, self.H
        px, pz = self.set_on()
        wl = 0.0
        out = []
        for i, (xn, yn, alb, rad) in enumerate(BUOYS):
            X, Z, D = sea_point(xn, yn)
            sw = 0.035 * (1.25 - 0.5 * self.tide)
            X, Z = X + sw * px, Z + sw * pz
            x, y = self.proj(X, wl, Z)
            out.append(("buoy", i, float(x), float(y), D, rad, alb))
        for i, (xn, yn) in enumerate(POTS):
            X, Z, D = sea_point(xn, yn)
            sw = 0.02 * (1.2 - 0.4 * self.tide)
            X, Z = X + sw * px, Z + sw * pz
            x, y = self.proj(X, wl, Z)
            out.append(("pot", i, float(x), float(y), D, POT_R, (226, 104, 40)))
        return out

    def sea_marks(self, lo=0.0, hi=2.0):
        """The skerry, the floats and the mooring buoys whose waterline lies between frame fractions lo and
        hi (bay draws them far to near, around the boats)."""
        H, s = self.H, self.s
        if lo <= SKERRY[1] < hi:
            self.skerry()
            self.skerry_life()      # seals hauled out, the cormorant (sealife.py)
        aboard = self.day.sea.pot_aboard(self.m)     # a float the creel boat has aboard with its pot
        marks = [m for m in self.mark_positions() if lo <= m[3] / H < hi and not (m[0] == "pot" and m[1] == aboard)]
        if not marks:
            return
        k0 = VH * H / math.radians(ALT_TOP)
        xs = [m[2] for m in marks]
        ys = [m[3] for m in marks]
        pad = 70 * s
        L = Layer(self, min(xs) - pad, min(ys) - 2 * pad, max(xs) + pad, max(ys) + pad)
        R = Layer(self, L.x0, min(ys) - 4 * s, L.x1, max(ys) + pad)
        px, pz = self.set_on()
        flow = self.tide_flow()
        v = self.wx.wind_ms
        thw = math.radians(self.wx.wind_dir_deg + 180)
        wind_x = -math.sin(thw)                                  # the wind's screen-x sense
        lean = max(-0.9, min(0.9, px))                           # the stream and the wind lean things over
        bob = 0.35 * s * sm(2, 10, v)
        for kind, i, x, y, D, rad, alb in sorted(marks, key=lambda m: m[3]):
            k = k0 / D
            r = rad * k
            shade = self.local_shade(x, y)
            yb = y + bob * math.sin(self.m * 1.7 + 2.3 * i + (0 if kind == "buoy" else 1.1))
            if kind == "buoy":
                self.ball(L, R, x, yb, r, alb, sub=0.38, shade=shade, gloss=0.3)
                # the mooring ring on top, and the pick-up buoy trailing on its line down the stream
                ring = self.lit((52, 50, 48), (0, 0.6, 0.8), shade=shade)
                tip = yb - r * (1 - 2 * 0.38) - r
                L.ellipse(x, tip, 0.32 * r, 0.16 * r, ring)
                L.ellipse(x, tip - 0.08 * r, 0.18 * r, 0.08 * r, self.lit((96, 92, 86), (0, 0.3, 0.95), shade=shade))
                qx = x + (1.6 + 1.2 * abs(lean)) * r * (1 if px >= 0 else -1)
                L.line([(x + 0.7 * r * (1 if px >= 0 else -1), yb), (qx, yb + 0.05 * r)], self.lit((150, 140, 116), (0, 1, 0.4), shade=shade), max(0.5 * s, 0.07 * r), a=0.8)
                self.ball(L, R, qx, yb + 0.05 * r, 0.32 * r, (222, 98, 40) if i == 1 else (232, 230, 222), sub=0.45, shade=shade)
            else:
                # strong stream drags a pot float half under and leaves a little wake behind it
                sub = 0.42 + 0.18 * abs(flow) * (1 - self.tide * 0.3)
                if abs(flow) > 0.2:
                    # the stream's wake: a short tapering streak down-stream of it
                    wake = self.lit((214, 222, 226), (0, 0.4, 1), shade=shade)
                    sx = 1 if px >= 0 else -1
                    ln = r * (1.2 + 2.0 * abs(flow))
                    L.line([(x + sx * r * 0.8, yb + 0.1 * r), (x + sx * (r * 0.8 + 0.45 * ln), yb + 0.18 * r)],
                           wake, max(0.5 * s, 0.3 * r), a=0.28 * abs(flow))
                    L.line([(x + sx * (r * 0.8 + 0.45 * ln), yb + 0.18 * r), (x + sx * (r * 0.8 + ln), yb + 0.25 * r)],
                           wake, max(0.4 * s, 0.15 * r), a=0.16 * abs(flow))
                if i == 0:
                    # the dahn: a pole through its float with a flag that streams downwind (hangs in a calm)
                    pole = self.lit((40, 38, 36), (0, 1, 0.2), shade=shade)
                    hgt = DAHN_H * k
                    tx = x + lean * 0.35 * hgt
                    ty = yb - hgt * (1 - 0.06 * lean * lean)
                    L.line([(x, yb + 0.3 * r), (tx, ty)], pole, max(0.6 * s, 0.13 * r))
                    R.line([(x, yb - 0.3 * r), (x + lean * 0.35 * hgt, 2 * yb - ty)], pole * 0.6, max(0.6 * s, 0.13 * r))
                    fly = sm(0.5, 5.0, v)
                    fw, fh = 0.55 * r * 2.6, 0.75 * r * 2.0
                    fx = wind_x if abs(wind_x) > 0.15 else 1.0
                    flag = self.lit((214, 74, 40), (0.0, 0.9, 0.3), shade=shade)
                    droop = (1 - fly) * fh * 1.2
                    L.poly([(tx, ty), (tx + fx * fw * (0.4 + 0.6 * fly), ty + droop * 0.6 + 0.1 * fh),
                            (tx + fx * fw * (0.35 + 0.6 * fly), ty + fh + droop), (tx, ty + fh)], flag)
                self.ball(L, R, x, yb, r, alb, sub=sub, shade=shade, gloss=0.3)
        self.reflect(R)
        L.composite()

    # ------------------------------------------------------------ skerry --
    def skerry(self):
        """A low skerry in the bay, drawn as a lit height field from far to near (each grid point a column
        down to the water). The water climbs and leaves it with the tide: wet weed below, a grey crust of
        barnacles on the knobs; when covered, it shows through the shallow water, and in a wind the sea
        breaks over it."""
        W, H, s = self.W, self.H, self.s
        X0, Z0, D = sea_point(*SKERRY)
        h, mot = skerry_field()
        nb, na = h.shape
        wl = self.water_level()
        if h.max() < wl - 0.45 * TR:
            return
        az = math.atan2(X0, Z0)
        fx, fz = math.sin(az), math.cos(az)                    # ahead, along the view
        lx, lz = math.cos(az), -math.sin(az)                   # across it, to the right
        ha, hb = SKERRY_HALF
        a = np.linspace(-1, 1, na, dtype=np.float32)[None, :]
        b = np.linspace(-1, 1, nb, dtype=np.float32)[:, None]
        Xw = X0 + a * ha * lx + b * hb * fx
        Zw = Z0 + a * ha * lz + b * hb * fz
        xs, yt = self.proj(Xw, np.maximum(h, wl), Zw)
        _, yw = self.proj(Xw, wl + 0 * h, Zw)
        xs, yt, yw = xs.astype(np.float32), yt.astype(np.float32), yw.astype(np.float32)
        # its light: normals from the height field, the cloud shadow where it lies
        ga, gb = np.gradient(h, axis=1) / (2 * ha / (na - 1)), np.gradient(h, axis=0) / (2 * hb / (nb - 1))
        gX, gZ = ga * lx + gb * fx, ga * lz + gb * fz
        nrm = normalize(np.stack([gX, gZ, np.ones_like(h)], -1))     # east, north, up (world x is west, z south)
        shade = self.local_shade(float(xs.mean()), float(yw.mean()))
        light = self.light(nrm, shade)
        if self.pools:
            light = light + self.local(np.float32(xs.mean()), np.float32(yw.mean()))
        # weed (bladder wrack) low down, a grey crust of barnacles on the knobs, dark rock in the cracks
        weed = np.array([64, 56, 30], np.float32)
        crust = np.array([124, 120, 110], np.float32)
        rock = np.array([84, 80, 74], np.float32)
        z = sm(-0.17 * TR, 0.15 * TR, h + 0.09 * TR * mot)[..., None]
        alb = weed * (1 - z) + crust * z
        alb = alb * (1 - 0.3 * sm(0.3, 1.2, -mot)[..., None]) + rock * 0.3 * sm(0.3, 1.2, -mot)[..., None]
        alb = alb * (0.85 + 0.15 * sm(-1.5, 1.5, mot))[..., None]
        wet = np.exp(-np.maximum(h - wl, 0) / (0.17 * TR))[..., None]
        col = alb * (1 - 0.4 * wet) * light + self.hor_col * (0.16 * wet * nrm[..., 2:3] ** 4)
        # rasterise far to near at the layers' supersampling
        vis = h > wl - 0.45 * TR
        if not vis.any():
            return
        x0 = int(math.floor(xs[vis].min() - 8 * s))
        x1 = int(math.ceil(xs[vis].max() + 8 * s))
        y0 = int(math.floor(yt[vis].min() - 3 * s))
        y1 = int(math.ceil(yw[vis].max() + (yw[vis] - yt[vis]).max() + 6 * s))
        x0, x1, y0, y1 = max(0, x0), min(W, x1), max(0, y0), min(H, y1)
        if x1 <= x0 or y1 <= y0:
            return
        cx = x0 + (np.arange((x1 - x0) * SS, dtype=np.float32) + 0.5) / SS
        cy = (y0 + (np.arange((y1 - y0) * SS, dtype=np.float32) + 0.5) / SS)[:, None]
        n_r, n_c = len(cy), len(cx)
        rock_c = np.zeros((n_r, n_c, 3), np.float32)
        rock_a = np.zeros((n_r, n_c), np.float32)
        refl_c = np.zeros((n_r, n_c, 3), np.float32)
        refl_a = np.zeros((n_r, n_c), np.float32)
        under_c = np.zeros((n_r, n_c, 3), np.float32)
        under_a = np.zeros((n_r, n_c), np.float32)
        sea_t = np.array([62, 104, 100], np.float32) * (self.amb + 0.45 * self.sun_col * self.sun_str + 0.2 * MOON_COL * self.moon_str)
        breaks = sm(3.5, 9.0, self.wx.wind_ms)
        for j in range(nb - 1, -1, -1):
            xr = xs[j]
            if not (vis[j].any() and xr[-1] > x0 and xr[0] < x1):
                continue
            # only the columns this row of the field covers, and the rows its span and reflection reach
            k0 = max(0, int((xr[0] - x0) * SS))
            k1 = min(n_c, int(math.ceil((xr[-1] - x0) * SS)) + 1)
            r0 = max(0, int((float(yt[j][vis[j]].min()) - y0) * SS) - 1)
            r1 = min(n_r, int(math.ceil((float((2 * yw[j] - yt[j])[vis[j]].max()) - y0) * SS)) + 2)
            if k1 <= k0 or r1 <= r0:
                continue
            cxs, cys = cx[k0:k1], cy[r0:r1]
            dh = np.interp(cxs, xr, h[j] - wl)
            ytc = np.interp(cxs, xr, yt[j])[None, :]
            ywc = np.interp(cxs, xr, yw[j])[None, :]
            cc = np.stack([np.interp(cxs, xr, col[j, :, c]) for c in range(3)], -1)[None, :, :]
            shape = (r1 - r0, k1 - k0)
            up = dh > 0
            if up.any():
                span = (cys >= ytc) & (cys <= ywc + 0.5 / SS) & up[None, :]
                rock_c[r0:r1, k0:k1][span] = np.broadcast_to(cc, shape + (3,))[span]
                rock_a[r0:r1, k0:k1][span] = 1.0
                rspan = (cys > ywc) & (cys <= 2 * ywc - ytc) & up[None, :]
                refl_c[r0:r1, k0:k1][rspan] = np.broadcast_to(cc * 0.5, shape + (3,))[rspan]
                refl_a[r0:r1, k0:k1][rspan] = 1.0
            sunk = (dh <= 0) & (dh > -0.45 * TR)
            if sunk.any():
                # covered: the rock shows through the shallow water, and breaks it in a wind
                depth = np.clip(-dh / (0.45 * TR), 0, 1)
                m = (np.abs(cys - ywc) <= 0.6 / SS) & sunk[None, :]
                tint = 0.5 * (1 - depth) ** 1.2
                c2 = cc * 0.45 * (1 - depth[None, :, None]) + sea_t * (0.55 + 0.45 * depth[None, :, None])
                under_c[r0:r1, k0:k1][m] = np.broadcast_to(c2, shape + (3,))[m]
                under_a[r0:r1, k0:k1][m] = np.broadcast_to(tint[None, :], shape)[m]
        # the waterline: a thin wash along the foot of what stands out of the water
        below = rock_a == 0
        edge = below & ((np.roll(rock_a, 1, 0) > 0) | (np.roll(rock_a, 2, 0) > 0))
        edge[:2] = False
        wash = self.lit((214, 222, 224), (0, 0.4, 1), shade=shade)
        surge = 0.2 + 0.4 * sm(1.0, 8.0, self.wx.wind_ms)
        # the wash comes and goes along the edge, shifting a little each minute
        lap = sm(-0.3, 0.8, np.interp(cx / s * 0.02 + self.m * 0.37, np.arange(1024, dtype=np.float32) * 0.25,
                                       fnoise(4, 1024, 1.5, 1, 4412)[1], period=256.0))
        edge = edge * lap[None, :]
        # over the covered rock in a wind: broken white water, changing a little each minute
        if breaks > 0 and under_a.max() > 0:
            rr = np.random.default_rng([self.day.date.toordinal(), 4420, self.m])
            speck = (rr.random(under_a.shape) < 0.35) & (under_a > 0.25)
            under_c[speck] = under_c[speck] * (1 - breaks) + wash * breaks
            under_a[speck] = np.maximum(under_a[speck], 0.6 * breaks)

        def down(c, a_):
            hh, ww = (y1 - y0), (x1 - x0)
            a2 = a_.reshape(hh, SS, ww, SS).mean((1, 3))
            c2 = (c * a_[..., None]).reshape(hh, SS, ww, SS, 3).mean((1, 3))
            return c2 / np.maximum(a2, 1e-6)[..., None], a2[..., None]
        # the reflection, broken up by the ripples
        if refl_a.max() > 0:
            rc, ra = down(refl_c, refl_a)
            amp, k = self.refl_amp()
            off = ripple_rows(ra.shape[0], y0, s, amp)[:, None]
            rows = np.arange(ra.shape[0], dtype=np.float32)[:, None]
            colsr = np.arange(ra.shape[1], dtype=np.float32)[None, :] + off
            rc = np.stack([ndi.map_coordinates(rc[..., c], [rows + 0 * colsr, colsr], order=1, mode="nearest") for c in range(3)], -1)
            ra = ndi.map_coordinates(ra[..., 0], [rows + 0 * colsr, colsr], order=1, mode="nearest")[..., None]
            self.over(y0, y1, x0, x1, rc, ra * k)
        if under_a.max() > 0:
            uc, ua = down(under_c, under_a)
            self.over(y0, y1, x0, x1, uc, ua)
        if rock_a.max() > 0:
            rc, ra = down(rock_c, rock_a)
            self.over(y0, y1, x0, x1, rc, ra)
            fc = np.broadcast_to(wash, (n_r, n_c, 3)).astype(np.float32)
            wc, wa = down(fc, edge.astype(np.float32) if edge.dtype == bool else edge)
            self.over(y0, y1, x0, x1, wc, wa * surge)

    # ------------------------------------------------------------ the bay --
    def bay(self):
        """The skerry, the floats, the mooring buoys and the boats, from the farthest to the nearest; with them,
        by their waterlines, the creel boat, the dolphins and seals' heads (sealife.py)."""
        b = self.day.events.boat(self.t)
        yb = b[1] if b else MOORED[1]
        items = self.sea_items()
        if not items:
            self.sea_marks(0.0, yb)
            self.boats()
            self.moored_boat()
            self.sea_marks(yb, 2.0)
            return

        def sail():
            self.boats()
            self.moored_boat()
        lo = 0.0
        for y, draw in sorted(items + [(yb, sail)], key=lambda t: t[0]):
            self.sea_marks(lo, y)
            draw()
            lo = y
        self.sea_marks(lo, 2.0)
