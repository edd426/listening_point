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
import functools
import math
from types import SimpleNamespace

import numpy as np

from core import *  # noqa: F401,F403

HK = 1.2            # km: the base of the low deck (sky.CLOUD_LAYERS "low"); lengths here are in deck heights
WF = 1.5            # wind at the deck relative to the surface, as the low noise layer
CELL = 1.7          # grid cell on the deck (deck heights): one heap at most per cell
DMAX = 11.0         # the farthest heap, about 5 degrees above the horizon; beyond, the horizon band
TILT = 0.75         # how much of the angle we look up at a heap it is turned away from us (see population)
COVER_K = 1.15      # heap size against the cover, set so the heaps you see take about their share of the sky
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
    tower = min(1.45, max(0.75, 0.6 + 0.6 * heat + 0.8 * shw + 0.6 * thn)) * (1 - 0.5 * lid)
    wet = max(wx.rain, wx.snow, 0.6 * wx.drizzle)
    dark = min(1.0, 0.15 + 0.5 * shw + 0.3 * thn + 0.25 * lid + 0.35 * wet)
    return SimpleNamespace(lid=lid, share=share, tower=tower, dark=dark, shower=shw, thunder=thn, front=frn, wet=wet)


# ------------------------------------------------------------- population ---
def core(r, T):
    """A dome's body: an ellipsoid centred on the deck (centre height, horizontal and vertical radii),
    which cuts away its lower half and leaves the flat base."""
    return 0.0, 0.85 * r * (1 - 0.2 * sm(1.2, 2.2, T / r)), 0.72 * T     # a tower is narrower


def _dome(rng, r, T, px, lean, sunh):
    """Spheres (east, north, up, radius, squash, kind) of one dome about its base centre, in deck
    heights. kind 0 is the body, 1 a head or a bump at the foot, 2 a knob.

    The body; a ring of bumps round its foot, cut flat by the deck with it, so the base is one plane
    with a lumpy edge; rounded heads bulging out of it, larger toward the crown and more of them on
    one side; and on the heads, knobs and knobs on knobs, mostly on the upper, sunward side, so the
    lit edge is a crisp cauliflower.

    The full set is always drawn from the generator in the same order, and a dome that is small in
    the frame (px, its radius in grid pixels) keeps only the first few of each kind, so as a heap
    drifts nearer it gains puffs one at a time and never changes shape."""
    z0, rc, tz = core(r, T)
    out = [(0.0, 0.0, z0, rc, tz / rc, 0)]
    f = float(np.clip((px - 10.0) / 35.0, 0, 1))
    n_ring = int(round(2 + 3 * f))
    n_heads = int(round((3 + 6 * f) * min(1.55, max(1.0, (T / r) ** 0.6))))
    n_k1 = int(round(12 * sm(16, 60, px)))
    n_k2 = int(round(12 * sm(45, 140, px)))
    a0 = rng.uniform(0, 2 * math.pi)
    for j in range(5):
        a = a0 + 2 * math.pi * (j + rng.uniform(-0.3, 0.3)) / 5
        R = min(r * rng.uniform(0.28, 0.4), 0.8 * T)
        d = rc * rng.uniform(0.45, 0.65)             # tucked in: the base is no wider than the heap
        if j < n_ring:
            out.append((d * math.cos(a), d * math.sin(a), 0.0, R, 1.0, 1))
    size = min(rc, tz)
    side, bias = rng.uniform(0, 2 * math.pi), rng.uniform(0.0, 0.7)
    heads = []
    for j in range(14):
        ph = side + rng.uniform(-math.pi, math.pi) * (1 - bias * rng.uniform(0, 1))
        ct = 0.15 + 0.85 * rng.uniform(0.0, 1.0) ** 0.6       # cos of the angle from the top of the dome
        st = math.sqrt(1 - ct * ct)
        R = min(size, 0.9 * rc) * rng.uniform(0.32, 0.55) * (0.75 + 0.3 * ct)
        nx, ny, nz = st * math.cos(ph) / rc, st * math.sin(ph) / rc, ct / tz
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        x, y, z = rc * st * math.cos(ph), rc * st * math.sin(ph), tz * ct
        o = 0.35 * R / ln
        x, y, z = x - o * nx + lean[0] * z, y - o * ny + lean[1] * z, z - o * nz
        heads.append((x, y, z, R))
        if j < n_heads:
            out.append((x, y, z, R, 1.0, 1))

    def knob(parent, scale):
        """A knob on a parent sphere, on its upper and sunward side."""
        vx, vy, vz = rng.normal(0, 1, 3)
        vx, vy, vz = vx + 0.9 * sunh[0], vy + 0.9 * sunh[1], abs(vz) + 1.1
        ln = math.sqrt(vx * vx + vy * vy + vz * vz)
        R = parent[3] * rng.uniform(scale * 0.8, scale * 1.2)
        o = parent[3] * 0.86
        return (parent[0] + o * vx / ln, parent[1] + o * vy / ln, parent[2] + o * vz / ln, R)

    k1 = []
    for j in range(12):                  # knobs on the first three heads, which every dome keeps
        kb = knob(heads[int(rng.integers(3))], 0.38)
        k1.append(kb)
        if j < n_k1:
            out.append(kb + (1.0, 2))
    for j in range(12):                  # and smaller knobs on the first six knobs
        p = int(rng.integers(6))
        kb = knob(k1[p], 0.42)
        if j < n_k2 and p < n_k1:
            out.append(kb + (1.0, 2))
    return out


