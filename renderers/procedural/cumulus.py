"""Heaped low cloud: cumulus with flat bases and domed, lit tops, out of the forecast.

The low deck's cover (`wx.cloud_low`) is shared out between two drawings:

- **heaps**, separate clouds built from spheres (squashed for flat ones) cut flat at the deck's base,
  ray-cast at the sky's half resolution and lit by the scene's sun or moon (`render`);
- **a lid**, the old noise layer (`sky.cloud_layer`), which takes over as the deck closes, or when a
  front's steady rain is about (`regime`).

What kind of heap the forecast makes (`regime`): fair cumulus need the day's warmth; showers and
thunder within the next hours build them into towers with heavier, darker bases, a few into anvils,
and rain hangs from the heaviest; at night the heaps flatten into stratocumulus. Clouds live in cells
of a grid that drifts with the wind at the deck (the same drift as the noise layers), so a heap keeps
its shape from minute to minute while it crosses the sky, grows as the cover rises past its own
threshold, and swells and shrinks a little on its own clock.
"""
import math
from types import SimpleNamespace

import numpy as np

from core import *  # noqa: F401,F403

HK = 1.2            # km: the base of the low deck (sky.CLOUD_LAYERS "low"); lengths here are in deck heights
WF = 1.5            # wind at the deck relative to the surface, as the low noise layer
CELL = 1.7          # grid cell on the deck (deck heights): one heap at most per cell
DMAX = 16.0         # the farthest heap, about 3.6 degrees above the horizon
SHOWERY = (80, 81, 82, 85, 86)


# ----------------------------------------------------------------- regime ---
def _window(x, before, after):
    """Mean of x over the minutes [m - before, m + after] for every minute m of the day."""
    c = np.concatenate([[0.0], np.cumsum(np.asarray(x, np.float64))])
    i = np.arange(len(x))
    a, b = np.clip(i - before, 0, len(x)), np.clip(i + after + 1, 0, len(x))
    return ((c[b] - c[a]) / np.maximum(b - a, 1)).astype(np.float32)


def regime_arrays(day):
    """Per-minute signals from the forecast's weather codes, made once per day: showers and thunder
    looked for over the next hours as well (heaps tower up before the rain), and a front's steady rain
    or snow (which closes the deck into a lid)."""
    got = getattr(day, "_cumulus_regime", None)
    if got is None:
        code = np.asarray(day.wx.code)
        sh = np.isin(code, SHOWERY) | (code >= 95)
        fr = ((code >= 51) & (code <= 67)) | ((code >= 71) & (code <= 77))
        got = dict(shower=_window(sh, 60, 150), thunder=_window(code >= 95, 90, 180), front=_window(fr, 60, 60))
        day._cumulus_regime = got
    return got


def regime(fr):
    """What kind of low cloud this minute holds.

    lid      0 open .. 1 a closed grey deck
    share    the part of the low cover drawn as heaps (the rest is the noise layer: stratocumulus and
             the lid). Heaps need convection: the day's warmth (which outlasts the sun by an hour or
             two), or showers and thunder about
    tower    height of a heap over its width, about 0.5 for fair-weather cumulus, 1-2.5 for towers
             when showers or thunder are near
    dark     how heavy the bases are
    shower, thunder   0-1, the codes' signals around this minute
    """
    ra, i, wx, day = regime_arrays(fr.day), min(fr.m, 1439), fr.wx, fr.day
    shw, thn, frn = float(ra["shower"][i]), float(ra["thunder"][i]), float(ra["front"][i])
    lag = float(day.sun_alt[max(min(fr.m, 1440) - 90, 0)])
    heat = sm(2, 30, max(fr.sun_alt, lag)) * (0.55 + 0.45 * sm(0, 22, wx.temp_c))
    conv = min(1.0, max(heat, 1.3 * shw, 1.3 * thn))
    lid = max(sm(0.6, 0.95, wx.cloud_low), frn * sm(0.35, 0.85, wx.cloud_low))
    share = (1 - lid) ** 2 * (0.25 + 0.75 * conv)
    tower = max(0.75, 0.6 + 0.6 * heat + 1.5 * shw + 1.3 * thn) * (1 - 0.5 * lid)
    wet = max(wx.rain, wx.snow, 0.6 * wx.drizzle)
    dark = min(1.0, 0.15 + 0.5 * shw + 0.3 * thn + 0.25 * lid + 0.35 * wet)
    return SimpleNamespace(lid=lid, share=share, tower=tower, dark=dark, shower=shw, thunder=thn, front=frn, wet=wet)


