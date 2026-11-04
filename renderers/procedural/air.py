"""Things in the air: far aircraft and their contrails, a hot-air balloon, a starling murmuration, wheeling
gulls, skeins of geese, and a kite.

When each appears is decided in events.py (Schedule._air and the older gull and geese schedules); this
module draws them, lit by the scene's own sun, moon and sky. In the shore kit's reference mode the schedules
are empty (day.py), so nothing here draws. Nothing here touches the frame's own random stream: every random
choice comes from a generator seeded by the date, the thing and the minute."""
import math

import numpy as np
from scipy import ndimage as ndi

from core import (ALT_TOP, AZ_SPAN, CLOUD_LIT, CLOUD_SHADE, GLOW_COL, SS, VH, Layer, fnoise, keys, normalize, sample,
                  sm, upsample)
from scipy.special import ndtri
from events import vnoise

R_EARTH = 6371.0
HIGH_WIND = 3.5          # the upper air moves this much faster than the surface wind (sky.py's high cloud)
# contrail splats are sorted into these widths (gaussian sigma, frame pixels); the wide ones are made on a
# coarser grid
SIGMAS = (0.7, 1.4, 2.8, 5.6, 11.2, 22.4, 44.8)
COARSE = (1, 1, 1, 2, 2, 4, 4)
# balloon envelopes: the colours of their gores, in order round the balloon
BALLOON_GORES = [((206, 54, 46), (244, 198, 66)),
                 ((44, 86, 168), (238, 234, 222)),
                 ((226, 120, 44), (52, 120, 74), (240, 210, 90)),
                 ((150, 60, 130), (236, 200, 90), (60, 140, 190), (220, 70, 60))]
# kites: the cloth's two colours (the tail's bows take them in turn)
KITE_COLOURS = [((204, 48, 44), (244, 200, 64)), ((40, 80, 164), (238, 234, 222)),
                ((232, 112, 40), (40, 40, 48)), ((46, 140, 96), (242, 214, 80))]


def unit_hash(*k):
    """A number in [0, 1) fixed by the integers k."""
    return float(np.random.default_rng([int(v) % (1 << 32) for v in k]).random())


