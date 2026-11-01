"""The observatory tower: masonry, dome, telescope, windows, door and clock.

The wall, the dome and the door are surfaces that never change, so their albedo, normals and
occlusion are made once per frame size (wall_maps, dome_maps, door_maps) and each minute only lights
them: the light comes from the scene, never from the drawing."""
import functools
import math
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

import astro
from core import *  # noqa: F401,F403
from stars import STAR_DEC, STAR_MAG, STAR_RA


def tex(u, v, seed, beta=2.0, aniso=1.0, n=256):
    """A periodic noise texture (zero mean, unit variance) sampled at texel coordinates u (across), v (down)."""
    u, v = np.broadcast_arrays(u, v)
    return sample(fnoise(n, n, beta, aniso, seed), v, u)


def rounded_inside(ex, ey, rc):
    """Distance to the edge of a rectangle with rounded corners, from the distances to its sides."""
    qx, qy = rc - ex, rc - ey
    return rc - np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) - np.minimum(np.maximum(qx, qy), 0)


@functools.lru_cache(maxsize=2)
def wall_maps(W, H):
    """The masonry: each stone has its own tone and tilt and a bevelled edge into a recessed joint, a
    few are darker or chipped; rain has streaked the stone under the cornice, the sills and the clock;
    the foot is damp, with moss in the joints and lichen, and the wall darkens where it meets the
    ground and under the cornice."""
    s = W / 3840
    T = TOWER
    cx, yb, yt, rt = T["cx"] * W, T["yb"] * H, T["yt"] * H, T["r"] * s
    rb = rt * 1.03
    et, eb = 1.2 * (yt / H - VH) * rt, 1.2 * (yb / H - VH) * rb
    x0, x1 = int(max(0, cx - rb - 2)), int(min(W, cx + rb + 3))
    y0, y1 = int(max(0, yt - abs(et) - 3)), int(min(H, yb + abs(eb) + 3))
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
    arc = np.arcsin(sv) * r
    hp = v * (yb - yt)
    # the courses, as before: 21 x 46 (at full size), each course shifted
    ch, sw = 21 * s, 46 * s
    ci = np.floor(hp / ch)
    fy = hp / ch - ci
    sx = (arc + hash2(ci, 7) * sw) / sw
    si = np.floor(sx)
    fx = sx - si
    t1, t2, t3 = hash2(ci, si), hash2(ci + 31.7, si - 11.3), hash2(ci - 17.9, si + 23.3)
    t4, t5, t6 = hash2(ci + 2.2, si + 5.5), hash2(ci - 8.1, si - 3.7), hash2(ci + 13.3, si + 0.9)
    U, V = arc / s, hp / s                      # texel coordinates on the unrolled wall
    wob = tex(U * 0.9, V * 0.9, 74, 1.7)
    ex = np.minimum(fx, 1 - fx) * sw * cv + 0.45 * s * wob      # no stone is quite square
    ey = np.minimum(fy, 1 - fy) * ch + 0.45 * s * tex(U * 0.9 + 91, V * 0.9, 74, 1.7)
    e = rounded_inside(ex, ey, 2.2 * s)
    mw, bw, D = 0.8 * s, 2.4 * s, 2.6 * s
    face = sm(mw, mw + bw, e)                   # 0 in the joint, 1 on the face of the stone
    rough = tex(U * 2.2, V * 2.2, 75, 1.9)
    pill = (1 - (2 * fx - 1) ** 2) * (1 - (2 * fy - 1) ** 2)
    tilt = 0.10 * ((t5 - 0.5) * (2 * fx - 1) * sw * cv + (t6 - 0.5) * (2 * fy - 1) * ch)
    h = face * (D * (1 + 0.6 * pill) + tilt + 0.5 * s * rough) + (1 - face) * 0.25 * s * rough
    # a few stones have lost a corner
    kx, ky = (t4 * 7 % 1 > 0.5).astype(np.float32), (t4 * 13 % 1 > 0.5).astype(np.float32)
    dc = np.hypot((fx - kx) * sw * cv, (fy - ky) * ch)
    rc = (0.35 + 0.3 * (t4 * 29 % 1)) * ch
    chip = (t4 < 0.14) * sm(rc, rc * 0.55, dc + 0.8 * s * wob)
    h = h - chip * D * 1.6 * (1 - dc / (rc + 1e-3))
    # tone: every stone its own, a few much darker, a few pale; mottled within
    val = 0.85 + 0.28 * t1
    val = np.where(t2 < 0.08, val * 0.78, np.where(t2 > 0.94, val * 1.09, val))
    warm = (t3 - 0.5) * 0.07
    mott = tex(U * 0.8, V * 0.8, 76, 2.0)
    fine = tex(U * 2.6, V * 2.6, 77, 1.3)
    alb = np.array([176, 166, 147], np.float32) * (val * (1 + 0.065 * mott + 0.03 * fine))[..., None]
    alb = alb * (1 + warm[..., None] * np.array([1.0, 0.25, -1.0], np.float32))
    alb = alb * (1 + 0.07 * chip)[..., None]
    mortar = np.array([140, 132, 116], np.float32) * (1 + 0.05 * fine)[..., None]
    alb = alb * face[..., None] + mortar * (1 - face[..., None])
    # rain streaks: under the cornice, the window sills and the clock
    streak = sample(fnoise(64, 512, 2.0, 0.08, 73), V * 0.05, U * 1.2)
    stain = sm(0.22, 0.0, v) * sm(-0.3, 1.0, streak) * 0.34
    for wsv in (-0.52, 0.52):
        dy_ = Y - (0.548 * H + 49 * s)
        aw = math.asin(wsv) * rt
        stain = stain + 0.42 * sm(0, 5 * s, dy_) * sm(120 * s, 8 * s, dy_) * sm(20 * s, 9 * s, np.abs(arc - aw)) \
            * sm(-0.6, 1.0, streak)
    Rc = CLOCK["R"] * s * 1.2
    dxc = np.abs(dx)
    yc = CLOCK["y"] * H + np.sqrt(np.clip(Rc ** 2 - dxc ** 2, 0, None))
    dy_ = Y - yc
    stain = stain + 0.36 * (dxc < Rc * 0.85) * sm(0, 4 * s, dy_) * sm(80 * s, 6 * s, dy_) * sm(-0.4, 1.0, streak)
    alb = alb * (1 - np.clip(stain, 0, 0.55))[..., None]
    # the damp foot, with moss in its joints and on the lowest stones, and lichen here and there
    low = tex(U * 0.35, V * 0.35, 78, 2.2)
    damp = sm(0.80, 0.97, v + 0.035 * low)
    alb = alb * (1 - 0.24 * damp)[..., None]
    alb = alb + (np.array([92, 100, 76], np.float32) - alb) * (0.18 * damp)[..., None]
    mn = tex(U * 1.1, V * 1.1, 79, 1.8)
    moss = np.clip(damp * sm(0.0, 1.2, mn + 0.9 * (1 - face) + 0.4 * sm(0.93, 1.0, v)), 0, 1) * 0.75
    mossc = np.array([74, 94, 52], np.float32) * (1 + 0.12 * fine)[..., None]
    alb = alb + (mossc - alb) * moss[..., None]
    ln = tex(U * 1.6, V * 1.6, 80, 1.5)
    lichen = sm(1.55, 2.05, ln) * face * (0.3 + 0.7 * sm(0.2, 0.9, v)) * 0.75
    alb = alb + (np.array([176, 172, 138], np.float32) - alb) * lichen[..., None]
    h = h + 0.5 * s * (moss + lichen)
    # normals: the round wall, tilted by the stones' relief
    nrm = np.stack([-sv, cv, np.zeros_like(sv)], -1)
    nrm = bump_normal(nrm, ndi.gaussian_filter(h, 0.6 * s), 1.0)
    # occlusion: in the joints, under the cornice, and down at the ground
    joint = 0.66 + 0.34 * sm(0.0, mw + 0.5 * bw, e)
    ao = joint * (0.58 + 0.42 * sm(0.0, 0.07, v)) * (0.6 + 0.4 * sm(1.0, 0.92, v)) * (1 - 0.35 * chip * (1 - dc / (rc + 1e-3)))
    cav = (0.8 + 0.2 * cv) * (0.85 + 0.15 * joint)     # the joints and the turning wall hide some of every light
    return SimpleNamespace(box=(x0, y0, x1, y1), X=X, Y=Y, cov=cov[..., None].astype(np.float32),
                           alb=alb.astype(np.float32), nrm=nrm.astype(np.float32), ao=ao.astype(np.float32),
                           cav=cav[..., None].astype(np.float32))