# ------------------------------------------------------------- population ---
def core(r, T):
    """A dome's body: an ellipsoid centred on the deck (centre height, horizontal and vertical radii),
    which cuts away its lower half and leaves the flat base."""
    return 0.0, 0.85 * r, 0.72 * T


def _dome(rng, r, T, lod, lean):
    """Spheres (east, north, up, radius, squash) of one dome about its base centre, in deck heights:
    the body; a ring of bumps round its foot, cut flat by the deck with it, so the base is one plane
    with a lumpy edge; and rounded heads bulging out of it, larger toward the crown and more of them on
    one side. lod 0-2 sets how many puffs a far or near dome gets."""
    z0, rc, tz = core(r, T)
    out = [(0.0, 0.0, z0, rc, tz / rc)]
    ring, heads = ((2, 3), (4, 5), (5, 9))[lod]
    a0 = rng.uniform(0, 2 * math.pi)
    for j in range(ring):
        a = a0 + 2 * math.pi * (j + rng.uniform(-0.3, 0.3)) / ring
        R = min(r * rng.uniform(0.32, 0.46), 0.8 * T)
        d = rc * rng.uniform(0.72, 0.98)
        out.append((d * math.cos(a), d * math.sin(a), 0.0, R, 1.0))
    size = min(rc, tz)
    side, bias = rng.uniform(0, 2 * math.pi), rng.uniform(0.0, 0.7)
    for j in range(int(heads * min(1.5, max(1.0, (T / r) ** 0.4)))):
        ph = side + rng.uniform(-math.pi, math.pi) * (1 - bias * rng.uniform(0, 1))
        ct = 0.25 + 0.75 * rng.uniform(0.0, 1.0) ** 0.6       # cos of the angle from the top of the dome
        st = math.sqrt(1 - ct * ct)
        R = size * rng.uniform(0.3, 0.5) * (0.75 + 0.3 * ct)
        nx, ny, nz = st * math.cos(ph) / rc, st * math.sin(ph) / rc, ct / tz
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        x, y, z = rc * st * math.cos(ph), rc * st * math.sin(ph), tz * ct
        o = 0.35 * R / ln
        x, y, z = x - o * nx, y - o * ny, z - o * nz
        out.append((x + lean[0] * z, y + lean[1] * z, z, R, 1.0))
    return out


