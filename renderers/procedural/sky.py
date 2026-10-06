"""Sky: gradient, sun and moon, stars, the Milky Way, clouds, and things that fly."""
import functools
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

from core import *  # noqa: F401,F403

import astro
from scipy.special import ndtri
from stars import GAL, LINES, STAR_DEC, STAR_IDX, STAR_MAG, STAR_RA, STAR_TINT

PLANET_TINT = {"Mercury": (1.05, .96, .86), "Venus": (1.0, .98, .93), "Mars": (1.2, .78, .58),
               "Jupiter": (1.02, .97, .88), "Saturn": (1.06, .99, .80)}
# the near side's dark seas and bright craters: (east, north, half-width, half-height) on the unit disk
MARIA = [(0.82, 0.29, 0.10, 0.13), (0.51, 0.15, 0.19, 0.15), (0.27, 0.47, 0.13, 0.12), (-0.23, 0.55, 0.22, 0.17),
         (-0.72, 0.25, 0.20, 0.36), (-0.27, -0.36, 0.15, 0.12), (0.76, -0.14, 0.08, 0.13), (0.55, -0.27, 0.07, 0.07),
         (0.02, 0.82, 0.30, 0.05), (-0.57, -0.41, 0.07, 0.07), (0.07, 0.22, 0.06, 0.05), (-0.45, -0.05, 0.12, 0.12)]


def moon_maria(P, Q):
    m = 0
    for (p, q, w, h) in MARIA:
        m = np.maximum(m, np.exp(-(((P - p) / w) ** 2 + ((Q - q) / h) ** 2) ** 1.5))
    return sm(0.25, 0.75, m * (0.85 + 0.3 * sample(fnoise(128, 128, 2.6, 1.0, 77), Q * 30 + 64, P * 30 + 64)))


def moon_rays(P, Q):
    """Tycho, Copernicus and Aristarchus: small bright craters, Tycho with faint rays."""
    out = 0
    for (p, q, r) in ((-0.14, -0.68, 0.05), (-0.34, 0.17, 0.035), (-0.67, 0.40, 0.03)):
        out = out + np.exp(-((P - p) ** 2 + (Q - q) ** 2) / r ** 2)
    ang = np.arctan2(Q + 0.68, P + 0.14)
    rays = np.exp(-np.hypot(P + 0.14, Q + 0.68) / 0.45) * sm(0.6, 1.0, np.cos(ang * 9))
    return out + 0.25 * rays

# cloud layers: name, noise texture (h, w, beta, aniso, seed), texels per plane unit, height (km),
# wind speed up there relative to the surface, opacity, edge softness
CLOUD_LAYERS = [("high", (256, 2048, 2.5, 3.5, 61), 110.0, 9.0, 3.5, 0.45, 1.3),
                ("mid", (512, 2048, 2.8, 2.0, 5), 55.0, 3.5, 2.2, 0.93, 1.0),
                ("low", (512, 2048, 3.2, 1.3, 11), 24.0, 1.2, 1.5, 0.97, 0.9)]


def norm_ppf(p):
    return float(ndtri(min(max(p, 0.002), 0.998)))


@functools.lru_cache(None)
def sky_grid(W, H, k):
    """Altitude, azimuth and the east/north/up direction of every k-th pixel of the sky."""
    hz = int(round(VH * H))
    y = (np.arange(0, hz, k, dtype=np.float32) + 0.5 * k) / H
    x = (np.arange(0, W, k, dtype=np.float32) + 0.5 * k) / W
    alt = np.ascontiguousarray(np.broadcast_to(((VH - y) / VH * ALT_TOP)[:, None], (len(y), len(x))))
    az = np.ascontiguousarray(np.broadcast_to((180 + (x - 0.5) * AZ_SPAN)[None, :], (len(y), len(x))))
    ar, zr = np.radians(alt), np.radians(az)
    ca = np.cos(ar)
    return alt, az, ca * np.sin(zr), ca * np.cos(zr), np.sin(ar)