def population(fr, reg):
    """The heaps in view this minute, as arrays of spheres in east/north/up deck heights (the camera at
    the origin, the deck's base at up = 1), each with the dome it belongs to; or None when there is no
    low cloud to heap.

    Heaps live in cells of a grid that drifts with the air. Where a slow field of clusters is high
    they are commoner and bigger; in a moderate wind they line up in streets along it. A big heap is
    a row of two to four domes, the first the tallest. Overhead (nearer than about two deck heights)
    they shrink away, so the top of the frame never holds a giant flat disc; far off they grow
    broader and flatter and fade into the band of cloud along the horizon (horizon_band)."""
    c = fr.wx.cloud_low * reg.share
    if c < 0.01:
        return None
    day = fr.day
    m = min(fr.m, 1440)
    ox, oz = day.drift_e[m] * WF / HK, -day.drift_n[m] * WF / HK     # the air's offset on the deck (east, south)
    I = np.arange(math.floor((-DMAX - 3 - ox) / CELL), math.floor((DMAX + 3 - ox) / CELL) + 1)
    J = np.arange(math.floor((-0.4 * DMAX - 3 - oz) / CELL), math.floor((DMAX + 3 - oz) / CELL) + 1)
    I, J = [a.ravel() for a in np.meshgrid(I, J)]
    salt = day.date.toordinal() % 7919
    u = [hash2(I * 1.0 + 0.371 * k + 0.0137 * salt, J * 1.13 + 3.71 * k + 0.0071 * salt) for k in range(9)]
    Xa = (I + 0.15 + 0.7 * u[1]) * CELL                                  # where the heap sits in the air (east, south)
    Za = (J + 0.15 + 0.7 * u[2]) * CELL
    X, Z = Xa + ox, Za + oz                                              # and where that is now
    D = np.hypot(X, Z)
    az = np.degrees(np.arctan2(X, -Z)) % 360
    # clusters, and streets along the wind
    clus = sm(-0.7, 0.9, sample(fnoise(256, 256, 2.4, 1.0, 91 + salt % 7), Za * 8.0, Xa * 8.0))
    th = math.radians(fr.wx.wind_dir_deg)
    down = (-math.sin(th), -math.cos(th))                                 # where the wind blows to (east, north)
    across = Xa * down[1] + Za * down[0]                                  # distance across the wind (east, south axes)
    street = 0.75 * sm(3, 7, fr.wx.wind_ms) * np.cos(2 * np.pi * across / 3.2 + salt)
    weight = (0.3 + 1.0 * clus) * (1 + street)
    q = min(1.0, 0.35 + 1.4 * c)
    grow = sm(0.0, 0.12, q * weight - u[0]) * sm(2.6, 4.0, D)
    keep = (grow > 0) & (D < DMAX) & (np.abs(az - 180) < AZ_SPAN / 2 + np.degrees(np.arctan2(3.0, D)))
    life = 0.82 + 0.18 * np.sin(2 * np.pi * (fr.m / (45 + 55 * u[5]) + u[4]))
    far = sm(5.0, 10.0, D)
    r = CELL * COVER_K * (0.3 + 1.5 * u[3] ** 3) * (0.55 + 0.9 * clus) * np.sqrt(min(c, 0.85) / (math.pi * q) * grow * life)
    r = np.minimum(r * (1 + 0.3 * far), 0.28 * D)
    lean = (0.12 * down[0], 0.12 * down[1])
    s_az = math.radians(fr.sun_az)
    sunh = (math.sin(s_az) * 0.8, math.cos(s_az) * 0.8)                   # toward the sun, on the deck (east, north)
    ppr = fr.W / 2 / math.radians(AZ_SPAN)                                  # sky-grid pixels per radian
    sph, domes = [], []
    for idx in np.nonzero(keep)[0]:
        rr = float(r[idx])
        if rr < 0.01:
            continue
        dist = float(D[idx])
        T = min(rr * (0.8 + 0.6 * float(u[6][idx])) * reg.tower * (1 - 0.4 * float(far[idx])), 7.0)
        rng = np.random.default_rng([salt, int(I[idx]) & 0xFFFFFFF, int(J[idx]) & 0xFFFFFFF, 4])
        x, y = float(X[idx]), -float(Z[idx])
        # a row of domes along an axis: the wind's in a street, any other way otherwise
        ax = float(rng.uniform(0, 2 * math.pi))
        if abs(float(street[idx])) > 0.2:
            ax = math.atan2(down[1], down[0]) + float(rng.uniform(-0.3, 0.3))
        nd = float(u[8][idx]) * 3.0 * sm(0.25, 0.7, rr)                       # extra domes, each growing in
        sizes = [1.0] + [float(v) for v in rng.uniform(0.45, 0.8, 3)]
        heights = [1.0] + [float(v) for v in rng.uniform(0.5, 0.9, 3)]
        seeds = rng.integers(1 << 30, size=4)
        parts, ends = [], [0.75 * rr, 0.75 * rr]                          # how far the row reaches each way
        for kd in range(4):
            g = 1.0 if kd == 0 else min(1.0, nd - (kd - 1))
            if g < 0.05:
                break
            pr = rr * sizes[kd] * g
            if kd == 0:
                off = 0.0
            else:
                way = kd % 2                                                # alternately ahead and behind
                off = ends[way] + 0.5 * pr
                ends[way] = off + 0.75 * pr
                off = off if way else -off
            parts.append((x + off * math.cos(ax), y + off * math.sin(ax), pr, T * heights[kd] * math.sqrt(sizes[kd]),
                          int(seeds[kd])))
        for (px, py, pr, pT, seed) in parts:
            prng = np.random.default_rng([salt, seed])
            # seen from below, a near heap would show mostly its flat underside; as a painter shows the
            # heap more from the side, it is turned away from us about its base by most of the angle
            # we look up at it (so its base is seen nearly edge-on), and its base plane turns with it
            dh = math.hypot(px, py)
            hx, hy = px / max(dh, 1e-6), py / max(dh, 1e-6)                 # away from us, on the deck
            tau = -TILT * math.atan2(1.0, dh)                                # top toward us: the base turns away
            ct, st = math.cos(tau), math.sin(tau)
            for j, (de, dn, du, R, sq, kind) in enumerate(_dome(prng, pr, pT, pr / max(dist, 0.3) * ppr, lean, sunh)):
                if j == 0 or R / dist * ppr > 2.0:                          # puffs too small to see are left out
                    along = de * hx + dn * hy                               # the part of the offset away from us
                    de2, dn2 = de - along * hx, dn - along * hy
                    a2, u2 = along * ct + du * st, du * ct - along * st     # turned in the vertical plane through us
                    sph.append((px + de2 + a2 * hx, py + dn2 + a2 * hy, 1.0 + u2, R, sq, len(domes), kind))
            z0, rc, tz = core(pr, pT)
            nb = (st * hx, st * hy, ct)                                     # the base plane's normal, turned with it
            domes.append((px, py, pr, pT, float(u[7][idx]), 1.0 + z0, rc, tz, nb[0], nb[1], nb[2],
                          nb[0] * px + nb[1] * py + nb[2] * 1.0))
    if not sph:
        return None
    s = np.array(sph, np.float32)
    cl = np.array(domes, np.float32)
    return SimpleNamespace(E=s[:, 0], N=s[:, 1], U=s[:, 2], R=s[:, 3], q=s[:, 4], cid=s[:, 5].astype(np.int32),
                           kind=s[:, 6].astype(np.int32),
                           cE=cl[:, 0], cN=cl[:, 1], r=cl[:, 2], T=cl[:, 3], u=cl[:, 4], z0=cl[:, 5], rc=cl[:, 6],
                           tz=cl[:, 7], nbE=cl[:, 8], nbN=cl[:, 9], nbU=cl[:, 10], nbc=cl[:, 11])


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
    S = np.zeros((11, h, w), np.float32)         # normal (3), height up the heap, puff rim, out under the base, the dome's
    #                                              distance, east, north, crease, the dome's radius (premultiplied)
    SD = np.full((h, w), -9.0, np.float32)       # grid pixels inside the outline of the whole field (for its edge)
    Ec = np.zeros((h, w), np.float32)            # how near a puff's edge, just outside it, and that puff's depth:
    Ez = np.full((h, w), np.inf, np.float32)     # what lies behind there is in the crease it makes
    # each sphere's box on the grid
    dist = np.sqrt(pop.E ** 2 + pop.N ** 2 + pop.U ** 2)
    rho = np.degrees(np.arcsin(np.clip(pop.R * np.maximum(pop.q, 1.0) / dist, 0, 0.999))) + 0.6   # a tall body reaches q R up
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
        wp = (0.12, 0.16, 0.26)[pop.kind[i]]     # how much the puff's own roundness shows: knobs most
        c = pop.cid[i]
        cE, cN, T = float(pop.cE[c]), float(pop.cN[c]), float(pop.T[c])
        z0, rc, tz = float(pop.z0[c]), float(pop.rc[c]), float(pop.tz[c])
        cd = math.sqrt(cE * cE + cN * cN + z0 * z0)       # the dome's distance: its texture rides with it
        rd = float(pop.r[c])
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
            sd = (R - perp) / (np.maximum(tc, 1e-3) * rpp)           # grid pixels inside the outline
        else:                            # a squashed body: its own slope across the grid
            sd = (R - perp) / (_slope(perp) + 1e-6)
        cov = np.clip(0.5 + sd, 0, 1)
        if not cov.any():
            continue
        sq = np.sqrt(np.maximum(b * b - a * (cc - R * R), 0))
        t = (b - sq) / a if q != 1.0 else b - sq
        nbE, nbN, nbU, nbc = (float(v[c]) for v in (pop.nbE, pop.nbN, pop.nbU, pop.nbc))
        cut = E * nbE + N * nbN + U * nbU - R * max(q, 1.0) < nbc and min(cov.shape) > 1
        if cut:                          # the base plane cuts this puff: a flat base where the ray meets it first
            t1 = (b + sq) / a if q != 1.0 else b + sq
            dn_ = dE * nbE + dN * nbN + dU * nbU
            # the edges are anti-aliased by their own slope across the grid, as a shader's fwidth would
            g = t1 * dn_ - nbc                                         # where the ray leaves the puff, above the base
            cov *= np.clip(0.5 + g / (_slope(g) + 1e-6), 0, 1)
            tp = nbc / np.maximum(dn_, 1e-3)
            g = tp - t
            base = np.clip(0.5 + g / (4.0 * _slope(g) + 1e-6), 0, 1)  # 1 on the flat base, soft at its rim
            t = np.maximum(t, tp)
        px, py, pz = t * dE, t * dN, t * dU
        # the puff's sphere and the heap's dome, blended (the dome leads, the puffs give it lumps)
        if q == 1.0:
            ir = wp / R
            gx, gy, gz = (px - E) * ir, (py - N) * ir, (pz - U) * ir
            rim = 1 - np.minimum(np.abs(t - b) * (1 / R), 1)
        else:
            gx, gy, gz = px - E, py - N, (pz - U) / (q * q)
            ln = 1 / (np.sqrt(gx * gx + gy * gy + gz * gz) + 1e-6)
            gx, gy, gz = gx * ln, gy * ln, gz * ln
            rim = 1 - np.minimum(np.abs(gx * dE + gy * dN + gz * dU), 1)
            gx, gy, gz = gx * wp, gy * wp, gz * wp
        fx, fy, fzz = (px - cE) * (1 / (rc * rc)), (py - cN) * (1 / (rc * rc)), (pz - z0) * (1 / (tz * tz))
        ln = (1 - wp) / (np.sqrt(fx * fx + fy * fy + fzz * fzz) + 1e-6)
        bx, by, bz = gx + fx * ln, gy + fy * ln, gz + fzz * ln
        hr = np.clip((pz - 1.0) * (1 / max(T, 1e-3)), 0, 1)
        if cut:
            side = 1 - base
            bx, by, bz = bx * side, by * side, bz * side - base   # the base is lit as the level underside it is
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
        np.maximum(SD[sl], sd, out=SD[sl])
        ec, ez = Ec[sl], Ez[sl]
        crease = ec * (t > ez + 0.04 * R)        # behind a nearer puff's edge: in the crease it makes
        if cut:
            crease = crease * (1 - base)
        s_ = S[:, sl[0], sl[1]]
        for j, v in enumerate((bx, by, bz, hr, rim, br, cd, px, py, crease, rd)):
            s_[j] *= keep
            s_[j] += wn * v
        a_ *= keep
        a_ += wn
        solid = (fw > 0.5) & (cov > 0.5)
        zb[solid] = t[solid]
        ring = np.clip(1 + sd / 5.0, 0, 1) ** 2 * (sd < 0.5)  # the few pixels just outside this puff
        new = (ring > ec) & (tc < zb)            # only where this puff is the nearest thing there
        ec[new], ez[new] = ring[new], tc[new]
    if A.max() <= 0.001:
        return None
    inv = 1 / np.maximum(A, 1e-6)
    S *= inv
    return SimpleNamespace(A=A, nE=S[0], nN=S[1], nU=S[2], hrel=S[3], rim=S[4], brim=S[5], dist=S[6], pE=S[7], pN=S[8],
                           crease=S[9], size=S[10], SD=SD)