def population(fr, reg):
    """The heaps in view this minute, as arrays of spheres in east/north/up deck heights (the camera at
    the origin, the deck's base at up = 1), each with the dome it belongs to; or None when there is no
    low cloud to heap. A big heap is two domes, the second lower and to one side."""
    c = 0.75 * fr.wx.cloud_low * reg.share
    if c < 0.01:
        return None
    day = fr.day
    m = min(fr.m, 1440)
    ox, oz = day.drift_e[m] * WF / HK, -day.drift_n[m] * WF / HK     # the air's offset on the deck (east, south)
    I = np.arange(math.floor((-DMAX - 3 - ox) / CELL), math.floor((DMAX + 3 - ox) / CELL) + 1)
    J = np.arange(math.floor((-0.4 * DMAX - 3 - oz) / CELL), math.floor((DMAX + 3 - oz) / CELL) + 1)
    I, J = [a.ravel() for a in np.meshgrid(I, J)]
    salt = day.date.toordinal() % 7919
    u = [hash2(I * 1.0 + 0.371 * k + 0.0137 * salt, J * 1.13 + 3.71 * k + 0.0071 * salt) for k in range(8)]
    q = min(1.0, 0.22 + 1.5 * c)
    grow = sm(0.0, 0.1, q - u[0])
    X = (I + 0.15 + 0.7 * u[1]) * CELL + ox                              # east
    Z = (J + 0.15 + 0.7 * u[2]) * CELL + oz                              # south
    D = np.hypot(X, Z)
    az = np.degrees(np.arctan2(X, -Z)) % 360
    keep = (grow > 0) & (D < DMAX) & (np.abs(az - 180) < AZ_SPAN / 2 + np.degrees(np.arctan2(3.0, D)))
    life = 0.82 + 0.18 * np.sin(2 * np.pi * (fr.m / (45 + 55 * u[5]) + u[4]))
    r = CELL * (0.45 + 1.25 * u[3] ** 2) * np.sqrt(min(c, 0.8) / (math.pi * q) * grow * life)
    th = math.radians(fr.wx.wind_dir_deg)
    down = (-math.sin(th), -math.cos(th))                                 # where the wind blows to (east, north)
    lean = (0.12 * down[0], 0.12 * down[1])
    ppr = fr.W / 2 / math.radians(AZ_SPAN)                                  # sky-grid pixels per radian
    sph, domes = [], []
    for idx in np.nonzero(keep)[0]:
        rr = float(r[idx])
        if rr < 0.05:
            continue
        T = min(rr * (0.55 + 0.45 * float(u[6][idx])) * reg.tower, 7.0)
        dist = float(D[idx])
        px_ = rr / max(dist, 0.3) * ppr                                     # the heap's radius on the grid
        lod = 2 if px_ > 45 else 1 if px_ > 14 else 0
        rng = np.random.default_rng([salt, int(I[idx]) & 0xFFFFFFF, int(J[idx]) & 0xFFFFFFF, 3])
        x, y = float(X[idx]), -float(Z[idx])
        parts = [(x, y, rr, T, lod)]
        if rr > 0.5 and u[7][idx] < 0.6:
            b = rng.uniform(0, 2 * math.pi)
            r2 = rr * rng.uniform(0.5, 0.75)
            parts.append((x + 0.75 * rr * math.cos(b), y + 0.75 * rr * math.sin(b), r2,
                          T * rng.uniform(0.55, 0.85) * math.sqrt(r2 / rr), max(lod - 1, 0)))
        for (px, py, pr, pT, pl) in parts:
            for j, (de, dn, du, R, sq) in enumerate(_dome(rng, pr, pT, pl, lean)):
                if j == 0 or R / dist * ppr > 2.5:                          # puffs too small to see are left out
                    sph.append((px + de, py + dn, 1.0 + du, R, sq, len(domes)))
            z0, rc, tz = core(pr, pT)
            domes.append((px, py, pr, pT, float(u[7][idx]), 1.0 + z0, rc, tz))
    if not sph:
        return None
    s = np.array(sph, np.float32)
    cl = np.array(domes, np.float32)
    return SimpleNamespace(E=s[:, 0], N=s[:, 1], U=s[:, 2], R=s[:, 3], q=s[:, 4], cid=s[:, 5].astype(np.int32),
                           cE=cl[:, 0], cN=cl[:, 1], r=cl[:, 2], T=cl[:, 3], u=cl[:, 4], z0=cl[:, 5], rc=cl[:, 6],
                           tz=cl[:, 7])


# --------------------------------------------------------------- ray cast ---
def _hit(dE, dN, dU, E, N, U, R, q, rpp):
    """Rays (unit east/north/up, from the camera) against one cut ellipsoid (or broadcast arrays of
    them). Returns coverage (anti-aliased over rpp radians), the distance to the visible surface,
    and whether that surface is the flat base."""
    du = dU / q
    cu = U / q
    a = dE * dE + dN * dN + du * du
    b = dE * E + dN * N + du * cu
    cc = E * E + N * N + cu * cu
    tc = b / a
    perp = np.sqrt(np.maximum(cc - b * tc, 0))
    ok = tc > 0
    tcs = np.where(ok, tc, 1.0)
    edge = np.clip(0.5 - (perp - R) / (tcs * rpp), 0, 1)
    sq = np.sqrt(np.maximum(b * b - a * (cc - R * R), 0))
    t0, t1 = (b - sq) / a, (b + sq) / a
    tp = 1.0 / np.maximum(dU, 1e-3)
    cut = np.clip(0.5 + (t1 * dU - 1.0) / (np.maximum(t1, 1e-3) * rpp), 0, 1)
    cov = np.where(ok, edge * cut, 0)
    base = t0 < tp
    return cov, np.where(base, tp, t0), base