class AirMixin:
    # ------------------------------------------------------------ geometry --
    def air_screen(self, E, N, U):
        """Frame pixels (x, y), altitude (deg) and distance (km) of points E, N, U km from the observer."""
        D = np.hypot(E, N)
        alt = np.degrees(np.arctan2(U - D * D / (2 * R_EARTH), D))
        az = np.degrees(np.arctan2(E, N)) % 360
        return (0.5 + (az - 180) / AZ_SPAN) * self.W, (VH - alt / ALT_TOP * VH) * self.H, alt, np.hypot(D, U)

    def high_drift(self, minutes):
        """How far the upper wind has carried the air since midnight (km east, north) at fractional minutes."""
        d = self.day
        x = np.clip(minutes, 0, 1440)
        i = np.minimum(np.floor(x).astype(int), 1439)
        f = x - i
        e = d.drift_e[i] * (1 - f) + d.drift_e[i + 1] * f
        n = d.drift_n[i] * (1 - f) + d.drift_n[i + 1] * f
        return e * HIGH_WIND, n * HIGH_WIND

    # ------------------------------------------------------ the high air --
    def high_air(self, col):
        """Contrails and the aircraft that make them, by day on a contrail day; aircraft lights by night.
        Drawn into the sky before the clouds, so cloud hides what is above it."""
        ev = self.day.events
        if not ev.flights:
            return
        sa = self.sun_alt
        trails = ev.contrails and sa > -7
        lights = sa < -3 and self.wx.rain < 0.3 and self.wx.snow < 0.3
        if not (trails or lights):
            return
        t = self.t
        live = []
        life = 0.5 + 30 * ev.persist ** 1.5           # minutes a trail stays (e-folding)
        reach = min(3 * life, 75) / 60 if trails else 0
        for i, f in enumerate(ev.flights):
            # a flight matters while it is within ~110 km, or its trail still is
            tc, v = f[0], f[4]
            if abs(t - tc) * 60 * v > 110 + v * reach * 60 + 80:
                continue
            live.append((i, f))
        if not live:
            return
        if trails:
            self.contrail_layer(col, live, life)
        for i, f in live:
            E, N, U = self.plane_now(f)
            x, y, alt, dist = self.air_screen(E, N, U)
            if not (0 <= x < self.W and 0 <= y < self.hz - 1) or alt < 2:
                continue
            if trails and sa > -4:
                self.plane_speck(col, x, y, alt, dist)
            if lights and f[5] < 0.55:
                self.plane_lights(col, i, x, y, alt, dist)

    def plane_now(self, f):
        E, N, U = self.day.events.plane_enu(f, self.t)
        return float(E), float(N), float(U)

    def contrail_layer(self, col, live, life):
        """Every trail behind every live flight, as gaussian splats along it: thin and bright behind the
        aircraft, then drifting with the upper wind, spreading and thinning until it is gone."""
        ev, s, W, hz, m = self.day.events, self.s, self.W, self.hz, self.m
        persist = ev.persist
        spread = 0.006 + 0.05 * persist                 # km of width gained per minute
        w0, tau0 = 0.06, 1.1
        ppr = W / math.radians(AZ_SPAN)                 # pixels per radian
        A = min(3 * life, 75.0)
        de0, dn0 = self.high_drift(np.array([m], np.float64))
        patch = fnoise(256, 256, 2.0, 1.0, 91)       # one texel is 4 km of the upper air
        oy, ox = (ev.seed * 0.37) % 256, (ev.seed * 0.61) % 256
        thr = float(ndtri(1 - (0.12 + 0.5 * persist)))       # the share of the sky where trails persist
        xs, ys, sg, wt = [], [], [], []
        for i, f in live:
            # ages (minutes) spaced so neighbouring splats overlap: finer where the trail is thin
            c = 0.22 / f[4]
            k = np.arange(int(math.log1p(A * spread / w0) / math.log1p(c * spread)) + 2)
            age = (w0 / spread) * np.expm1(k * math.log1p(c * spread))
            age = age[age <= A]
            te = m - age
            E, N, U = ev.plane_enu(f, te / 60)
            de, dn = self.high_drift(te)
            # the upper air is moist in patches that drift with it: there a trail lasts and spreads, elsewhere
            # it is gone within a minute
            q = sm(-0.3, 0.3, sample(patch, (N - dn) / 4 + oy, (E - de) / 4 + ox) - thr)
            loc = 0.4 + (life - 0.4) * q
            E, N = E + (de0[0] - de), N + (dn0[0] - dn)
            x, y, alt, dist = self.air_screen(E, N, U)
            width = w0 + spread * q * age
            sig = np.maximum(0.6 * s / 0.75, 0.42 * width / dist * ppr)
            ok = (alt > 0.5) & (x > -3 * sig) & (x < W + 3 * sig) & (y > -3 * sig) & (y < hz + 3 * sig)
            if not ok.any():
                continue
            # optical depth across the trail: forms a moment behind the aircraft, thins as it spreads, fades
            # with age; older trails break into lumps
            lump = 1 + (0.25 + 0.2 * persist) * sm(1, 6, age) * np.sin(age * 9.0 + i) * np.sin(age * 2.3 + 2 * i)
            lump *= 1 - 0.8 * sm(3, 15, age) * sm(0.2, 0.9, np.sin(age * 0.9 + 3 * i) * np.sin(age * 0.37 + i))
            od = tau0 * sm(0.0, 0.025, age) * (w0 / width) ** (0.35 - 0.2 * persist) * np.exp(-age / loc) * lump
            step = np.hypot(np.gradient(x), np.gradient(y))
            step = np.minimum(step, 3 * sig)
            w = od * math.sqrt(2 * math.pi) * sig * step
            ok &= w > 1e-4
            if not ok.any():            # every splat too faint to draw (2026-11-05 09:27 crashed on the empty box)
                continue
            xs.append(x[ok]), ys.append(y[ok]), sg.append(sig[ok]), wt.append(w[ok])
        if not xs:
            return
        x, y, sig, w = (np.concatenate(v) for v in (xs, ys, sg, wt))
        b = np.clip(np.rint(np.log2(sig / SIGMAS[0])), 0, len(SIGMAS) - 1).astype(int)
        # the union box of all splats, clipped to the sky
        X0 = int(max(0, math.floor((x - 3 * sig).min())))
        X1 = int(min(W, math.ceil((x + 3 * sig).max()) + 1))
        Y0 = int(max(0, math.floor((y - 3 * sig).min())))
        Y1 = int(min(hz, math.ceil((y + 3 * sig).max()) + 1))
        if X1 <= X0 or Y1 <= Y0:
            return
        X0, Y0 = X0 // 4 * 4, Y0 // 4 * 4         # so every coarse grid starts inside the box
        D = np.zeros((Y1 - Y0, X1 - X0), np.float32)
        for k in np.unique(b):
            sel = b == k
            f = COARSE[k]
            bx, by, bw = x[sel], y[sel], w[sel]
            pad = 3 * SIGMAS[k]
            gx0 = int(max(X0, math.floor(bx.min() - pad)) // f * f)
            gy0 = int(max(Y0, math.floor(by.min() - pad)) // f * f)
            gx1 = int(min(X1, math.ceil(bx.max() + pad) + 1))
            gy1 = int(min(Y1, math.ceil(by.max() + pad) + 1))
            if gx1 <= gx0 or gy1 <= gy0:
                continue
            gw, gh = -(-(gx1 - gx0) // f), -(-(gy1 - gy0) // f)
            g = self.splat(gh, gw, (bx - gx0) / f - 0.5, (by - gy0) / f - 0.5, bw / (f * f))
            g = ndi.gaussian_filter(g, SIGMAS[k] / f, mode="constant", truncate=3.0)
            if f > 1:
                g = upsample(g, (gh * f, gw * f))
            g = g[:gy1 - gy0, :gx1 - gx0]
            D[gy0 - Y0:gy1 - Y0, gx0 - X0:gx1 - X0] += g
        al = 1 - np.exp(-np.maximum(D, 0))
        # thin ice is barely there at night unless the moon lights it (as sky.py's high cloud)
        al *= 1 - 0.85 * self.night * (1 - min(1.0, 2 * self.moon_sky))
        yy, xx = np.nonzero(al > 2e-3)
        if not len(yy):
            return
        a = al[yy, xx][:, None]
        Y, X = yy + Y0, xx + X0
        sa = self.sun_alt + 2.0      # ten kilometres up, the trails keep the sun a little longer
        lc, sc = keys(CLOUD_LIT, sa), keys(CLOUD_SHADE, sa)
        lc = lc + np.array([46, 52, 70], np.float32) * self.moon_sky
        cc = np.broadcast_to(sc + (lc - sc) * 0.85, (len(Y), 3)).copy()
        if self.sun_glow is not None:
            g = self.sun_glow[np.minimum(Y // 2, self.sun_glow.shape[0] - 1), np.minimum(X // 2, self.sun_glow.shape[1] - 1)]
            cc += g[:, None] * keys(GLOW_COL, self.sun_alt) * 0.9
        alt = (VH - (Y + 0.5) / self.H) / VH * ALT_TOP
        hm = (np.exp(-alt / 9) * 0.55)[:, None]
        cc = cc * (1 - hm) + self.hor_col * hm
        col[Y, X] = col[Y, X] * (1 - a) + cc * a

    @staticmethod
    def splat(h, w, x, y, wt):
        """Bilinear splat of weights wt at fractional cell positions (x, y) into an (h, w) grid."""
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = (x - x0).astype(np.float32), (y - y0).astype(np.float32)
        out = np.zeros(h * w, np.float64)
        for dx, dy, k in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
            cx, cy = x0 + dx, y0 + dy
            ok = (cx >= 0) & (cx < w) & (cy >= 0) & (cy < h)
            out += np.bincount((cy[ok] * w + cx[ok]), weights=(wt * k)[ok], minlength=h * w)
        return out.reshape(h, w).astype(np.float32)

    def speck(self, col, x, y, r, c, a):
        """A tiny soft dot of colour c and peak cover a over col (h, w, 3)."""
        R = int(math.ceil(3 * r)) + 1
        x0, x1 = max(0, int(x) - R), min(col.shape[1], int(x) + R + 1)
        y0, y1 = max(0, int(y) - R), min(col.shape[0], int(y) + R + 1)
        if x0 >= x1 or y0 >= y1:
            return
        X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5 - x
        Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5 - y
        k = (a * np.exp(-(X * X + Y * Y) / (r * r)))[..., None]
        reg = col[y0:y1, x0:x1]
        reg[:] = reg * (1 - k) + np.asarray(c, np.float32) * k

    def plane_speck(self, col, x, y, alt, dist):
        """The aircraft at the head of its trail: a glint of sunlit metal, or a dark speck in shadow."""
        s = self.s
        lum = float(np.clip(0.25 + self.amb.mean() * 0.7 + 0.75 * self.sun_str, 0, 1.25))
        c = np.array([226, 228, 234], np.float32) * lum * self.sun_col / self.sun_col.max()
        haze = float(np.exp(-alt / 9) * 0.5)
        c = c * (1 - haze) + self.hor_col * haze
        self.speck(col, x, y, max(0.75, 1.3 * s * 18 / max(dist, 12)), c, 0.9 * (1 - haze))

    def plane_lights(self, col, i, x, y, alt, dist):
        """A night flight: a red beacon, the white tail light, and a strobe caught in some minutes."""
        s = self.s
        k = float(sm(150, 30, dist) * sm(1, 8, alt))
        if k <= 0:
            return
        self._add(col, x, y, 1.0 * s, np.array([255, 70, 55], np.float32), 1.1 * k)
        self._add(col, x - 1.5 * s, y, 0.7 * s, np.array([255, 245, 225], np.float32), 0.35 * k)
        if unit_hash(self.day.events.seed, 31, i, self.m) < 0.35:
            self._add(col, x + 0.8 * s, y, 1.1 * s, np.array([255, 255, 255], np.float32), 1.5 * k)

    # --------------------------------------------------- the lower air --
    def flocks(self):
        """Everything in the lower air, far to near: balloons, starlings, gulls, geese."""
        ev = self.day.events
        if ev.balloons:
            self.air_balloons()
        if ev.starlings:
            self.air_starlings()
        if ev.gulls:
            self.air_gulls()
        if ev.geese:
            self.air_geese()

    # ------------------------------------------------------------ balloons --
    def air_balloons(self):
        ev = self.day.events
        for b in ev.balloons:
            pos = ev.balloon(b, self.t)
            if pos:
                self.draw_balloon(b, *pos)

    def draw_balloon(self, b, xf, yf, burner):
        """A far hot-air balloon: an envelope of coloured gores lit by the low sun (from inside too when the
        burner fires), the basket hanging below on its cables."""
        s, W, H = self.s, self.W, self.H
        R = 8.5 * s * b["size"]                  # the envelope's radius, pixels
        x, y = xf * W, yf * H                    # the envelope's centre
        L = Layer(self, x - 1.3 * R - 2, y - 1.2 * R - 2, x + 1.3 * R + 2, y + 2.4 * R + 2)
        if not L.ok:
            return
        # the envelope, per pixel at the layer's supersampling
        px0, py0 = L.x0, L.y0
        hh, ww = (L.y1 - L.y0) * SS, (L.x1 - L.x0) * SS
        X = ((np.arange(ww, dtype=np.float32) + 0.5) / SS + px0 - x)[None, :] / R
        Y = ((np.arange(hh, dtype=np.float32) + 0.5) / SS + py0 - y)[:, None] / R
        X, Y = np.broadcast_arrays(X, Y)
        # profile: a sphere above, tapering to the mouth below
        top = Y < 0.25
        u = np.clip((Y - 0.25) / 1.2, 0, 1)
        r = np.where(top, np.sqrt(np.clip(1 - Y * Y, 0, 1)), 0.30 + 0.668 * (1 - u) ** 1.35)
        inside = (np.abs(X) < r) & (Y > -1) & (Y < 1.45)
        cover = np.clip((r - np.abs(X)) * R * SS * 0.5 + 0.5, 0, 1) * np.clip((1.45 - Y) * R * SS, 0, 1) * np.clip((Y + 1) * R * SS, 0, 1)
        if not inside.any():
            return
        sx = np.clip(X / np.maximum(r, 1e-3), -1, 1)          # sine of the longitude seen from here
        cz = np.sqrt(1 - sx * sx)
        slope = np.where(top, 0.0, 0.668 * 1.35 * (1 - u) ** 0.35 / 1.2)
        ny = np.where(top, -Y, -slope) / np.sqrt(1 + np.where(top, 0.0, slope * slope))
        nyc = np.sqrt(np.clip(1 - ny * ny, 0, 1))
        sph = np.stack([X, -Y, np.sqrt(np.clip(1 - X * X - Y * Y, 0, 1))], -1)
        tap = np.stack([sx * nyc, ny, cz * nyc], -1)
        n = np.where(top[..., None], sph, tap)                 # (right, up, toward us)
        enu = normalize(np.stack([-n[..., 0], n[..., 2], n[..., 1]], -1))
        lgt = self.light(enu)
        gores = np.array(BALLOON_GORES[b["colours"]], np.float32)
        G = 4 * len(gores)
        lon = np.arcsin(sx) + 0.15 * self.m + b["seed"] % 7
        gi = np.floor(lon / (2 * math.pi / G)).astype(int)
        alb = gores[gi % len(gores)]
        seam = np.abs((lon / (2 * math.pi / G)) % 1 - 0.5) > 0.42
        alb = alb * np.where(seam, 0.82, 1.0)[..., None]
        c = alb * lgt
        if burner:          # the fabric glows from inside, most near the mouth
            c += alb * np.array([1.0, 0.62, 0.32], np.float32) * (0.35 + 0.5 * sm(-0.6, 1.3, Y))[..., None] * 0.55
        haze = 0.13 + 0.1 * self.night
        c = c * (1 - haze) + self.hor_col * haze
        L.blit(px0, py0, c, cover * inside)
        # cables and basket
        dark = self.lit((70, 54, 40), (0, 1, 0.3)) * (1 - haze) + self.hor_col * haze
        my, by_ = y + 1.45 * R, y + 1.95 * R
        for e in (-1, 1):
            L.line([(x + e * 0.27 * R, my), (x + e * 0.17 * R, by_)], dark, 0.45 * s)
        L.poly([(x - 0.2 * R, by_), (x + 0.2 * R, by_), (x + 0.17 * R, by_ + 0.38 * R), (x - 0.17 * R, by_ + 0.38 * R)],
               self.lit((128, 96, 62), (0, 1, 0.3)) * (1 - haze) + self.hor_col * haze)
        L.composite()
        if burner:
            self.glow(x, my, 0.5 * R, (255, 170, 80), 0.35 * (0.3 + 0.7 * self.lights_on))

    # ---------------------------------------------------------- starlings --
    def air_starlings(self):
        """A murmuration: thousands of starlings as one folded sheet that turns and ripples, so the dark
        bands are where it is seen edge-on. Gathers before sunset, drops into its roost after."""
        st = self.day.events.starlings
        t = self.t
        if not st["t0"] <= t <= st["t1"]:
            return
        W, H = self.W, self.H
        tau, T = (t - st["t0"]) * 60, (st["t1"] - st["t0"]) * 60
        sd = st["seed"]

        def vn(k, p):
            return vnoise(sd + k, tau, p)
        rng = np.random.default_rng([sd, 0])        # the same birds all evening
        N = st["n"]
        ang = rng.uniform(0, 2 * math.pi, N)
        rad = np.sqrt(rng.random(N)) * (1 + 0.04 * rng.standard_normal(N))
        u, v = rad * np.cos(ang), rad * np.sin(ang)
        thick = rng.standard_normal(N) * 0.05
        lobe = rng.random(N)
        drop = rng.random(N)
        jit = rng.standard_normal((2, N)) * 0.012
        # the sheet's outline: stretched, bent, tapered and S-curved by smooth changes over minutes
        X = u * (1.0 + 0.35 * vn(1, 5.0))
        Y = v * (0.32 + 0.12 * vn(2, 4.0))
        Y = Y + 0.35 * vn(3, 3.5) * (X * X - 0.3) + 0.25 * vn(4, 4.5) * np.sin(2.2 * X)
        Y = Y * (1 + 0.45 * vn(5, 6.0) * X)
        # folds out of the sheet, travelling across it
        Z = (0.55 + 0.30 * vn(6, 3.0)) * np.sin((2.2 + 1.2 * vn(7, 5.0)) * X + (0.8 * vn(8, 4.0)) * Y + 1.1 * tau)
        Z = Z + 0.25 * np.sin(3.4 * Y - 1.6 * X + 0.7 * tau + 2) + thick
        # turn it: yaw shows the sheet edge-on now and then, pitch tips it, roll tilts it on the screen
        yaw, pitch, roll = 1.2 * vn(9, 4.0), 0.6 * vn(10, 5.0), 0.35 * vn(11, 6.0)
        X, Z = X * math.cos(yaw) + Z * math.sin(yaw), -X * math.sin(yaw) + Z * math.cos(yaw)
        Y, Z = Y * math.cos(pitch) + Z * math.sin(pitch), -Y * math.sin(pitch) + Z * math.cos(pitch)
        X, Y = X * math.cos(roll) - Y * math.sin(roll), X * math.sin(roll) + Y * math.cos(roll)
        # now and then a part breaks away and rejoins
        q = 0.3 * max(0.0, vn(12, 7.0))
        away = lobe < q
        X = X + away * (0.9 + 0.3 * vn(13, 3.0)) * np.sign(vn(14, 11.0) + 1e-3)
        Y = Y + away * 0.3 * vn(15, 3.0)
        # gathering: the flock grows as groups arrive; at the end the birds pour down into the roost
        scale = 0.040 * W * st["size"] * (0.65 + 0.35 * sm(0, 7, tau))
        k_end = sm(T - 9, T, tau)
        scale *= 1 - 0.35 * k_end
        cx = (st["x0"] + (st["x1"] - st["x0"]) * sm(0, T, tau) + 0.015 * vn(16, 7.0)) * W
        cy = (st["y"] + 0.006 * vn(17, 5.0)) * H
        sx = cx + scale * (X + jit[0])
        sy = cy - scale * (Y + jit[1])
        fall = np.clip(tau - (T - 9) - drop * 9, 0, None)                 # minutes since each bird dropped
        sy = sy + fall * fall * 0.004 * H
        sx = sx + (cx - sx) * np.clip(fall / 3, 0, 0.8)
        n_vis = int(N * (0.35 + 0.65 * sm(0, 8, tau)))
        sx, sy = sx[:n_vis], sy[:n_vis]
        ok = sy < self.hz - 1
        sx, sy = sx[ok], sy[ok]
        if not len(sx):
            return
        x0, x1 = int(max(0, sx.min() - 3)), int(min(W, sx.max() + 4))
        y0, y1 = int(max(0, sy.min() - 3)), int(min(self.hz, sy.max() + 4))
        if x1 <= x0 or y1 <= y0:
            return
        h, w = y1 - y0, x1 - x0
        g = self.splat(h * SS, w * SS, (sx - x0) * SS - 0.5, (sy - y0) * SS - 0.5, np.ones(len(sx), np.float32))
        g = g.reshape(h, SS, w, SS).sum((1, 3))
        a = (1 - np.exp(-0.8 * (self.s / 0.75) ** 2 * g))[..., None]
        haze = 0.22
        bird = np.array([24, 22, 28], np.float32) * (0.6 + 0.8 * float(self.amb.mean()))
        c = bird * (1 - haze) + self.hor_col * haze
        self.over(y0, y1, x0, x1, np.broadcast_to(c, (h, w, 3)), a)

    # --------------------------------------------------------------- gulls --
    def air_gulls(self):
        """Gulls wheeling over the bay: crooked wings, black tips, and a white underside that flashes when a
        bank tips it toward the sun."""
        ev, s, W, H, t = self.day.events, self.s, self.W, self.H, self.t
        gulls = ev.sky_gulls(t)
        if not gulls:
            return
        for (i, x, y, size, a, sg) in gulls:     # each on its own small layer: they are few and far apart
            x, y, sz = x * W, y * H, size * 17 * s
            L = Layer(self, x - 1.3 * sz, y - 1.3 * sz, x + 1.3 * sz, y + 1.3 * sz)
            if L.ok:
                self.draw_gull(L, i, x, y, sz, a, sg)
                L.composite()

    def draw_gull(self, L, i, x, y, sz, a, sg):
        # plan view: heading along the circle, wings along its radius; the circle is seen from below at the
        # same slant as its path (0.45), and up on the screen is up
        hx, hd = -math.sin(a) * sg, math.cos(a) * sg
        wx_, wd = math.cos(a), math.sin(a)
        fd, cu = 0.72, 0.9            # seen from well below: the wings keep most of their span
        Hs = np.array([hx, hd * fd])
        Ws = np.array([wx_, wd * fd])
        Us = np.array([0.0, -cu])
        # pose: mostly gliding with crooked wings, sometimes caught mid-beat
        r = unit_hash(self.day.events.seed, 32, i, self.m)
        if r < 0.65:
            wrist, tip = 0.22, -0.10
        elif r < 0.85:
            wrist, tip = 0.42, 0.55
        else:
            wrist, tip = -0.05, -0.45
        bank = math.radians(32)
        # the underside faces down and outward from the turn; in ENU the plan's x is west and its depth south
        n = np.array([-math.sin(bank) * wx_, -math.sin(bank) * wd, -math.cos(bank)], np.float32)
        sun = max(0.0, float(n @ self.sunv)) * self.sun_str
        # the underside is in its own shade against the sky (lit from below by the sea and the sky's sides)
        # until a bank turns it to the sun
        Lw = self.amb * 0.95 + self.bounce * 0.6 + self.sun_col * (0.10 * self.sun_str + 1.3 * sun)
        white = np.array([236, 238, 240], np.float32) * Lw
        grey = np.array([150, 156, 166], np.float32) * Lw
        black = np.array([34, 34, 38], np.float32) * (0.6 + 0.4 * Lw)
        P = lambda al, be, ga: (x + al * Hs[0] * sz + be * Ws[0] * sz + ga * Us[0] * sz,
                                y + al * Hs[1] * sz + be * Ws[1] * sz + ga * Us[1] * sz)
        for e in (-1, 1):
            # the inner wing lifts toward the turn's outside a little (the bank)
            lift = 0.18 * e
            root_f, root_b = P(0.16, 0.08 * e, 0), P(-0.14, 0.08 * e, 0)
            wr_f, wr_b = P(0.12, 0.48 * e, wrist + lift * 0.5), P(-0.16, 0.46 * e, wrist + lift * 0.5)
            tp = P(-0.30, 1.0 * e, tip + lift)
            mid_f, mid_b = P(-0.02, 0.76 * e, (wrist + tip) / 2 + lift * 0.75), P(-0.20, 0.72 * e, (wrist + tip) / 2 + lift * 0.75)
            L.poly([root_f, wr_f, mid_f, tp, mid_b, wr_b, root_b], white)
            L.line([wr_b, mid_b], grey, 0.5 * self.s)
            L.poly([mid_f, tp, mid_b], black)
        L.poly([P(0.42, 0, 0.02), P(0.18, 0.09, 0), P(-0.40, 0.05, 0), P(-0.48, 0, 0), P(-0.40, -0.05, 0), P(0.18, -0.09, 0)], white)

    # --------------------------------------------------------------- geese --
    def air_geese(self):
        """Skeins of geese in the migration months: a ragged V with uneven arms, each goose with its neck
        out and its own wingbeat, and often one straggling behind."""
        ev, s, W, H = self.day.events, self.s, self.W, self.H
        for k, (t0, d, yh) in enumerate(ev.geese):
            sk = ev.skeins[k]
            u = (self.t - t0) * 60 / sk["mins"]
            if not 0 <= u <= 1:
                continue
            gx = (-0.08 + 1.16 * u if d > 0 else 1.08 - 1.16 * u) * W
            # a skein heading away from us sinks toward the horizon as it crosses, one coming nearer climbs
            gy = (yh + 0.03 * math.sin(u * 3) + 0.14 * math.sin(math.radians(sk["psi"])) * (u - 0.5)) * H
            elev = math.radians(max(8.0, (VH - gy / H) / VH * ALT_TOP))
            fd, cu = math.sin(elev), math.cos(elev)
            span = 11.5 * s * sk["size"]                     # half the wingspan, pixels
            sp = 2.5 * span                                  # spacing along an arm
            psi = math.radians(sk["psi"])
            # plan axes: flight direction and its left, as (screen x, depth away from us)
            fx, fz = d * math.cos(psi), math.sin(psi)
            lx, lz = -fz, fx
            half = math.radians(sk["half"])
            n = sk["n"]
            near = max(1, int(round((n - 1) * sk["near"])))
            birds = [(0.0, 0.0, 0)]
            for j in range(1, near + 1):
                birds.append((j, -1, j))
            for j in range(1, n - near):
                birds.append((j, 1, n + j))
            if sk["straggler"]:
                jj = max(near, n - 1 - near) + 1.6 + 1.2 * unit_hash(sk["seed"], 1)
                birds.append((jj, -1 if near >= n - 1 - near else 1, 2 * n + 1))
            body = self.lit((86, 80, 72), [0, 0.3, -0.9])
            belly = self.lit((150, 140, 126), [0, 0.3, -0.9])
            pos = []
            for (j, side, key) in birds:
                if j == 0:
                    bx, bz = 0.0, 0.0
                else:
                    # a little ragged: each goose wanders off its place, slowly over the crossing
                    al = j * sp * (1 + 0.14 * vnoise(sk["seed"] + key, u * 40, 3.0))
                    lat = 0.18 * sp * vnoise(sk["seed"] + 500 + key, u * 40, 4.0)
                    bx = -al * math.cos(half) * fx + side * al * math.sin(half) * lx + lat * lx
                    bz = -al * math.cos(half) * fz + side * al * math.sin(half) * lz + lat * lz
                pos.append((gx + bx, gy + bz * fd, key))
            xs, ys = [p[0] for p in pos], [p[1] for p in pos]
            pad = 2 * span
            L = Layer(self, min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
            if not L.ok:
                continue
            for (px, py, key) in pos:
                beat = 2 * math.pi * unit_hash(sk["seed"], key, self.m)
                self.draw_goose(L, px, py, span, (fx, fz * fd), (lx, lz), fd, cu, beat, body, belly)
            L.composite()

    def draw_goose(self, L, x, y, span, fwd, left, fd, cu, beat, body, belly):
        fx, fy = fwd
        nrm = math.hypot(fx, fy) + 1e-6
        fx, fy = fx / nrm, fy / nrm
        lx, lz = left
        b = math.radians(10) + math.radians(38) * math.sin(beat)       # wing angle above the level
        s = self.s
        sh = (x + 0.12 * span * fx, y + 0.12 * span * fy)
        for e in (-1, 1):
            # wingtip in 3D: out to the side (screen x, and depth foreshortened), up by the beat, swept back
            tx = sh[0] + span * (e * lx * math.cos(b) - 0.22 * fx)
            ty = sh[1] + span * (e * lz * fd * math.cos(b) - cu * math.sin(b) - 0.22 * fy)
            mx, my = (sh[0] + tx) / 2, (sh[1] + ty) / 2
            L.poly([(sh[0] + 0.16 * span * fx, sh[1] + 0.16 * span * fy), (mx + 0.05 * span * fx, my + 0.05 * span * fy),
                    (tx, ty), (mx - 0.14 * span * fx, my - 0.14 * span * fy), (sh[0] - 0.22 * span * fx, sh[1] - 0.22 * span * fy)], body)
        # body, neck stretched out ahead, head; a paler belly
        L.poly([(x + 0.30 * span * fx, y + 0.30 * span * fy - 0.06 * span), (x - 0.42 * span * fx, y - 0.42 * span * fy - 0.07 * span),
                (x - 0.55 * span * fx, y - 0.55 * span * fy), (x - 0.42 * span * fx, y - 0.42 * span * fy + 0.07 * span),
                (x + 0.30 * span * fx, y + 0.30 * span * fy + 0.07 * span)], body)
        L.line([(x - 0.25 * span * fx, y - 0.25 * span * fy + 0.05 * span), (x + 0.2 * span * fx, y + 0.2 * span * fy + 0.05 * span)],
               belly, 0.6 * s)
        L.line([(x + 0.28 * span * fx, y + 0.28 * span * fy), (x + 0.72 * span * fx, y + 0.72 * span * fy)], body, 0.9 * s)
        L.ellipse(x + 0.78 * span * fx, y + 0.78 * span * fy, 0.10 * span, 0.08 * span, body)

    # ---------------------------------------------------------------- kite --
    def air_kite(self):
        """A kite on a windy day, flown from just beyond the frame: its line runs off the edge on the side
        the wind comes from, its tail streams downwind, and with the sun behind it the cloth glows."""
        kt = self.day.events.kite
        if not kt or not kt["t0"] <= self.t <= kt["t1"]:
            return
        s, W, H, m = self.s, self.W, self.H, self.m
        side, sd = kt["side"], kt["seed"]
        wx = self.wx
        tau = (self.t - kt["t0"]) * 60
        up = sm(0, 4, tau) * (1 - sm(kt["t1"] * 60 - kt["t0"] * 60 - 4, kt["t1"] * 60 - kt["t0"] * 60, tau))
        windy = sm(4, 12, wx.wind_ms)
        # the flyer's hand, just off the frame
        ax, ay = (-0.004 * W, 0.70 * H) if side < 0 else (1.004 * W, 0.845 * H)
        bx = (0.075 + 0.08 * kt["x"]) if side < 0 else (0.925 - 0.08 * kt["x"])
        kx = (bx - side * 0.012 * vnoise(sd, tau, 3.0) + 0.006 * vnoise(sd + 1, tau, 1.3)) * W
        ky = (0.33 - 0.10 * windy + 0.02 * vnoise(sd + 2, tau, 2.5) + 0.01 * vnoise(sd + 3, tau, 0.9)) * H
        ky = ay + (ky - ay) * up
        kx = ax + (kx - ax) * max(up, 0.2)
        tilt = math.radians(14 * vnoise(sd + 4, tau, 1.7) + 8 * side * (1 - windy))
        # the wind across the screen: an east wind (from 90) blows toward the right
        th = math.radians(wx.wind_dir_deg)
        wsx = math.sin(th)
        size = 28 * s
        L = Layer(self, min(ax, kx) - 12 * size, min(ay, ky) - 4 * size, max(ax, kx) + 12 * size, max(ay, ky) + 8 * size)
        if not L.ok:
            return
        # the line, sagging between hand and bridle
        bri = (kx + 0.15 * size * math.sin(tilt), ky + 0.15 * size * math.cos(tilt))
        pts = []
        for k in range(41):
            f = k / 40
            sag = 0.16 * (1 - 0.5 * windy) * math.hypot(ax - bri[0], ay - bri[1]) * 4 * f * (1 - f)
            pts.append((bri[0] + (ax - bri[0]) * f, bri[1] + (ay - bri[1]) * f + sag))
        line = self.lit((226, 220, 204), (0, 0.6, 0.8))
        for k in range(40):
            L.line([pts[k], pts[k + 1]], line, (0.5 + 0.6 * k / 40) * s, a=0.55)
        # the cloth: its face looks upwind toward the flyer and down a little
        n = normalize(np.array([0.45 * -side, 0.8, -0.35], np.float32))
        pal = KITE_COLOURS[kt["colours"]]
        # thin cloth: lit on the face we see, and glowing with the sky (and the sun, if behind it) through it
        lt = self.light(n) + 0.6 * self.amb
        back = max(0.0, -float(n @ self.sunv)) * self.sun_str
        glow = self.sun_col * back * 0.9

        def cloth(c):
            c = np.asarray(c, np.float32)
            return c * lt + c * glow

        ct, st_ = math.cos(tilt), math.sin(tilt)
        R = lambda px, py: (kx + px * size * ct - py * size * st_, ky + px * size * st_ + py * size * ct)
        frame = self.lit((60, 46, 36), (0, 0.6, 0.8))
        if kt["style"] < 2:          # a diamond: four panels in two colours, a cross of spars
            T, B, Lf, Rt, C = R(0, -0.62), R(0, 1.0), R(-0.55, 0), R(0.55, 0), R(0, 0)
            for (p, q), c in (((T, Lf), pal[0]), ((T, Rt), pal[1]), ((B, Lf), pal[1]), ((B, Rt), pal[0])):
                L.poly([C, p, q], cloth(c))
            L.line([T, B], frame, 0.7 * s)
            L.line([Lf, Rt], frame, 0.7 * s)
            L.line([T, Lf, B, Rt, T], frame, 0.45 * s, a=0.7)
            tail0 = B
        else:                        # a delta: a wide triangle with a keel, two colours
            T, Lf, Rt, C = R(0, -0.55), R(-1.0, 0.55), R(1.0, 0.55), R(0, 0.40)
            L.poly([T, Lf, C], cloth(pal[0]))
            L.poly([T, Rt, C], cloth(pal[1]))
            L.line([T, C], frame, 0.7 * s)
            L.line([Lf, T, Rt], frame, 0.5 * s, a=0.8)
            tail0 = C
        # the tail streams downwind and droops when the wind eases
        dx, dy = 0.75 * wsx, 1.0 + 0.6 * (1 - windy)
        nn = math.hypot(dx, dy)
        dx, dy = dx / nn, dy / nn
        tl = 4.2 * size
        tail = []
        for k in range(31):
            f = k / 30
            wv = 0.10 * tl * f * math.sin(6.0 * f - 0.9 * m + sd % 5) * (0.5 + 0.5 * windy)
            tail.append((tail0[0] + dx * tl * f - dy * wv, tail0[1] + dy * tl * f * (1 + 0.15 * f * (1 - windy)) + dx * wv))
        tcol = self.lit((214, 206, 190), (0, 0.6, 0.8))
        L.line(tail, tcol, 0.6 * s, a=0.85)
        for k in range(4, 31, 4):
            px, py = tail[k]
            c = cloth(pal[(k // 4) % 2])
            w = 0.16 * size
            L.poly([(px - w, py - 0.6 * w), (px + w, py + 0.6 * w), (px + w, py - 0.6 * w), (px - w, py + 0.6 * w)], c)
        L.composite()