@functools.lru_cache(maxsize=2)
def dome_maps(W, H):
    """The dome's copper: sixteen gores between standing seams, each gore in sheets lapped over the one
    below, every sheet its own shade of patina, with verdigris run down from the seams."""
    s = W / 3840
    cx, yt = TOWER["cx"] * W, TOWER["yt"] * H
    cy, R = yt - 16 * s, TOWER["r"] * s * 0.99
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
    clat = np.cos(lat)
    gore = np.floor((lon + 11.25) / 22.5)
    ribd = np.abs(((lon + 11.25) % 22.5) - 11.25) * math.pi / 180 * R * clat
    # sheets: about 11 degrees of latitude each, staggered from gore to gore
    lstep = 11.0
    ls = (np.degrees(lat) + 30 + 5.5 * (gore % 2)) / lstep
    sheet = np.floor(ls)
    fl = ls - sheet
    sd = np.minimum(fl, 1 - fl) * lstep * math.pi / 180 * R          # px to the nearest lap
    lap = sm(1.3 * s, 0.2 * s, fl * lstep * math.pi / 180 * R)      # the lower edge of a sheet, over the next
    h = 1.5 * s * sm(2.0 * s, 0.3 * s, ribd) + 0.9 * s * lap * sm(0.4 * s, 1.4 * s, ribd)
    streak = sample(fnoise(256, 256, 2.0, 0.12, 61), Y * 0.6 / s + 0 * X, X * 0.6 / s + 0 * Y)
    fine = tex(X * 1.8 / s, Y * 1.8 / s, 62, 1.5)
    p1, p2 = hash2(gore, sheet), hash2(gore + 7.3, sheet - 2.1)
    # patina: streaked as the rain runs down, every sheet its own shade, with the pale verdigris washed
    # out from under each lap and along the seams
    alb = np.array([76, 137, 116], np.float32) * (1 + 0.13 * streak + 0.05 * fine + 0.12 * (p2 - 0.5))[..., None]
    verd = sm(0.5, 1.3, 0.7 * streak + 0.7 * sm(0.45, 0.0, fl) + 0.5 * sm(3 * s, 0, ribd) + 0.6 * (p1 - 0.5))
    alb = alb + (np.array([112, 172, 150], np.float32) - alb) * (0.6 * verd)[..., None]
    alb = alb * (1 - 0.38 * sm(1.4 * s, 0.3 * s, ribd) - 0.06 * lap)[..., None]
    nrm = bump_normal(nrm, h, 1.0)
    # the skirt below the cornice turns away from the sky and into its shadow
    ao = (0.5 + 0.5 * sm(-0.28, 0.06, sy)) * (0.9 + 0.1 * sm(0.3 * s, 1.6 * s, sd))
    return SimpleNamespace(box=(x0, y0, x1, y1), sx=sx, sy=sy, rho=rho, z=z, cov=cov, nrm=nrm.astype(np.float32),
                           alb=alb.astype(np.float32), ao=ao.astype(np.float32), ribd=ribd)