def _slope(g):
    """How fast g changes per grid pixel (the length of its gradient)."""
    gy, gx = np.gradient(g)
    return np.sqrt(gx * gx + gy * gy)


def coverage(pop, dirs, rpp=0.002):
    """Heap coverage (0-1) toward a few directions (n, 3 east/north/up), e.g. across the sun's disk."""
    d = np.asarray(dirs, np.float32)[:, :, None]
    cov = _hit(d[:, 0], d[:, 1], d[:, 2], pop.E[None], pop.N[None], pop.U[None], pop.R[None], pop.q[None], rpp)[0]
    return cov.max(1)


def render(fr, pop, grid, k):
    """Ray-cast the heaps on the sky grid (alt, az, east, north, up at every k-th pixel), puff by puff
    from the nearest, each laid under what is already there with its own anti-aliased edge, as a
    painter would lay overlapping puffs. Returns the coverage and, averaged under it, what the
    shading needs: a normal that blends the puff's sphere into the whole heap's dome, the height up
    the heap, the light at each puff's rim, and how far out under the base a point is."""
    alt, az, e, n, u = grid
    h, w = alt.shape
    W, H = fr.W, fr.H
    rpp = 0.5 * (math.radians(AZ_SPAN) / (W / k) + math.radians(ALT_TOP) / (VH * H / k))
    A = np.zeros((h, w), np.float32)
    S = np.zeros((9, h, w), np.float32)          # normal (3), height up the heap, puff rim, out under the base, distance, east, north
    # each sphere's box on the grid
    dist = np.sqrt(pop.E ** 2 + pop.N ** 2 + pop.U ** 2)
    rho = np.degrees(np.arcsin(np.clip(pop.R / dist, 0, 0.999))) + 0.6
    ac = np.degrees(np.arcsin(pop.U / dist))
    zc = np.degrees(np.arctan2(pop.E, pop.N)) % 360
    top = np.minimum(ac + rho, 89.0)
    half = np.where(ac + rho >= 89.0, 180.0,
                    np.degrees(np.arcsin(np.clip(np.sin(np.radians(rho)) / np.cos(np.radians(top)), 0, 1))) + 0.6)
    x0 = ((0.5 + (zc - 180 - half) / AZ_SPAN) * W / k).astype(np.int64)
    x1 = ((0.5 + (zc - 180 + half) / AZ_SPAN) * W / k).astype(np.int64) + 2
    y0 = ((VH - (ac + rho) / ALT_TOP * VH) * H / k).astype(np.int64)
    y1 = ((VH - (ac - rho) / ALT_TOP * VH) * H / k).astype(np.int64) + 2
    x0, x1, y0, y1 = np.clip(x0, 0, w), np.clip(x1, 0, w), np.clip(y0, 0, h), np.clip(y1, 0, h)
    Zb = np.full((h, w), np.inf, np.float32)
    near = dist - pop.R
    for i in np.argsort(near, kind="stable"):
        if x1[i] <= x0[i] or y1[i] <= y0[i]:
            continue
        sl = (slice(y0[i], y1[i]), slice(x0[i], x1[i]))
        a_, zb = A[sl], Zb[sl]
        if a_.min() > 0.995 and near[i] > zb.max():
            continue
        dE, dN, dU = e[sl], n[sl], u[sl]
        E, N, U, R, q = (float(v[i]) for v in (pop.E, pop.N, pop.U, pop.R, pop.q))
        c = pop.cid[i]
        cE, cN, T = float(pop.cE[c]), float(pop.cN[c]), float(pop.T[c])
        z0, rc, tz = float(pop.z0[c]), float(pop.rc[c]), float(pop.tz[c])
        # the ray against the (squashed) sphere; rays are unit vectors, so a = 1 when it is round
        du = dU if q == 1.0 else dU * (1 / q)
        cu = U / q
        b = dE * E + dN * N + du * cu
        cc = E * E + N * N + cu * cu
        if q == 1.0:
            a, tc = 1.0, b
        else:
            a = dE * dE + dN * dN + du * du
            tc = b / a
        perp = np.sqrt(np.maximum(cc - b * tc, 0))
        if q == 1.0 or min(perp.shape) < 2:
            cov = np.clip(0.5 - (perp - R) / (np.maximum(tc, 1e-3) * rpp), 0, 1)
        else:                            # a squashed body: its own slope across the grid
            cov = np.clip(0.5 + (R - perp) / (_slope(perp) + 1e-6), 0, 1)
        if not cov.any():
            continue
        sq = np.sqrt(np.maximum(b * b - a * (cc - R * R), 0))
        t = (b - sq) / a if q != 1.0 else b - sq
        cut = U - R * q < 1.0 and min(cov.shape) > 1
        if cut:                          # the deck cuts this puff: a flat base where the ray meets it first
            t1 = (b + sq) / a if q != 1.0 else b + sq
            # the edges are anti-aliased by their own slope across the grid, as a shader's fwidth would
            g = t1 * dU - 1.0                                          # where the ray leaves the puff, above the deck
            cov *= np.clip(0.5 + g / (_slope(g) + 1e-6), 0, 1)
            tp = 1.0 / np.maximum(dU, 1e-3)
            g = tp - t
            base = np.clip(0.5 + g / (_slope(g) + 1e-6), 0, 1)        # 1 on the flat base, soft at its rim
            t = np.maximum(t, tp)
        px, py, pz = t * dE, t * dN, t * dU
        # the puff's sphere and the heap's dome, blended (the dome leads, the puffs give it lumps)
        if q == 1.0:
            ir = 0.2 / R
            gx, gy, gz = (px - E) * ir, (py - N) * ir, (pz - U) * ir
            rim = 1 - np.minimum(np.abs(t - b) * (1 / R), 1)
        else:
            gx, gy, gz = px - E, py - N, (pz - U) / (q * q)
            ln = 0.2 / (np.sqrt(gx * gx + gy * gy + gz * gz) + 1e-6)
            gx, gy, gz = gx * ln, gy * ln, gz * ln
            rim = 1 - np.minimum(5 * np.abs(gx * dE + gy * dN + gz * dU), 1)
        fx, fy, fzz = (px - cE) * (1 / (rc * rc)), (py - cN) * (1 / (rc * rc)), (pz - z0) * (1 / (tz * tz))
        ln = 0.8 / (np.sqrt(fx * fx + fy * fy + fzz * fzz) + 1e-6)
        bx, by, bz = gx + fx * ln, gy + fy * ln, gz + fzz * ln
        hr = np.clip((pz - 1.0) * (1 / max(T, 1e-3)), 0, 1)
        if cut:
            side = 1 - base
            bx, by, bz = bx * side, by * side, bz * side - base
            br = side + base * np.minimum(np.hypot(px - cE, py - cN) * (1 / rc), 1)
            rim = rim * side
        else:
            br = 1.0
        # in front of what is there: laid over it; behind: shows only where that is thin. Where two
        # surfaces cross, the depth test is softened over about a pixel, so the crease is smooth; a tie
        # (two puffs' bases in the one plane) goes to the puff already there
        fw = np.clip((zb - t) / (1.5 * rpp * t), 0, 1)
        wn = cov * (fw + (1 - fw) * (1 - a_))
        keep = 1 - cov * fw
        s_ = S[:, sl[0], sl[1]]
        for j, v in enumerate((bx, by, bz, hr, rim, br, t, px, py)):
            s_[j] *= keep
            s_[j] += wn * v
        a_ *= keep
        a_ += wn
        solid = (fw > 0.5) & (cov > 0.5)
        zb[solid] = t[solid]
    if A.max() <= 0.001:
        return None
    inv = 1 / np.maximum(A, 1e-6)
    S *= inv
    return SimpleNamespace(A=A, nE=S[0], nN=S[1], nU=S[2], hrel=S[3], rim=S[4], brim=S[5], dist=S[6], pE=S[7], pN=S[8])