class SkyMixin:
    def sky(self):
        W, H, hz, sa = self.W, self.H, self.hz, self.sun_alt
        alt, az, e, n, u = sky_grid(W, H, 2)
        zen, mid, hor = keys(SKY_ZEN, sa), keys(SKY_MID, sa), keys(SKY_HOR, sa)
        tu = sm(6, 60, alt)[..., None]
        col = mid * (1 - tu) + zen * tu
        wh = np.exp(-np.maximum(alt, 0) / 7.0)[..., None]
        col = col * (1 - wh) + hor * wh

        self.sun_glow = None
        vis = sm(-14, -1, sa)
        if vis > 0:
            g = np.degrees(np.arccos(np.clip(e * self.sunv[0] + n * self.sunv[1] + u * self.sunv[2], -1, 1)))
            self.sun_glow = (0.55 * np.exp(-g / 2.2) * self.sun_vis + 0.30 * np.exp(-g / 9) + 0.15 * np.exp(-g / 30)) * vis
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
        ms = sm(-2, 15, self.moon_alt) * self.night * (0.25 + 0.75 * self.moon_bright)
        self.moon_sky = ms
        if ms > 0:
            col += np.array([14, 20, 38], np.float32) * ms * (0.6 + 0.4 * sm(40, 0, alt))[..., None]
            gm = np.degrees(np.arccos(np.clip(e * self.moonv[0] + n * self.moonv[1] + u * self.moonv[2], -1, 1)))
            col += (0.5 * np.exp(-gm / 1.6) + 0.22 * np.exp(-gm / 7) + 0.08 * np.exp(-gm / 25))[..., None] \
                * np.array([190, 205, 235], np.float32) * ms
        self.milky_way(col, e, n, u)
        self.sky_half = (alt, az)
        full = upsample(col, (hz, W))
        self.stars(full)
        self.sun_disk(full)
        self.moon_disk(full)
        self.comet(full)
        self.clouds(full)
        self.c[:hz] = full

    def milky_way(self, col, e, n, u):
        vis = sm(-10, -17, self.sun_alt) * (1 - 0.4 * sm(0, 25, self.moon_alt) * self.moon_bright)
        if vis < 0.01:
            return
        # local east/north/up -> equator of date -> J2000 -> galactic, as one rotation
        L, ph = math.radians(self.lst * 15), math.radians(self.day.lat)
        sL, cL, sp, cp = math.sin(L), math.cos(L), math.sin(ph), math.cos(ph)
        R = np.array([[-sL, -cL * sp, cL * cp], [cL, -sL * sp, sL * cp], [0, cp, sp]])
        M = (GAL @ astro.precession_matrix(self.jd).T @ R).astype(np.float32)
        gx = M[0, 0] * e + M[0, 1] * n + M[0, 2] * u
        gy = M[1, 0] * e + M[1, 1] * n + M[1, 2] * u
        gz = M[2, 0] * e + M[2, 1] * n + M[2, 2] * u
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

    def limiting_mag(self):
        """Faintest magnitude that shows: stars come out one by one at dusk; moonlight and haze hide the faint ones."""
        lim = float(np.interp(self.sun_alt, [-18, -15, -12, -9, -6, -4, -2, 0], [6.6, 6.1, 5.2, 3.8, 2.2, 1.2, -0.3, -1.5]))
        return lim - 1.3 * self.moon_bright * sm(0, 30, self.moon_alt) - 4.0 * self.wx.fog

    def stars(self, col):
        W, H, hz, s = self.W, self.H, self.hz, self.s
        lim = self.limiting_mag()
        if lim < -1.0:
            return
        day = self.day
        alt, az = astro.star_vectors_to_altaz(STAR_RA, STAR_DEC, self.jd, day.lat, day.lon)
        alt = alt + astro.refraction(alt)
        mag, tint = STAR_MAG, STAR_TINT
        # the planets join the catalogue for this frame
        pl = [(day.planets[k][0][self.m], day.planets[k][1][self.m], day.planets[k][2][self.m], PLANET_TINT[k]) for k in PLANET_TINT]
        alt = np.concatenate([alt, [p[0] for p in pl]])
        az = np.concatenate([az, [p[1] for p in pl]])
        mag = np.concatenate([mag, [p[2] for p in pl]])
        tint = np.concatenate([tint, np.array([p[3] for p in pl], np.float32)])
        x, y = to_screen(alt, az)
        X, Y = x * W, y * H
        ok = (alt > 0.4) & (X >= 0) & (X < W) & (Y >= 0) & (Y < hz - 1)
        tw = 1 + 0.12 * self.rng.standard_normal(len(mag))
        sig = max(0.55, 1.15 * s)
        fade = sm(lim + 0.4, lim - 1.0, mag)
        peak = np.minimum(255 * 10 ** (-0.17 * (mag + 0.5)), 360) * fade * tw * (0.35 + 0.65 * sm(0, 14, alt))
        energy = (peak * 2 * math.pi * sig * sig).astype(np.float32)
        ok &= energy > 0.5
        layer = np.zeros((hz, W, 3), np.float32)
        xi, yi = X[ok].astype(int), Y[ok].astype(int)
        for ch in range(3):
            np.add.at(layer[..., ch], (yi, xi), energy[ok] * tint[ok, ch])
            layer[..., ch] = ndi.gaussian_filter(layer[..., ch], sig)
        col += layer
        big = ok & (mag < 1.6)
        for i in np.nonzero(big)[0]:
            r = (6 + 4 * max(0.0, -1 - mag[i])) * s      # Venus and Jupiter get a wider halo
            self._add(col, X[i], Y[i], r, np.array([200, 215, 255], np.float32) * tint[i], 0.16 * peak[i] / 255)
        self.star_xy = (X, Y, ok)
        # faint constellation figures: connecting the dots
        lv = sm(-6, -12, self.sun_alt) * (1 - 0.35 * sm(0, 25, self.moon_alt) * self.moon_bright) * (1 - self.wx.fog)
        if lv < 0.02:
            return
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

    def sky_dir(self, v, alt, az):
        """Screen direction (right, down) of the great circle from the point (alt, az) toward unit vector v."""
        p = enu(alt, az)
        t = np.asarray(v, np.float32) - float(np.dot(v, p)) * p
        a, z = math.radians(alt), math.radians(az)
        dx = t @ np.array([math.cos(z), -math.sin(z), 0], np.float32)
        dy = -(t @ np.array([-math.sin(a) * math.sin(z), -math.sin(a) * math.cos(z), math.cos(a)], np.float32))
        n = math.hypot(dx, dy) + 1e-9
        return dx / n, dy / n

    def moon_disk(self, col):
        if self.moon_alt < -2:
            return
        x, y = to_screen(self.moon_alt, self.moon_az)
        x, y, R = x * self.W, y * self.H, 26 * self.s
        x0, x1 = int(max(0, x - R - 2)), int(min(self.W, x + R + 3))
        y0, y1 = int(max(0, y - R - 2)), int(min(self.hz, y + R + 3))
        if x0 >= x1 or y0 >= y1:
            return
        X = (np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - x) / R
        Y = (np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - y) / R
        X, Y = np.broadcast_arrays(X, Y)
        d = np.sqrt(X * X + Y * Y)
        Z = np.sqrt(np.clip(1 - d * d, 0, 1))
        # lunar north points roughly at the celestial pole, so the face tilts through the night
        ph = math.radians(self.day.lat)
        nx, ny = self.sky_dir(np.array([0, math.cos(ph), math.sin(ph)], np.float32), self.moon_alt, self.moon_az)
        P, Q = -ny * X + nx * Y, nx * X + ny * Y
        mar = moon_maria(P, Q)
        crat = sample(fnoise(128, 128, 1.2, 1.0, 78), Q * 40 + 64, P * 40 + 64)
        limb = 1 - 0.2 * d ** 2
        albedo = (1 - 0.34 * mar) * (1 + 0.06 * crat) * limb
        albedo += 0.35 * moon_rays(P, Q)
        # phase: light arrives from the sun's direction on the sky; the dark side keeps a little earthshine
        bx, by = self.sky_dir(self.sunv, self.moon_alt, self.moon_az)
        inc = math.acos(max(-1.0, min(1.0, 2 * self.moon_frac - 1)))
        lit = (X * bx + Y * by) * math.sin(inc) + Z * math.cos(inc)
        lit = sm(-0.04, 0.06, lit)
        shine = 0.05 * (1 - self.moon_frac) * self.night
        low = sm(14, 1, self.moon_alt)
        tone = np.array([238, 234, 220], np.float32) * (1 - low * np.array([0, 0.18, 0.42], np.float32))
        base = tone * (albedo * (lit + shine * (1 - lit)))[..., None]
        a = np.clip(1 - (d - 1) * R, 0, 1) * (0.45 + 0.55 * self.night)
        a = a * np.maximum(lit, self.night * 0.85)
        a = a[..., None]
        reg = col[y0:y1, x0:x1]
        reg[:] = reg * (1 - a) + base * a

    def clouds(self, col):
        """Three layers from the forecast: high cirrus streaks, mid-level fleece, low heaps or a grey lid."""
        sa = self.sun_alt
        alt, az = self.sky_half
        lv = self.sunv if sa > -12 else self.moonv
        ld = np.array([lv[0], -lv[1]], np.float32)
        ld /= np.linalg.norm(ld) + 1e-6
        lc, sc = keys(CLOUD_LIT, sa), keys(CLOUD_SHADE, sa)
        lc = lc + np.array([46, 52, 70], np.float32) * self.moon_sky
        wet = max(self.wx.rain, self.wx.snow, self.wx.drizzle * 0.6)
        hm = (np.exp(-alt / 9) * 0.55)[..., None]
        acc_c = np.zeros(alt.shape + (3,), np.float32)
        acc_a = np.zeros(alt.shape + (1,), np.float32)
        for i in range(3):
            got = self.cloud_layer(i, alt, az, detail=True)
            if got is None:
                continue
            dens, n0, rows, cols, tex = got
            name, op = CLOUD_LAYERS[i][0], CLOUD_LAYERS[i][5]
            n1 = sample(tex, rows + ld[1] * 5, cols + ld[0] * 5)
            lit = np.clip(0.62 + (n0 - n1) * (1.4 if name != "low" else 1.8), 0, 1)
            cover = self.layer_cover(i)
            if name == "low":
                # thick low cloud is dark underneath; a full lid is flatter and greyer
                thick = sm(0.0, 2.0, n0 - norm_ppf(1 - cover))
                lit = lit * (1 - 0.45 * thick) * (1 - 0.35 * sm(0.75, 1.0, cover))
                lit = lit * (1 - 0.5 * wet)
            lit = lit[..., None]
            cc = sc * (1 - 0.45 * wet) + (lc * (1 - 0.3 * wet) - sc * (1 - 0.45 * wet)) * lit
            if self.sun_glow is not None:
                cc += (self.sun_glow * (1 - 0.6 * dens))[..., None] * keys(GLOW_COL, sa) * (0.9 if name != "low" else 0.6)
            cc = cc * (1 - hm) + self.hor_col * hm
            if name == "high":   # thin ice cloud: barely there at night unless the moon lights it
                op = op * (1 - 0.8 * self.night * (1 - min(1.0, 2 * self.moon_sky)))
            al = (dens * op)[..., None]
            acc_c = acc_c * (1 - al) + cc * al
            acc_a = acc_a * (1 - al) + al
        if acc_a.max() <= 0.001:
            return
        hz, W = col.shape[:2]
        acc_c = upsample(acc_c, (hz, W))
        acc_a = upsample(acc_a, (hz, W))
        col *= 1 - acc_a
        col += acc_c

    def layer_cover(self, i):
        return (self.wx.cloud_high, self.wx.cloud_mid, self.wx.cloud_low)[i]

    def cloud_layer(self, i, alt, az, detail=False):
        """Density of cloud layer i (0 high, 1 mid, 2 low) toward the given directions, drifting with the wind."""
        name, tx, K, hk, wf, op, soft = CLOUD_LAYERS[i]
        cover = self.layer_cover(i)
        if cover < 0.01:
            return None
        a = np.radians(np.maximum(alt, 0.8))
        zr = np.radians(az)
        u, ca = np.sin(a), np.cos(a)
        Xp, Zp = ca * np.sin(zr) / u, -ca * np.cos(zr) / u
        de, dn = self.day.drift_e[self.m], self.day.drift_n[self.m]
        Xp = Xp - de * wf / hk
        Zp = Zp + dn * wf / hk
        if name == "high":   # cirrus streaks lie along the wind
            th = math.radians(self.wx.wind_dir_deg)
            Xp, Zp = Xp * math.cos(th) - Zp * math.sin(th), Xp * math.sin(th) + Zp * math.cos(th)
        tex = fnoise(*tx)
        rows, cols = Zp * K, Xp * K + 300 * i
        n0 = sample(tex, rows, cols)
        th = norm_ppf(1 - cover) + 0.45 * sample(fnoise(256, 512, 3.0, 1.5, 6 + i), rows * 0.1, cols * 0.1) * (1 - cover)
        dens = sm(th - 0.25 * soft, th + 0.6 * soft, n0) * sm(0.5, 6, alt)
        return (dens, n0, rows, cols, tex) if detail else dens

    def sun_visibility(self):
        """How much direct sun gets through the clouds at this minute (1 clear, 0 hidden)."""
        if self.sun_alt < -3:
            return 1.0
        through = 1.0
        alt, az = np.array([max(self.sun_alt, 0.5)], np.float32), np.array([self.sun_az], np.float32)
        for i in range(3):
            d = self.cloud_layer(i, alt, az)
            if d is None:
                continue
            k = (0.25, 0.85, 0.97)[i]
            through *= 1 - k * float(d[0])
        fog = self.wx.fog
        return through * (1 - 0.85 * fog)

    def sky_extras(self):
        s, W, H = self.s, self.W, self.H
        gulls = self.day.events.sky_gulls(self.t)
        if gulls:
            L = Layer(self, 0.40 * W, 0.05 * H, W, 0.50 * H)
            gc = np.array([70, 72, 82], np.float32) * (0.7 + 0.3 * self.amb / self.amb.max())
            for (gx, gy, sz, f) in gulls:
                gx, gy, sz = gx * W, gy * H, sz * 14 * s
                pts = [(gx - sz, gy - 0.1 * sz * f), (gx - 0.5 * sz, gy - 0.45 * sz * f), (gx, gy),
                       (gx + 0.5 * sz, gy - 0.45 * sz * f), (gx + sz, gy - 0.1 * sz * f)]
                L.line(pts, gc, 2.0 * s)
            L.composite()
        for (t0, d, yh) in self.day.events.geese:   # a skein of geese, a quarter of an hour to cross
            u = (self.t - t0) * 60 / 14
            if 0 <= u <= 1:
                L = Layer(self, 0, 0, W, 0.5 * H)
                gx, gy = (-0.05 + 1.1 * u if d > 0 else 1.05 - 1.1 * u) * W, (yh + 0.03 * math.sin(u * 3)) * H
                c = np.array([40, 40, 46], np.float32) * (0.6 + 0.4 * self.amb.mean() / 0.45)
                for i in range(11):
                    side = 1 if i % 2 else -1
                    j = (i + 1) // 2
                    bx, by = gx - d * j * 14 * s, gy + side * j * 7 * s + j * 2 * s
                    flap = math.sin(self.m * 2.1 + i)
                    L.line([(bx - 5 * s, by - 2 * s * flap), (bx, by), (bx + 5 * s, by - 2 * s * flap)], c, 1.3 * s)
                L.composite()
        met = self.day.events.meteor(self.m) if self.limiting_mag() > 2.5 else None
        if met:
            (ax, ay), (bx, by), bright = met
            L = Layer(self, min(ax, bx) * W - 10, min(ay, by) * H - 10, max(ax, bx) * W + 10, max(ay, by) * H + 10)
            for i in range(40):
                t0, t1 = i / 40, (i + 1) / 40
                L.line([((ax + (bx - ax) * t0) * W, (ay + (by - ay) * t0) * H),
                        ((ax + (bx - ax) * t1) * W, (ay + (by - ay) * t1) * H)],
                       (235, 240, 255), (0.6 + 2.2 * t1) * s, a=t1 ** 1.6 * 0.9 * bright)
            L.composite()
            self.glow(bx * W, by * H, 5 * s, (220, 230, 255), 0.6 * bright)