@functools.lru_cache(maxsize=2)
def door_maps(W, H):
    """The door, at the layer's supersampled resolution: six planks, each its own tone, grained along
    their length, bevelled into dark gaps; greyed and darker near the step; set back in the arch."""
    s = W / 3840
    cx, yb = TOWER["cx"] * W, TOWER["yb"] * H
    dw, dh = 34 * s, 128 * s
    dyb = yb + 12 * s
    ox, oy = math.floor(cx - dw - 1), math.floor(dyb - dh - 1)
    nx, ny = (math.ceil(cx + dw + 1) - ox) * SS, (math.ceil(dyb + 1) - oy) * SS
    X = ox + (np.arange(nx, dtype=np.float32)[None, :] + 0.5) / SS
    Y = oy + (np.arange(ny, dtype=np.float32)[:, None] + 0.5) / SS
    X, Y = np.broadcast_arrays(X, Y)
    dx, ys = X - cx, dyb - dh + dw
    edge = np.where(Y < ys, dw - np.hypot(dx, Y - ys), dw - np.abs(dx))
    cov = np.clip(edge * SS + 0.5, 0, 1) * np.clip((dyb - Y) * SS + 0.5, 0, 1)
    pw = 2 * dw / 6
    k = np.floor((X - (cx - dw)) / pw)
    fx = (X - (cx - dw)) / pw - k
    pe = np.minimum(fx, 1 - fx) * pw
    t1, t2 = hash2(k, 3.3), hash2(k, 17.1)
    grain = tex(X / s * 1.4 + 37 * k, Y / s * 0.09 + 11 * k, 82, 1.4, 0.12)
    gap = sm(0.8 * s, 0.25 * s, pe)
    alb = np.array([104, 63, 39], np.float32) * ((0.86 + 0.26 * t1) * (1 + 0.11 * grain) * (1 - 0.6 * gap))[..., None]
    alb = alb * (1 + (t2 - 0.5)[..., None] * 0.10 * np.array([1, 0, -1], np.float32))
    foot = sm(dyb - 26 * s, dyb, Y)
    alb = alb * (1 - 0.16 * foot)[..., None]
    alb = alb + (np.array([92, 82, 72], np.float32) - alb) * (0.22 * foot)[..., None]
    h = 1.6 * s * sm(0.3 * s, 2.0 * s, pe) + 0.25 * s * grain
    nrm = np.broadcast_to(normalize(np.array([0, 1, 0.1], np.float32)), X.shape + (3,))
    nrm = bump_normal(nrm, h * SS, 1.0)            # the gradient is per supersampled pixel
    ao = (0.62 + 0.38 * sm(0, 8 * s, edge)) * (0.8 + 0.2 * sm(0, 1.5 * s, pe))
    return SimpleNamespace(origin=(ox, oy), X=X, Y=Y, edge=edge, ys=ys, cov=cov, alb=alb.astype(np.float32),
                           nrm=nrm.astype(np.float32), ao=ao.astype(np.float32), dw=dw, dyb=dyb, cx=cx)