# ---------------------------------------------------------------- shading ---
def _tone(ndl):
    """Light on a face turned ndl toward the light: wrapped (cloud is soft) and pulled toward two
    tones, lit and shaded, as a painter would."""
    w = np.clip((ndl + 0.4) / 1.4, 0, 1)
    return 0.4 * w + 0.6 * sm(0.33, 0.66, w)


def shade(fr, pop, hit, reg, grid):
    """Colour and coverage of the heaps on the sky grid, inside the box (a pair of slices of the grid)
    that holds them, lit by the scene's own sun and moon.

    Sunlit faces take the sunlight's colour as the deck sees it (it sees the sun set about a degree
    after we do); the rest is lit by the sky. While the sun is below the deck's level but not yet set
    on it, it lights the bases from below, orange toward it and pink away from it; then the earth's
    shadow climbs past the deck and the heaps go violet-grey against the glowing sky. Toward the sun,
    the thin edges glow."""
    rows, cols = np.nonzero(hit.A.max(1) > 0.002)[0], np.nonzero(hit.A.max(0) > 0.002)[0]
    box = (slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1))
    hit = SimpleNamespace(**{k: v[box] for k, v in vars(hit).items()})
    alt, az, e, n, u = (g[box] for g in grid)
    sa = fr.sun_alt
    sac = sa + 1.1                                      # the sun's altitude as the deck sees it
    ds = sm(-0.6, 0.6, sac) * (0.35 + 0.65 * getattr(fr, "sun_through_layers", 1.0))   # less behind the higher layers
    nE, nN, nU = hit.nE, hit.nN, hit.nU
    dm = 0.75 * fr.moon_sky * sm(-2, 8, fr.moon_alt) * (1 - ds)
    lc = keys(CLOUD_SUN, sac) * ds + (keys(CLOUD_LIT, sa) + np.array([46, 52, 70], np.float32) * fr.moon_sky) * (1 - ds)
    sc = keys(CLOUD_SHADE, sa)
    sv, mv = fr.sunv, fr.moonv
    L = ds * _tone(nE * sv[0] + nN * sv[1] + nU * sv[2])
    if dm > 0:
        L = L + dm * _tone(nE * mv[0] + nN * mv[1] + nU * mv[2])
    hrel, down = hit.hrel, np.clip(-nU, 0, 1)
    L = L * (1 - 0.22 * (1 - hrel) ** 1.6 * sm(4, 25, sa))           # a high sun: the puffs above shade the lower body
    L = L + 0.08 * min(1.0, ds + dm) * hit.rim ** 2 * (1 - down)       # each puff's rim catches a little light
    dark = reg.dark
    body = (0.85 - 0.1 * (1 - hrel) ** 3) * (1 - 0.4 * dark) * (1 - 0.3 * dark * (1 - hrel))
    under = 0.72 * (1 - 0.4 * dark) * (0.86 + 0.24 * hit.brim ** 2)      # the flat base: darkest under the middle
    if down.max() > 0.5:                 # and mottled, as the air under it is lumpy
        mot = sample(fnoise(256, 256, 2.0, 1.0, 83), hit.pN * 9.0, hit.pE * 9.0)
        under = under * (1 + 0.07 * np.clip(mot, -2, 2))
    sce = sc * (body * (1 - down) + under * down)[..., None]
    col = sce + (lc - sce) * np.clip(L, 0, 1.2)[..., None]
    # a low sun lights the undersides: orange toward the sun, pink away from it
    ug = ds * (sm(2.5, 0.0, sa) + 0.2 * sm(9, 2, sa))
    if ug > 0:
        side = sm(-0.5, 0.9, np.cos(np.radians(az - fr.sun_az)))
        w = (down ** 0.6 * 0.85 + 0.15 * (1 - hrel)) * (0.4 + 0.6 * side) * (1 - 0.4 * dark)
        pink = np.array([242, 120, 150], np.float32)
        tint = pink + (lc - pink) * side[..., None]
        col += (ug * w * 0.85)[..., None] * tint
    # toward the sun, light comes through the thin edges: a bright lining, and a glow in the body
    if ds > 0 and fr.sun_alt > -2:
        cg = 1 - (e * sv[0] + n * sv[1] + u * sv[2])
        ph = np.exp(-cg / 0.02) + 0.35 * np.exp(-cg / 0.12)
        k = ds * (1 - 0.5 * dark) * (1 - 0.5 * reg.lid)
        col += (ph * (1.6 * hit.rim ** 2 + 0.2) * k)[..., None] * lc
    col *= 1 - 0.35 * reg.wet
    hm = (0.8 * (1 - np.exp(-hit.dist * (HK / 16.0))) + 0.2 * np.exp(-alt / 4))[..., None]   # haze with distance
    col = col * (1 - hm) + fr.hor_col * hm
    a = hit.A * sm(1.0, 4.0, alt)
    return col, a, box