# ---------------------------------------------------------------- shading ---
@functools.lru_cache(None)
def billow_tex(seed, cells=32):
    """Round bumps, as a cauliflower's: a periodic 512 x 512 field of sphere caps, one on each of a
    jittered grid of points (cells x cells), each about as wide as the space its point owns; 1 at a
    cap's top, 0 in the creases between them."""
    n = 512
    c = n // cells
    rng = np.random.default_rng(seed)
    py_ = np.arange(cells)[:, None] * c + rng.uniform(0.15, 0.85, (cells, cells)) * c
    px_ = np.arange(cells)[None, :] * c + rng.uniform(0.15, 0.85, (cells, cells)) * c
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    cy, cx = (yy // c).astype(int), (xx // c).astype(int)
    f1 = np.full((n, n), 1e9, np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            j, i = (cy + dy) % cells, (cx + dx) % cells
            qy = py_[j, i] + ((cy + dy) // cells) * n          # the neighbour's point, across the wrap
            qx = px_[j, i] + ((cx + dx) // cells) * n
            f1 = np.minimum(f1, (yy - qy) ** 2 + (xx - qx) ** 2)
    return np.sqrt(np.clip(1 - f1 / (0.75 * c) ** 2, 0, 1)).astype(np.float32)


WARM = np.array([1.16, 1.12, 1.03], np.float32)   # sunlit cloud: a warm white, past white (the grade's shoulder takes it)


def lights(fr):
    """The light on low cloud this minute: direct sun (strength, colour), moonlight (strength, colour)
    and the sky's light on the shaded side, a blue-grey from the cloud's own shade and the sky above."""
    sa = fr.sun_alt
    sac = sa + 1.1                                      # the sun's altitude as the deck sees it
    ds = sm(-0.6, 0.6, sac) * (0.35 + 0.65 * getattr(fr, "sun_through_layers", 1.0))   # less behind higher cloud
    dm = 0.75 * fr.moon_sky * sm(-2, 8, fr.moon_alt) * (1 - ds)
    sunc = keys(CLOUD_SUN, sac) * WARM
    moonc = keys(CLOUD_LIT, sa) + np.array([46, 52, 70], np.float32) * fr.moon_sky
    skyc = keys(CLOUD_SHADE, sa) * 0.66 + keys(SKY_MID, sa) * 0.24 + keys(SKY_ZEN, sa) * 0.06
    return ds, sunc, dm, moonc, skyc


def _ramp(ndl):
    """Light on a face turned ndl toward the light, as a painter would lay it: a broad lit plane and a
    defined, slightly soft turn into shade (cloud is soft, so the turn comes a little past side-on)."""
    return sm(-0.12, 0.38, ndl)


def shade(fr, pop, hit, reg, grid):
    """Colour and coverage of the heaps on the sky grid, inside the box (a pair of slices of the grid)
    that holds them, lit by the scene's own sun and moon.

    Sunlit planes take the sunlight's colour as the deck sees it (it sees the sun set about a degree
    after we do), a warm white at the brightest; the shaded side takes the sky's blue-grey, lighter
    on faces that look up, darkest in the creases between puffs and under the flat base. While the
    sun is below the deck's level but not yet set on it, it lights the bases from below, orange
    toward it and rose away from it; then the earth's shadow climbs past the deck and the heaps go
    violet-grey against the glowing sky. Toward the sun the thin edges glow: a silver lining."""
    rows, cols = np.nonzero(hit.A.max(1) > 0.002)[0], np.nonzero(hit.A.max(0) > 0.002)[0]
    box = (slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1))
    hit = SimpleNamespace(**{k: v[box] for k, v in vars(hit).items()})
    alt, az, e, n, u = (g[box] for g in grid)
    sa = fr.sun_alt
    ds, sunc, dm, moonc, skyc = lights(fr)
    nE, nN, nU = hit.nE, hit.nN, hit.nU
    sv, mv = fr.sunv, fr.moonv
    hrel, down, crease = hit.hrel, np.clip(-nU, 0, 1), np.clip(hit.crease, 0, 1)
    dark = reg.dark
    # cauliflower: billows at two sizes (about 150 m and 60 m) on the face the heap shows us, in
    # coordinates that ride with it (across and up, at its distance), lit from the sun's side and
    # cutting the lit edge into knobs; they fade with distance, where they would only shimmer
    dist = np.maximum(hit.dist, 0.3)                    # the dome's distance
    U_ = np.radians(az) * dist
    V_ = np.radians(alt) * dist
    b1 = sample(billow_tex(85), V_ * 42.0, U_ * 42.0)
    b2 = sample(billow_tex(86), V_ * 115.0 + 37.0, U_ * 115.0 + 11.0)
    near = sm(9.0, 2.5, dist) * (1 - down) * sm(0.0, 0.06, hrel)
    bil = (0.7 * b1 + 0.3 * b2) * near
    gy, gx = np.gradient(bil)
    sx = ((fr.sun_az - az + 180) % 360 - 180) / AZ_SPAN * fr.W           # the sun's way on the screen (right, down)
    sy = (alt - sa) / ALT_TOP * VH * fr.H
    ln = np.sqrt(sx * sx + sy * sy) + 1e-3
    bump = np.clip(-(gx * sx + gy * sy) / ln * 3.5, -0.35, 0.35)
    # the shaded side, lit by the sky
    big = sm(0.25, 0.7, hit.size)                      # small heaps are thin: their bases are lighter
    sky = (0.84 + 0.14 * np.clip(nU, -1, 1) + 0.12 * down * (1 - big)) * (1 - 0.07 * crease) * (1 - 0.3 * dark) * (1 - 0.15 * dark * (1 - hrel))
    under = (0.98 - 0.08 * big) * (0.86 + 0.14 * hit.brim ** 3)   # the flat base: darker under the middle, lighter at its rim,
    if down.max() > 0.5:                                # and mottled, as the air under it is lumpy
        mot = sample(fnoise(256, 256, 2.0, 1.0, 83), hit.pN * 9.0, hit.pE * 9.0)
        mot2 = sample(fnoise(256, 256, 2.0, 1.0, 84), hit.pN * 26.0, hit.pE * 26.0)
        under = under * (1 + 0.09 * np.clip(mot, -2, 2) + 0.05 * np.clip(mot2, -2, 2))
    up = np.clip(gy * 5.0, -0.4, 0.4)                  # billows facing up take more of the sky's light
    sky = sky * (1 - down + under * down) * (1 - 0.2 * near * (1 - np.clip(bil, 0, 1))) * (1 + 0.35 * up) * 0.92
    col = skyc * sky[..., None]
    # the sunlit planes
    Ls = ds * _ramp(nE * sv[0] + nN * sv[1] + nU * sv[2] + bump)
    Ls = Ls * (1 - 0.3 * big * (1 - hrel) ** 1.6 * sm(4, 25, sa)) * (1 - 0.05 * crease)   # high sun: lower body in the puffs' shade
    col += (sunc - col) * (Ls * (1 - 0.3 * dark))[..., None]
    if dm > 0:
        Lm = dm * _ramp(nE * mv[0] + nN * mv[1] + nU * mv[2])
        col += (moonc - col) * Lm[..., None]
    # a low sun lights the undersides: orange toward the sun, rose away from it
    ug = ds * (sm(2.5, 0.0, sa) + 0.2 * sm(9, 2, sa))
    if ug > 0:
        side = sm(-0.5, 0.9, np.cos(np.radians(az - fr.sun_az)))
        w = (0.3 * down + 0.7 * (1 - hrel) ** 1.5) * (0.4 + 0.6 * side) * (1 - 0.4 * dark)
        rose = np.array([242, 120, 150], np.float32)
        tint = rose + (sunc / WARM - rose) * side[..., None]
        col += (ug * w * 0.85)[..., None] * tint
    # toward the sun, light comes through the thin edges: a silver lining, and a glow in the body
    if ds > 0 and sa > -2:
        cg = 1 - (e * sv[0] + n * sv[1] + u * sv[2])
        ph = np.exp(-cg / 0.025) + 0.4 * np.exp(-cg / 0.12)
        edge = np.clip(1 - hit.SD / 3.5, 0, 1) ** 1.5 * (0.35 + 0.65 * np.clip(bil / np.maximum(near, 1e-3), 0, 1))
        edge = edge * (1 - down)                           # the outline of the heap, broken by its knobs
        k = ds * (1 - 0.4 * dark) * (1 - 0.5 * reg.lid)
        col += (ph * (1.5 * edge + 0.2 + 0.15 * (1 - big)) * k)[..., None] * sunc   # small heaps are thin: they glow a little
    col *= 1 - 0.35 * reg.wet
    hm = (0.65 * (1 - np.exp(-hit.dist * (HK / 24.0))) + 0.2 * np.exp(-alt / 4))[..., None]  # haze with distance
    col = col * (1 - hm) + fr.hor_col * hm
    knobs = np.clip(0.5 + hit.SD - 2.6 * near * (1.0 - np.clip(bil, 0, 1)), 0, 1)   # the edge cut into knobs
    a = np.minimum(hit.A, knobs) * sm(1.0, 4.0, alt) * sm(DMAX, DMAX - 3, hit.dist)
    return col, a, box


def horizon_band(fr, reg, grid):
    """Far off, the heaps run together into a band along the horizon: the same cover, drawn as low
    flattened lumps of a noise on the deck (perspective lays them flat), drifting with the heaps, lit
    along their tops and lost in the haze. Colour and coverage on the rows of the sky grid near the
    horizon, and the first of those rows; or None."""
    c = fr.wx.cloud_low * reg.share
    if c < 0.01:
        return None
    alt, az = grid[0], grid[1]
    rows = np.nonzero(alt[:, 0] < 9.0)[0]
    r0 = int(rows[0])
    a, z = alt[r0:], az[r0:]
    ar, zr = np.radians(np.maximum(a, 0.4)), np.radians(z)
    cot = np.cos(ar) / np.sin(ar)
    m = min(fr.m, 1440)
    X = cot * np.sin(zr) - fr.day.drift_e[m] * WF / HK
    Z = -cot * np.cos(zr) + fr.day.drift_n[m] * WF / HK
    tex = fnoise(512, 2048, 2.6, 1.0, 13)
    n0 = sample(tex, Z * 3.0, X * 3.0)
    nu = sample(tex, Z * 3.0 * 1.06 + 0.8, X * 3.0)     # a little farther: higher in the frame
    th = float(np.quantile(n0[a > 1.0], 1 - min(0.9, c)))
    dens = sm(th - 0.1, th + 0.45, n0)
    top = np.clip((dens - sm(th - 0.1, th + 0.45, nu)) * 2.5, 0, 1)   # the upper edge of a lump
    sa = fr.sun_alt
    ds, sunc, dm, moonc, skyc = lights(fr)
    col = skyc[None, None, :] * (0.92 - 0.1 * (1 - dens))[..., None]
    lit = (0.25 + 0.75 * top) * ds * sm(-5, 25, sa) * 0.8 + dm * 0.4 * top
    col = col + (sunc - col) * lit[..., None]
    col *= 1 - 0.35 * reg.wet
    hm = (0.45 + 0.4 * sm(6.0, 0.5, a))[..., None]
    col = col * (1 - hm) + fr.hor_col * hm
    alpha = dens * sm(0.3, 1.6, a) * sm(9.0, 4.5, a) * 0.9
    return col, alpha, r0


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