class TowerMixin:
    def cylinder(self, cx, yt, yb, rt, rb, albedo_fn, haze=0.0, local=True, ell_k=1.2, nrm_fn=None):
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
        if nrm_fn is not None:
            nrm = nrm_fn(nrm, sv, v, X, Y, r)
        L = self.light(nrm) * (0.8 + 0.2 * cv)[..., None]
        if local and self.pools:
            L = L + self.local(X, Y)
        col = alb * L
        if haze:
            col = col * (1 - haze) + self.hor_col * haze
        self.over(y0, y1, x0, x1, col, cov[..., None])

    def tower(self):
        s, W, H = self.s, self.W, self.H
        tw = self.tw
        cx, yb, yt, r = tw["cx"], tw["yb"], tw["yt"], tw["r"]
        M = wall_maps(W, H)
        x0, y0, x1, y1 = M.box
        L = self.light(M.nrm, ao=M.ao) * M.cav
        if self.pools:
            L = L + self.local(M.X, M.Y)
        self.over(y0, y1, x0, x1, M.alb * (1 - 0.3 * self.wx.wet) * L, M.cov)
        # dome, then the cornice ring that it sits on
        cy = yt - 16 * s
        self.dome(cx, cy, r * 0.99)

        def cornice(sv, v, X, Y, rr):
            arc = np.arcsin(sv) * rr
            fx = (arc / (16 * s)) % 1.0
            dent = ((fx < 0.35) & (v > 0.62))[..., None]
            base = np.array([198, 190, 172], np.float32) * (1 - 0.1 * (v > 0.55))[..., None]
            base = base * (1 + 0.04 * tex(arc / s * 1.5, Y / s * 1.5, 81, 1.6))[..., None]
            return np.where(dent, base * 0.55, base)

        def moulding(nrm, sv, v, X, Y, rr):
            # a rounded lip on top, a fascia, a fillet, the dentils (bevelled blocks), a soffit under them
            arc = np.arcsin(sv) * rr
            fx = (arc / (16 * s)) % 1.0
            up = 0.9 * sm(0.22, 0.0, v) - 0.5 * sm(0.53, 0.58, v) * sm(0.64, 0.6, v) - 0.7 * sm(0.9, 1.0, v)
            side = (v > 0.62) * (sm(0.42, 0.35, fx) - sm(0.93, 1.0, fx)) * 0.8
            t = np.stack([-np.sqrt(1 - sv ** 2), -sv, np.zeros_like(sv)], -1)      # along the ring, to screen right
            return normalize(nrm + up[..., None] * np.array([0, 0, 1], np.float32) + side[..., None] * t)
        self.cylinder(cx, cy, yt + 8 * s, r * 1.08, r * 1.08, cornice, nrm_fn=moulding)
        self.telescope(cx, cy, r * 0.99)
        self.tower_details()

    def dome(self, cx, cy, R):
        s = self.s
        x0, x1 = int(cx - R - 2), int(cx + R + 3)
        y0, y1 = int(cy - R - 2), int(cy + 0.35 * R)
        M = dome_maps(self.W, self.H)
        x0, y0, x1, y1 = M.box
        sx, sy, rho, z, cov, nrm, alb = M.sx, M.sy, M.rho, M.z, M.cov, M.nrm, M.alb
        if self.wx.snow_cover > 0.02:
            rib = sm(1.6 * s, 0.4 * s, M.ribd)
            cap = (sm(0.15, 0.55, sy) * min(1.0, self.wx.snow_cover * 1.6) * (1 - 0.6 * rib))[..., None]
            alb = alb * (1 - cap) + np.array([236, 240, 246], np.float32) * cap
        spec_dir = normalize(self.sunv + np.array([0, 1, 0], np.float32))
        spec = np.clip(nrm @ spec_dir, 0, 1) ** 40 * self.sun_str * (0.5 + 0.6 * self.wx.wet)
        col = alb * self.light(nrm, ao=M.ao) + spec[..., None] * 255 * self.sun_col
        col += (self.wx.wet * 0.12 * sm(0.0, 0.8, sy))[..., None] * self.hor_col
        if self.observing:
            mx, my = self.scope_target()
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
        self.over(y0, y1, x0, x1, col, cov[..., None])
        L = Layer(self, cx - 40 * s, cy - R - 64 * s, cx + 40 * s, cy - R + 4 * s)
        brass = self.lit((176, 136, 64), (0, 0.6, 0.8))
        L.line([(cx, cy - R + 2 * s), (cx, cy - R - 48 * s)], brass * 0.8, 2.2 * s)
        L.ellipse(cx, cy - R - 6 * s, 5.5 * s, 5.5 * s, brass)
        # a weathervane: the cross shows north and east, the arrow points into the wind
        iron = self.lit((40, 38, 36), (0, 0.6, 0.8))
        top = cy - R - 30 * s
        L.line([(cx - 14 * s, top), (cx + 14 * s, top)], iron, 1.4 * s)
        L.line([(cx, top - 5 * s), (cx, top + 5 * s)], iron, 1.4 * s)
        for ex, ey in ((cx - 14 * s, top), (cx + 14 * s, top), (cx, top - 5 * s), (cx, top + 5 * s)):
            L.ellipse(ex, ey, 1.6 * s, 1.6 * s, brass)
        A = math.radians(self.wx.wind_dir_deg)
        dx, dy = -math.sin(A), math.cos(A) * 0.35
        ln, ay = 20 * s, cy - R - 44 * s
        hx, hy, tx, ty = cx + dx * ln, ay + dy * ln, cx - dx * ln, ay - dy * ln
        L.line([(tx, ty), (hx, hy)], iron, 1.8 * s)
        px, py = -dy, dx
        L.poly([(hx + dx * 6 * s, hy + dy * 6 * s), (hx + px * 4 * s, hy + py * 4 * s), (hx - px * 4 * s, hy - py * 4 * s)], iron)
        L.poly([(tx, ty), (tx - dx * 5 * s + px * 7 * s, ty - dy * 5 * s + py * 7 * s - 3 * s),
                (tx - dx * 9 * s, ty - dy * 9 * s - 2 * s), (tx - dx * 5 * s - px * 7 * s, ty - dy * 5 * s - py * 7 * s + 1 * s)], iron)
        L.composite()

    def scope_target(self):
        """Where the telescope looks, as screen fractions: the moon when it is up and lit, else the
        brightest planet, else the brightest star well up; chosen on the hour and then tracked."""
        day, m = self.day, self.m
        h0 = min(1440, (m // 60) * 60)
        if day.moon_alt[h0] > 10 and self.moon_alt > 6 and day.moon_frac[h0] > 0.12:
            return to_screen(self.moon_alt, self.moon_az)
        best = None
        for name, (alt, az, mag) in day.planets.items():
            if alt[h0] > 12 and alt[m] > 6 and mag[h0] < 1.2 and (best is None or mag[h0] < best[0]):
                best = (mag[h0], alt[m], az[m])
        if best:
            return to_screen(best[1], best[2])
        alt, az = astro.star_vectors_to_altaz(STAR_RA[:85], STAR_DEC[:85], float(day.jd[h0]), day.lat, day.lon)
        ok = (alt > 25) & (np.abs(az - 180) < 100)
        i = int(np.argmin(np.where(ok, STAR_MAG[:85], 99)))
        alt, az = astro.star_vectors_to_altaz(STAR_RA[i:i + 1], STAR_DEC[i:i + 1], self.jd, day.lat, day.lon)
        return to_screen(float(alt[0]), float(az[0]))

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
            jt = self.lit((140, 132, 116), nrm, wx, wy)
            for g in (0.55, 1.15, 1.99, 2.59):
                L.line([(wx + ww * math.cos(g), wy - wh - ww * math.sin(g)),
                        (wx + (ww + 6 * s * k) * math.cos(g), wy - wh - (ww + 6 * s * k) * math.sin(g))], jt, 0.9 * s)
            for yy in (wy - wh * 0.2, wy + wh * 0.45):
                for side in (-1, 1):
                    L.line([(wx + side * ww, yy), (wx + side * (ww + 6 * s * k), yy)], jt, 0.9 * s)
            reveal = self.lit((70, 70, 70), nrm, wx, wy) * 0.8
            L.poly([(wx - ww, wy + wh), (wx + ww, wy + wh), (wx + ww, wy - wh), (wx - ww, wy - wh)], reveal)
            L.ellipse(wx, wy - wh, ww, ww, reveal)
            glass = self.lit((42, 50, 62), nrm) + self.amb * 30
            wl = self.windows_lit
            glass = glass * (1 - wl) + np.array([255, 190, 112], np.float32) * wl
            gi = 1.4 * s * k
            L.poly([(wx - ww + gi, wy + wh), (wx + ww - gi, wy + wh), (wx + ww - gi, wy - wh), (wx - ww + gi, wy - wh)], glass)
            L.ellipse(wx, wy - wh, ww - gi, ww - gi, glass)
            mull = self.lit((60, 52, 44), nrm)
            L.line([(wx, wy - wh - ww), (wx, wy + wh)], mull, 2.2 * s)
            L.line([(wx - ww, wy + 2 * s), (wx + ww, wy + 2 * s)], mull, 2.2 * s)
            sill = (196 * 1.06, 188 * 1.06, 170 * 1.06)
            L.poly([(wx - ww - 8 * s * k, wy + wh + 4 * s), (wx + ww + 8 * s * k, wy + wh + 4 * s),
                    (wx + ww + 8 * s * k, wy + wh + 9 * s), (wx - ww - 8 * s * k, wy + wh + 9 * s)], self.lit(sill, nrm, wx, wy))
            L.poly([(wx - ww - 8 * s * k, wy + wh + 3 * s), (wx + ww + 8 * s * k, wy + wh + 3 * s),
                    (wx + ww + 8 * s * k, wy + wh + 5.5 * s), (wx - ww - 8 * s * k, wy + wh + 5.5 * s)],
                   self.lit(sill, normalize([-sv * 0.5, k * 0.5, 0.85]), wx, wy))
            L.line([(wx - ww - 8 * s * k, wy + wh + 9.3 * s), (wx + ww + 8 * s * k, wy + wh + 9.3 * s)],
                   self.lit((150, 142, 126), normalize([-sv * 0.3, k * 0.3, -0.9]), wx, wy), 1.0 * s)
            wins.append((wx, wy))
        # a small plant on the left sill, a silhouette when the lamp is lit inside
        wx, wy = wins[0]
        plant = np.array([30, 40, 26], np.float32) * (0.4 + 0.6 * (1 - self.windows_lit)) + self.amb * 20
        L.poly([(wx - 7 * s, wy + 40 * s), (wx + 5 * s, wy + 40 * s), (wx + 4 * s, wy + 31 * s), (wx - 6 * s, wy + 31 * s)], plant)
        for a in (-0.9, -0.4, 0.1, 0.6):
            L.ellipse(wx - 1 * s + 9 * s * math.sin(a), wy + 25 * s - 6 * s * math.cos(a), 4 * s, 7 * s, plant)
        # clock
        self.clock(L, cx, CLOCK["y"] * H, CLOCK["R"] * s)
        # door
        dw, dh = 34 * s, 128 * s
        dyb = yb + 12 * s
        # the doorway: dressed stone, jamb blocks long and short and a ring of voussoirs with a keystone,
        # each stone its own tone, set in mortar
        sp = dyb - dh + dw
        rg = np.random.default_rng(53)
        up_n = normalize([0, 0.45, 0.9])
        arch_alb = np.array([190, 182, 164], np.float32)
        L.poly([(cx - dw - 12 * s, dyb), (cx + dw + 12 * s, dyb), (cx + dw + 12 * s, sp), (cx - dw - 12 * s, sp)],
               self.lit((120, 112, 98), front, cx, dyb - dh))
        L.ellipse(cx, sp, dw + 12 * s, dw + 12 * s, self.lit((120, 112, 98), front, cx, dyb - dh))
        bh = (dyb - sp) / 4
        for side in (-1, 1):
            for j in range(4):
                ya, yb2 = dyb - j * bh, dyb - (j + 1) * bh
                xa, xb = cx + side * dw, cx + side * (dw + (12 if j % 2 == 0 else 10) * s)
                a_ = arch_alb * rg.uniform(0.84, 1.08)
                L.poly([(xa, ya - 0.6 * s), (xb, ya - 0.6 * s), (xb, yb2 + 0.6 * s), (xa, yb2 + 0.6 * s)], self.lit(a_, front, cx, dyb - dh))
                L.line([(xa, yb2 + 1.1 * s), (xb, yb2 + 1.1 * s)], self.lit(a_, up_n, cx, dyb - dh), 0.9 * s)
        n_v = 9
        for i in range(n_v):
            g0, g1 = math.pi * i / n_v + 0.6 * s / dw, math.pi * (i + 1) / n_v - 0.6 * s / dw
            ro = dw + (15 if i == n_v // 2 else 12) * s
            ri = dw + 0.3 * s
            pts = [(cx + ri * math.cos(g), sp - ri * math.sin(g)) for g in np.linspace(g0, g1, 4)] + \
                  [(cx + ro * math.cos(g), sp - ro * math.sin(g)) for g in np.linspace(g1, g0, 4)]
            gm = (g0 + g1) / 2
            a_ = arch_alb * rg.uniform(0.84, 1.08)
            L.poly(pts, self.lit(a_, front, cx, dyb - dh))
            # its outer face turns a little toward the sky, the soffit inside the arch away from it
            L.line([(cx + (ro - 0.6 * s) * math.cos(g), sp - (ro - 0.6 * s) * math.sin(g)) for g in np.linspace(g0, g1, 4)],
                   self.lit(a_, normalize([0.4 * math.cos(gm), 0.6, 0.6 * math.sin(gm)]), cx, dyb - dh), 0.9 * s)
        wood = self.lit((96, 58, 36), front, cx, dyb - dh * 0.5)
        self.door_wood(L)
        # the ironwork: two strap hinges with their nails, and rows of nail heads; each piece has a top
        # face that takes the sky and an underside that does not
        iron = self.lit((34, 32, 32), front)
        iron_top = self.lit((44, 42, 40), normalize([0, 0.55, 0.85]))
        iron_low = self.lit((34, 32, 32), normalize([0, 0.6, -0.8]))
        nail = self.lit((92, 86, 78), normalize([0, 0.7, 0.7]))
        for yy in (dyb - 0.25 * dh, dyb - 0.7 * dh):
            L.line([(cx - dw, yy), (cx + dw * 0.7, yy)], iron, 3.2 * s)
            L.line([(cx - dw, yy - 1.2 * s), (cx + dw * 0.7, yy - 1.2 * s)], iron_top, 0.9 * s)
            L.line([(cx - dw, yy + 1.3 * s), (cx + dw * 0.7, yy + 1.3 * s)], iron_low, 0.8 * s)
            L.poly([(cx + dw * 0.7, yy - 3.5 * s), (cx + dw * 0.86, yy), (cx + dw * 0.7, yy + 3.5 * s)], iron)
            L.poly([(cx + dw * 0.7, yy - 3.5 * s), (cx + dw * 0.86, yy), (cx + dw * 0.7, yy - 1.5 * s)], iron_top)
            for k in range(6):
                L.ellipse(cx - dw + (k + 0.5) * 1.6 * dw / 6, yy, 1.2 * s, 1.2 * s, nail)
        for i in range(3):
            for j in range(5):
                L.ellipse(cx - dw * 0.6 + i * dw * 0.6, dyb - dh * (0.15 + 0.17 * j), 1.0 * s, 1.0 * s, nail)
        L.ellipse(cx + dw * 0.55, dyb - 0.47 * dh, 5 * s, 5 * s, iron)
        L.ellipse(cx + dw * 0.55, dyb - 0.47 * dh, 3 * s, 3 * s, wood)
        step = self.lit((176, 168, 150), [0, 0.5, 0.9], cx, dyb)
        L.poly([(cx - 50 * s, dyb + 9 * s), (cx + 50 * s, dyb + 9 * s), (cx + 46 * s, dyb - 1 * s), (cx - 46 * s, dyb - 1 * s)], step)
        mat = self.lit((104, 80, 52), [0, 0.3, 1], cx, dyb)
        L.poly([(cx - 27 * s, dyb + 7 * s), (cx + 27 * s, dyb + 7 * s), (cx + 25 * s, dyb + 1 * s), (cx - 25 * s, dyb + 1 * s)], mat)
        L.line([(cx - 25 * s, dyb + 4 * s), (cx + 25 * s, dyb + 4 * s)], mat * 0.75, 0.8 * s)
        if self.wx.snow_cover > 0.1:
            L.poly([(cx - 50 * s, dyb - 1 * s), (cx + 50 * s, dyb - 1 * s), (cx + 48 * s, dyb + 3 * s), (cx - 48 * s, dyb + 3 * s)],
                   self.lit((236, 240, 246), [0, 0.3, 1]), a=min(1.0, self.wx.snow_cover * 1.5))
        # a terracotta pot by the door with whatever is in season
        px, py = cx - 62 * s, dyb + 6 * s
        terracotta = self.lit((168, 86, 52), front, px, py)
        L.poly([(px - 9 * s, py - 16 * s), (px + 9 * s, py - 16 * s), (px + 7 * s, py), (px - 7 * s, py)], terracotta)
        L.poly([(px - 10 * s, py - 19 * s), (px + 10 * s, py - 19 * s), (px + 10 * s, py - 15 * s), (px - 10 * s, py - 15 * s)], terracotta * 1.1)
        se = self.season
        rp = np.random.default_rng(57)
        bloom = None
        if 60 <= se.doy < 125:
            leafc, bloom = (70, 110, 50), (238, 206, 52)      # daffodils
        elif 125 <= se.doy < 275:
            leafc, bloom = (58, 96, 44), (212, 46, 40)        # geraniums
        elif 275 <= se.doy < 320:
            leafc, bloom = (70, 84, 56), (176, 106, 172)      # heather
        else:
            leafc = (40, 70, 44)                              # a little box tree
        for k in range(14):
            a = rp.uniform(-1.2, 1.2)
            ln = rp.uniform(8, 18) * s
            L.line([(px + rp.normal(0, 3) * s, py - 18 * s), (px + math.sin(a) * ln, py - 18 * s - math.cos(a) * ln)],
                   self.lit(leafc, front, px, py), 2.0 * s)
        if bloom:
            for k in range(9):
                L.ellipse(px + rp.normal(0, 7) * s, py - rp.uniform(24, 36) * s, 2.6 * s, 2.2 * s, self.lit(bloom, front, px, py))
        else:
            L.ellipse(px, py - 30 * s, 10 * s, 13 * s, self.lit(leafc, front, px, py))
        # a brass plaque, and a boot scraper by the step
        pl = self.lit((180, 140, 70), front) + 25 * self.sun_str
        L.poly([(cx + dw + 20 * s, dyb - 70 * s), (cx + dw + 34 * s, dyb - 70 * s), (cx + dw + 34 * s, dyb - 60 * s), (cx + dw + 20 * s, dyb - 60 * s)], pl)
        L.line([(cx + 54 * s, dyb + 6 * s), (cx + 54 * s, dyb - 2 * s), (cx + 66 * s, dyb - 2 * s), (cx + 66 * s, dyb + 6 * s)], iron, 1.4 * s)
        # a cast-iron downpipe from the gutter under the cornice
        dpx = cx + 0.86 * r
        dp = self.lit((52, 58, 64), normalize([-0.86, 0.5, 0.1]))
        L.line([(dpx, yt + 10 * s), (dpx, yb + 6 * s)], dp, 4.2 * s)
        L.poly([(dpx - 6 * s, yt + 8 * s), (dpx + 6 * s, yt + 8 * s), (dpx + 3 * s, yt + 18 * s), (dpx - 3 * s, yt + 18 * s)], dp)
        for yy in np.arange(yt + 60 * s, yb, 70 * s):
            L.line([(dpx - 4 * s, yy), (dpx + 4 * s, yy)], dp * 0.7, 2.0 * s)
        L.line([(dpx, yb + 2 * s), (dpx + 8 * s, yb + 8 * s)], dp, 4.2 * s)
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

    def door_wood(self, L):
        """The planked door (door_maps), lit, drawn into the details layer. When the sun reaches the
        door's face, the jambs and the arch, a stone deep, shade the side and top toward it."""
        D = door_maps(self.W, self.H)
        s = self.s
        shade = None
        e, n, u = (float(c) for c in self.sunv)
        if n > 0.02 and self.sun_str > 0:
            dd = 8 * s
            ox = float(np.clip(dd * -e / n, -40 * s, 40 * s))
            oy = float(np.clip(dd * u / n, 0, 80 * s))
            Xs, Ys = D.X + ox, D.Y - oy
            inside = np.where(Ys < D.ys, D.dw - np.hypot(Xs - D.cx, Ys - D.ys), D.dw - np.abs(Xs - D.cx))
            shade = sm(0.5 * s, -0.5 * s, inside)
        Lt = self.light(D.nrm, shade=shade, ao=D.ao)
        if self.pools:
            Lt = Lt + self.local(D.X, D.Y)
        L.blit(D.origin[0], D.origin[1], D.alb * Lt, D.cov)

    def clock(self, L, x, y, R):
        s, h = self.s, self.h
        on = self.lights_on
        front = normalize([0, 1, 0.1])
        L.ellipse(x, y, R * 1.2, R * 1.2, self.lit((196, 188, 170), front, x, y))
        L.ellipse(x, y, R * 1.07, R * 1.07, self.lit((170, 128, 58), front))
        L.ellipse(x, y, R * 0.99, R * 0.99, self.lit((120, 90, 40), front))
        face = self.lit((234, 226, 204), front) * (1 - 0.6 * on) + np.array([255, 238, 200], np.float32) * 0.92 * on
        # twice a year the sun passes right behind the dial, and the glass glows
        az_c, alt_c = 180 + (x / self.W - 0.5) * AZ_SPAN, (VH - y / self.H) / VH * ALT_TOP
        off = math.hypot((self.sun_az - az_c) * math.cos(math.radians(alt_c)), self.sun_alt - alt_c)
        back = sm(1.6, 0.3, off) * self.sun_vis
        if back > 0:
            face = face * (1 - back) + np.array([255, 246, 220], np.float32) * back
            self.backlit = (x, y, R, back)
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
        hh, mins = h, self.m % 60
        if self.day.mysteries.clock_stopped and 213 <= self.m < 246:
            hh, mins = 3, 33
        hand((hh % 12) * 30 + mins * 0.5, R * 0.52, R * 0.055, R * 0.12)
        hand(mins * 6, R * 0.80, R * 0.035, R * 0.14)
        L.ellipse(x, y, R * 0.065, R * 0.065, self.lit((180, 140, 64), front) + 30 * on)