def shafts(fr, pop, reg, grid, k):
    """Rain hanging from the heaviest heaps when showers are about: a grey curtain from the base down
    to the horizon, leaning downwind, streaked. Returns colour and coverage on the sky grid, or None."""
    rain = reg.shower * (1 - 0.5 * reg.lid)
    if rain < 0.25:
        return None
    alt, az, e, n, u = grid
    h, w = alt.shape
    W, H = fr.W, fr.H
    pick = np.nonzero((pop.u < 1.4 * rain) & (pop.T > 0.9 * pop.r) & (pop.r > 0.35))[0]
    if len(pick) == 0:
        return None
    th = math.radians(fr.wx.wind_dir_deg)
    down = (-math.sin(th), -math.cos(th))
    A = np.zeros((h, w), np.float32)
    streak = fnoise(4, 2048, 1.1, 1, 57)[1]

    def screen(E, N, U):
        D = math.hypot(E, N)
        x = (0.5 + ((math.degrees(math.atan2(E, N)) % 360) - 180) / AZ_SPAN) * W / k
        y = (VH - math.degrees(math.atan2(U, D)) / ALT_TOP * VH) * H / k
        return x, y, D

    for i in pick:
        cE, cN, rc = float(pop.cE[i]), float(pop.cN[i]), float(pop.rc[i])
        xt, yt, D = screen(cE, cN, 1.0)
        xb, yb, _ = screen(cE + 0.35 * down[0], cN + 0.35 * down[1], 0.0)
        hw = 0.6 * rc / D * (W / k) / math.radians(AZ_SPAN)
        if hw < 4 or D > DMAX:
            continue
        y0, y1 = int(max(yt, 0)), int(min(yb + 1, h))
        x0, x1 = int(max(min(xt, xb) - hw - 2, 0)), int(min(max(xt, xb) + hw + 2, w))
        if y1 <= y0 or x1 <= x0:
            continue
        Y = np.arange(y0, y1, dtype=np.float32)[:, None]
        X = np.arange(x0, x1, dtype=np.float32)[None, :]
        f = (Y - yt) / max(yb - yt, 1)
        xc = xt + (xb - xt) * f
        d = np.abs(X - xc) / hw
        st = 0.7 + 0.3 * np.interp((X - xc) / hw * 40 + i * 97.0, np.arange(2048), streak, period=2048)
        a = np.clip(1 - d * d, 0, 1) ** 1.5 * st * sm(0.0, 0.12, f) * (1 - 0.35 * f)
        A[y0:y1, x0:x1] = np.maximum(A[y0:y1, x0:x1], a * min(1.0, 0.5 + rain) * 0.5)
    if A.max() < 0.01:
        return None
    sa = fr.sun_alt
    col = keys(CLOUD_SHADE, sa) * 0.78 * (1 - 0.25 * reg.dark)
    hm = (0.5 * np.exp(-alt / 4))[..., None]
    col = col * (1 - hm) + fr.hor_col * hm
    return col, A
