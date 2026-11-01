"""The tree: a branching skeleton that fills the old canopy's outline, and leaves that come out in
April, darken through summer, turn and fall in October and November, and leave it bare for winter.

The leaves grow in clumps round the twig ends. Each leaf takes its normal partly from its clump and
partly from the crown, so a clump is lit on the side that faces the sun and the crown on the side
that faces it, and each is darker inside and underneath; the light itself comes from the scene. The
trunk, roots and thicker limbs are drawn per pixel with bark (furrows between plates) as albedo and
normals, made once (bark_maps), and lit each keyframe, in the canopy's shade where it falls on them."""
import functools
import math

import numpy as np
from scipy.spatial import cKDTree

from core import *  # noqa: F401,F403

GREENS = [(62, 98, 42), (74, 112, 46), (56, 88, 40), (88, 120, 52), (70, 104, 40)]
YOUNG = [(124, 162, 62), (138, 172, 72), (110, 150, 56)]
AUTUMN = [(210, 164, 50), (218, 124, 42), (186, 72, 38), (156, 100, 50), (196, 142, 46)]
LEAF = [(1.0, 0.0), (0.5, 0.36), (0.0, 0.42), (-0.45, 0.28), (-0.62, 0.0), (-0.45, -0.28), (0.0, -0.42), (0.5, -0.36)]


def envelope(th):
    return 1 + 0.10 * math.sin(3 * th + 0.7) + 0.07 * math.sin(5 * th + 2.1) + 0.05 * math.sin(8 * th)


@functools.lru_cache(None)
def skeleton(W, H):
    """Branches grown by space colonisation toward points scattered through the crown's outline, so
    the bare tree fills the same shape the leaves do. Returns segments (x0, y0, x1, y1, w0, w1, depth)
    and nodes (x, y, width, is_tip). The same tree every day."""
    s = W / 3840
    rng = np.random.default_rng(7)
    ccx, ccy = CANOPY[0] * W, CANOPY[1] * H
    Rx, Ry = CANOPY[2] * s, CANOPY[3] * s
    pts = []
    vmax = (0.548 * H - ccy) / Ry                 # the crown's underside is nearly flat, as before
    while len(pts) < 2600:
        u, v = rng.uniform(-1.05, 1.05, 2)
        th = math.atan2(-v, u)
        env = 1 + 0.07 * math.sin(3 * th + 0.7) + 0.05 * math.sin(5 * th + 2.1)
        if math.hypot(u, v) < 0.96 * env and v < vmax:
            pts.append((ccx + u * Rx, ccy + v * Ry))
    P = np.array(pts)
    fx, fy = 0.452 * W, 0.575 * H
    nodes = [(fx, fy)]
    parent = [-1]
    D, di, dk = 8 * s, 46 * s, 11 * s
    # three main limbs from the fork, as the old tree had; the crown grows out of them
    for a, ln in ((2.25, 150), (1.62, 115), (0.95, 160)):
        prev, x, y, ang = 0, fx, fy, a
        for _ in range(int(ln * s / D)):
            ang += rng.normal(0, 0.04) + 0.03 * (math.pi / 2 - ang)
            x, y = x + D * math.cos(ang), y - D * math.sin(ang)
            nodes.append((x, y))
            parent.append(prev)
            prev = len(nodes) - 1
    for _ in range(600):
        tree = cKDTree(np.array(nodes))
        d, idx = tree.query(P, distance_upper_bound=di)
        ok = np.isfinite(d)
        if not ok.any():
            x, y = nodes[-1]
            nodes.append((x + rng.normal(0, 0.2) * D, y - D))
            parent.append(len(nodes) - 2)
            continue
        acc = {}
        for p_, i in zip(P[ok], idx[ok]):
            v = p_ - np.array(nodes[i])
            acc[i] = acc.get(i, 0) + v / (np.linalg.norm(v) + 1e-6)
        grew = False
        for i, v in acc.items():
            v = v / (np.linalg.norm(v) + 1e-6) + np.array([rng.normal(0, 0.12), -0.12])
            v /= np.linalg.norm(v) + 1e-6
            q = (nodes[i][0] + D * v[0], nodes[i][1] + D * v[1])
            if min(math.hypot(q[0] - a, q[1] - b) for a, b in nodes[-40:]) < 0.5 * D:
                continue
            nodes.append(q)
            parent.append(i)
            grew = True
        dd, _ = cKDTree(np.array(nodes)).query(P)
        P = P[dd > dk]
        if len(P) == 0 or not grew:
            break
    n = len(nodes)
    kids = [[] for _ in range(n)]
    for i in range(1, n):
        kids[parent[i]].append(i)
    w = np.zeros(n)
    for i in range(n - 1, -1, -1):
        w[i] = (sum(w[k] ** 2.4 for k in kids[i]) + (1.0 if not kids[i] else 0.0)) ** (1 / 2.4)
    w *= 15 * s / w[0]
    w = np.maximum(w, 0.55 * s)
    depth = np.zeros(n, int)
    for i in range(1, n):
        depth[i] = depth[parent[i]] + (1 if len(kids[parent[i]]) > 1 else 0)
    segs = []
    bx, by = TREE_BASE[0] * W, TREE_BASE[1] * H
    tp = [(bx + (fx - bx) * t + 6 * s * math.sin(t * 5), by + (fy - by) * t) for t in np.linspace(0, 1, 6)]
    tw = np.linspace(26, 15, 6) * s
    for i in range(5):
        segs.append((*tp[i], *tp[i + 1], tw[i], tw[i + 1], 0))
    for i in range(1, n):
        p_ = parent[i]
        segs.append((nodes[p_][0], nodes[p_][1], nodes[i][0], nodes[i][1], w[i] * 1.04, w[i], int(depth[i]) + 1))
    out = [(nodes[i][0], nodes[i][1], w[i], not kids[i]) for i in range(n)]
    return segs, out


@functools.lru_cache(maxsize=2)
def leaf_set(W, H):
    """Every leaf the tree can carry, with what does not change from day to day: where it is, its own
    days to unfold, turn and fall, its colour and angle, its clump, its normal, its occlusion, and
    whether it falls in one of the crown's gaps."""
    s = W / 3840
    segs, nodes = skeleton(W, H)
    r = np.random.default_rng(8)
    ccx, ccy = CANOPY[0] * W, CANOPY[1] * H
    Rx, Ry = CANOPY[2] * s, CANOPY[3] * s
    tips = [(x, y, 1.0 if tip else 0.0) for (x, y, w, tip) in nodes if tip or w < 2.6 * s]
    rows = []
    for (tx, ty, tip) in tips:
        n = int(r.integers(14, 22) if tip else r.integers(8, 14))
        for _ in range(n):
            ox, oy = r.normal(0, (14 if tip else 11) * s, 2)
            rows.append((tx + ox, ty + oy * 0.85, r.uniform(0, 1), r.uniform(0, 1), r.uniform(0, 1), r.integers(0, 5), r.uniform(0, math.pi)))
    A = np.array(rows, np.float64)
    lx, ly = A[:, 0], A[:, 1]
    q = np.random.default_rng(81)
    # clumps: k-means from a jittered grid, a few rounds
    g = 50 * s
    gx, gy = np.meshgrid(np.arange(ccx - 1.3 * Rx, ccx + 1.3 * Rx, g), np.arange(ccy - 1.3 * Ry, ccy + 1.3 * Ry, g * 0.85))
    C = np.stack([gx.ravel(), gy.ravel()], 1) + q.uniform(-0.3, 0.3, (gx.size, 2)) * g
    P = np.stack([lx, ly], 1)
    for _ in range(4):
        lab = cKDTree(C).query(P)[1]
        cnt = np.bincount(lab, minlength=len(C))
        keep = cnt > 0
        C = np.stack([np.bincount(lab, P[:, 0], len(C)), np.bincount(lab, P[:, 1], len(C))], 1)[keep] / cnt[keep, None]
    lab = cKDTree(C).query(P)[1]
    d = P - C[lab]
    rad = np.sqrt(np.bincount(lab, (d ** 2).sum(1), len(C)) / np.maximum(1, np.bincount(lab, None, len(C))))
    Rk = np.maximum(rad * 1.6, 14 * s)[lab]
    dx, dy = d[:, 0] / Rk, d[:, 1] / Rk
    rr = np.minimum(np.hypot(dx, dy), 0.97)
    k = rr / (np.hypot(dx, dy) + 1e-9)
    dx, dy = dx * k, dy * k
    lz = np.sqrt(1 - dx ** 2 - dy ** 2)
    zk = q.uniform(-1, 1, len(C))[lab]
    nc = len(C)
    tone = (1 + 0.14 * (q.uniform(0, 1, nc) - 0.5))[lab]      # each clump a shade of its own
    # a clump's leaves sit a little closer together than the twigs' spread, and mostly share its
    # colour, and a twig's leaves turn together, so the crown reads in clumps rather than as confetti
    lx, ly = C[lab, 0] + 0.88 * (lx - C[lab, 0]), C[lab, 1] + 0.88 * (ly - C[lab, 1])
    pal = np.where(q.uniform(0, 1, len(lx)) < 0.55, q.integers(0, 5, nc)[lab], A[:, 5].astype(int))
    turn = 0.55 * A[:, 3] + 0.45 * q.uniform(0, 1, nc)[lab]
    # the crown as a whole: an ellipsoid; front clumps face the camera, back ones away from it
    nx, ny = (lx - ccx) / Rx, (ccy - ly) / Ry
    e2 = nx ** 2 + ny ** 2
    edge = np.minimum(1.0, np.sqrt(e2))
    gz = np.sqrt(np.clip(1 - e2, 0.04, 1))
    Gf = normalize(np.stack([-nx, gz, ny + 0.1], 1))
    Gb = normalize(np.stack([-nx, -gz, ny + 0.1], 1))
    G = np.where((zk < -0.25)[:, None], Gb, Gf)
    Lc = np.stack([-dx, lz, -dy], 1)
    jit = q.normal(0, 1, (len(lx), 3)) * 0.14
    N = normalize(0.75 * Lc + 0.32 * Gf + jit + np.array([0, 0, 0.3]))     # leaves turn up to the sky
    # how deep in the crown and in its clump a leaf sits, which hides the sky from it
    ao = (0.84 + 0.16 * edge ** 0.8) * (0.74 + 0.26 * ((1 - dy) / 2) ** 0.8 * (0.7 + 0.3 * lz)) * (0.9 + 0.1 * (zk + 1) / 2) \
        * (1 - 0.25 * np.clip(-ny, 0, 1) ** 1.5)
    ao = np.where(zk < -0.25, ao * 0.85, ao)
    # draw back to front: clump depth first, then within the clump
    zl = zk * 0.7 + (lz - 0.5) * 0.5 + q.uniform(-0.08, 0.08, len(lx))
    # gaps where the sky shows through, more of them toward the edge, which they break up
    gn = sample(fnoise(128, 128, 2.0, 1.0, 83), (ly - ccy) / s * 0.26, (lx - ccx) / s * 0.26)
    gap = gn > 1.75 - 0.5 * sm(0.4, 0.9, edge) + 0.6 * sm(0.9, 1.05, edge)
    return dict(lx=lx, ly=ly, appear=A[:, 2], turn=turn, fall=A[:, 4], pal=pal, rot=A[:, 6],
                N=N.astype(np.float32), tone=tone.astype(np.float32), G=G.astype(np.float32), Lc=Lc.astype(np.float32), ao=ao.astype(np.float32),
                edge=edge, rim=rr, zl=zl, back=zl < -0.12, gap=gap, ny=ny)


def bark(around, along, s):
    """Bark: plates split by narrow furrows that run along the limb, wandering, now and then bridged.
    Takes coordinates in frame pixels round and along the limb; returns (relief in frame pixels,
    albedo factor, a slow noise for lichen)."""
    u, v = np.broadcast_arrays(around / s, along / s)
    wob = sample(fnoise(256, 256, 2.2, 0.3, 91), v * 0.05, u * 0.12)
    ph = u / 5.5 + 0.9 * wob
    d = np.abs(ph - np.round(ph))
    brk = sample(fnoise(256, 256, 1.8, 0.25, 92), v * 0.09, u * 0.25)
    furrow = sm(0.2, 0.04, d) * sm(-0.8, 0.0, brk)
    n2 = sample(fnoise(256, 256, 1.4, 1.0, 95), v * 0.9, u * 0.9)
    n3 = sample(fnoise(256, 256, 2.2, 0.5, 93), v * 0.2, u * 0.2)
    h = s * (1.5 * (1 - furrow) + 0.25 * n2)
    f = (0.52 + 0.62 * (1 - furrow)) * (1 + 0.06 * n2 + 0.09 * n3)
    return h, f, n3


@functools.lru_cache(maxsize=2)
def bark_maps(W, H):
    """The trunk, its roots and every limb thicker than a twig, painted once into flat buffers: albedo,
    normal, coverage and occlusion, and how far inside the crown each pixel is (where the leaves will
    shade it). Roots first, then the trunk and limbs from the ground up, each over the last."""
    s = W / 3840
    segs, nodes = skeleton(W, H)
    bx, by = TREE_BASE[0] * W, TREE_BASE[1] * H
    ccx, ccy = CANOPY[0] * W, CANOPY[1] * H
    Rx, Ry = CANOPY[2] * s, CANOPY[3] * s
    fx, fy = 0.452 * W, 0.575 * H
    thick = [q for q in segs if q[4] >= 3 * s and q[6] > 0]
    pad = 3
    x0 = int(math.floor(min(min(q[0], q[2]) - max(q[4], q[5]) for q in thick))) - pad
    x1 = int(math.ceil(max(max(q[0], q[2]) + max(q[4], q[5]) for q in thick))) + pad
    y0 = int(math.floor(min(min(q[1], q[3]) - max(q[4], q[5]) for q in thick))) - pad
    y1 = int(math.ceil(max(max(q[1], q[3]) + max(q[4], q[5]) for q in thick))) + pad
    x0, x1 = min(x0, int(bx - 52 * s) - pad), max(x1, int(bx + 52 * s) + pad)
    y1 = max(y1, int(by + 8 * s) + pad)
    h, w = y1 - y0, x1 - x0
    ALB, NRM = np.zeros((h, w, 3), np.float32), np.zeros((h, w, 3), np.float32)
    COV, AO = np.zeros((h, w), np.float32), np.zeros((h, w), np.float32)
    # distance along the tree from the ground, so the bark runs on from one segment to the next
    start = {}
    tip_of = {}
    for q in segs:
        a = (round(q[0], 3), round(q[1], 3))
        b = (round(q[2], 3), round(q[3], 3))
        la = tip_of.get(a, 0.0)
        tip_of[b] = la + math.hypot(q[2] - q[0], q[3] - q[1])
        start[id(q)] = la
    base_col = np.array([78, 64, 52], np.float32)

    def put(X0, Y0, cov, alb, nrm, ao):
        sl = (slice(Y0 - y0, Y0 - y0 + cov.shape[0]), slice(X0 - x0, X0 - x0 + cov.shape[1]))
        c = cov[..., None]
        ALB[sl] = ALB[sl] * (1 - c) + alb * c
        NRM[sl] = NRM[sl] * (1 - c) + nrm * c
        AO[sl] = AO[sl] * (1 - cov) + ao * cov
        COV[sl] = COV[sl] * (1 - cov) + cov

    # the trunk, swept row by row from the fork to the ground, flaring into its roots at the foot
    X0, X1 = int(bx - 52 * s), int(bx + 52 * s)
    Y0, Y1 = int(fy - 6 * s), int(by + 8 * s)
    Xg = np.arange(X0, X1, dtype=np.float32)[None, :] + 0.5
    Yg = np.arange(Y0, Y1, dtype=np.float32)[:, None] + 0.5
    t = np.clip((by - Yg) / (by - fy), 0, 1)
    xc = bx + (fx - bx) * t + 6 * s * np.sin(t * 5)
    fl = sm(by - 40 * s, by + 5 * s, Yg) ** 1.5
    wt = 26 * s - 11 * s * t + 20 * s * fl
    m_ = (Xg - xc) / wt
    m = np.clip(m_, -0.98, 0.98)
    edge_n = sample(fnoise(4, 256, 1.6, 1.0, 96)[:1].repeat(4, 0), 0 * Xg + 1.0, Xg / s * 0.4)
    ybot = by + 5 * s - 5 * s * m ** 2 + 1.5 * s * edge_n
    cov = np.clip(wt - np.abs(Xg - xc) + 0.5, 0, 1) * np.clip(ybot - Yg + 0.5, 0, 1) * np.clip(Yg - (fy - 4 * s) + 0.5, 0, 1)
    around, along = np.arcsin(m) * wt, by - Yg
    hh, f, n3 = bark(around, along, s)
    roots = sum(np.exp(-((m - mi) / 0.13) ** 2) for mi in (-0.8, -0.38, 0.1, 0.6))
    hh = hh + fl * 3.0 * s * roots
    nrm = np.stack([-m, np.sqrt(1 - m ** 2), 0.15 + 0.9 * fl * np.abs(m)], -1)
    nrm = bump_normal(nrm, hh, 0.9)
    alb = base_col * f[..., None]
    alb = alb + (np.array([112, 116, 96], np.float32) - alb) * (sm(0.9, 1.6, n3) * 0.35)[..., None]
    alb = alb * (1 - 0.22 * sm(by - 30 * s, by + 5 * s, Yg))[..., None]
    ao = (0.6 + 0.4 * np.sqrt(1 - m ** 2)) * (1 - 0.4 * sm(by - 14 * s, by + 6 * s, Yg)) * (1 - 0.3 * fl * (1 - np.clip(roots, 0, 1)))
    put(X0, Y0, cov, alb, nrm, ao)
    # the limbs, segment by segment from the fork outward
    for q in thick:
        xa, ya, xb, yb_, w0, w1, depth = q
        X0 = int(max(x0, math.floor(min(xa, xb) - max(w0, w1) - 2)))
        X1 = int(min(x1, math.ceil(max(xa, xb) + max(w0, w1) + 2)))
        Y0 = int(max(y0, math.floor(min(ya, yb_) - max(w0, w1) - 2)))
        Y1 = int(min(y1, math.ceil(max(ya, yb_) + max(w0, w1) + 2)))
        Xg = np.arange(X0, X1, dtype=np.float32)[None, :] + 0.5
        Yg = np.arange(Y0, Y1, dtype=np.float32)[:, None] + 0.5
        dx, dy = xb - xa, yb_ - ya
        ln = math.hypot(dx, dy) + 1e-6
        ux, uy = dx / ln, dy / ln
        px, py = -uy, ux                         # across, to screen right for a limb that goes up
        t_ = ((Xg - xa) * ux + (Yg - ya) * uy) / ln
        t = np.clip(t_, 0, 1)
        o = (Xg - xa) * px + (Yg - ya) * py
        wt = w0 + (w1 - w0) * t
        dist = np.hypot(Xg - (xa + dx * t), Yg - (ya + dy * t))
        cov = np.clip(wt - dist + 0.5, 0, 1)
        if not cov.any():
            continue
        m = np.clip(o / wt, -0.98, 0.98)
        along = start.get(id(q), 0.0) + t_ * ln
        around = np.arcsin(m) * wt
        hh, f, n3 = bark(around, along, s)
        hh = hh * np.clip(wt / (8 * s), 0.3, 1)          # a thin limb shows less of its bark's relief
        nrm = np.stack([-m * px, np.sqrt(1 - m ** 2), 0.15 - m * py], -1)
        nrm = bump_normal(nrm, hh, 0.9)
        alb = base_col * f[..., None]
        alb = alb + (np.array([112, 116, 96], np.float32) - alb) * (sm(0.9, 1.6, n3) * 0.35)[..., None]
        ao = 0.6 + 0.4 * np.sqrt(1 - m ** 2)
        put(X0, Y0, cov, alb, nrm, ao)
    k = np.maximum(COV, 1e-6)
    ALB /= k[..., None]
    AO /= k
    NRM = normalize(NRM)
    X = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
    Y = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
    # inside the crown, where the leaves shade the limbs
    inside = sm(1.05, 0.8, np.hypot((X - ccx) / Rx, (Y - ccy) / Ry))
    dap = sample(fnoise(128, 128, 1.6, 1.0, 94), Y / s * 0.12 + 0 * X, X / s * 0.12 + 0 * Y)
    idx = np.nonzero(COV > 0.002)
    return dict(box=(x0, y0, x1, y1), idx=idx, X=np.broadcast_to(X, COV.shape)[idx], Y=np.broadcast_to(Y, COV.shape)[idx],
                alb=ALB[idx], nrm=NRM[idx], ao=AO[idx], cov=COV, inside=np.broadcast_to(inside, COV.shape)[idx],
                dap=dap[idx], cb=ccy + 0.42 * Ry, Rx=Rx)


@functools.lru_cache(maxsize=2)
def twig_set(W, H):
    """The fine twigs at the ends, which are most of what you see of a bare tree: (x0, y0, x1, y1)."""
    s = W / 3840
    segs, nodes = skeleton(W, H)
    r = np.random.default_rng(9)
    out = []
    for (x, y, w, tip) in nodes:
        if w < 1.6 * s:
            for _ in range(2 if tip else 1):
                a = r.uniform(0, 2 * math.pi)
                ln = r.uniform(5, 12) * s
                out.append((x, y, x + ln * math.cos(a), y - ln * abs(math.sin(a)) * 0.8 - 1.5 * s))
    return out


class TreeMixin:
    def tree(self):
        s, W, H = self.s, self.W, self.H
        se, wx = self.season, self.wx
        bx, by = TREE_BASE[0] * W, TREE_BASE[1] * H
        ccx, ccy = CANOPY[0] * W, CANOPY[1] * H
        Rx, Ry = CANOPY[2] * s, CANOPY[3] * s
        segs, nodes = skeleton(W, H)
        box = (ccx - Rx * 1.35, ccy - Ry * 1.35, ccx + Rx * 1.35, by + 20 * s)
        sunv = self.sunv
        back_sun = max(0.0, -float(sunv[1])) * self.sun_str
        pools = self.local(np.float32(bx), np.float32(by - 120 * s)) if self.pools else 0
        # how much the crown shades what is under and inside it: a leafy crown nearly all of the sun,
        # a bare one a little
        dens = 0.22 + 0.7 * se.leaves

        # every leaf has its own day to unfold, turn and fall, so the crown changes a little each day
        F = leaf_set(W, H)
        grow_ = se.leaf_out
        vis = ~((F["appear"] > grow_ * 1.15 - 0.05) | (F["turn"] * 0.7 + F["fall"] * 0.3 < se.drop * 1.1 - 0.08) | F["gap"])
        polys = []
        if vis.any():
            ix = np.nonzero(vis)[0]
            pal = F["pal"][ix]
            appear = F["appear"][ix]
            g = np.array(GREENS, np.float32)[pal] * (0.85 + 0.3 * appear)[:, None]
            g = g * (1 - se.young) + np.array(YOUNG, np.float32)[pal % 3] * se.young
            kk = sm(F["turn"][ix] - 0.12, F["turn"][ix] + 0.12, se.autumn * 1.15 - 0.05)[:, None]
            alb = (g * (1 - kk) + np.array(AUTUMN, np.float32)[pal] * kk) * F["tone"][ix, None]
            # the crown shades its own far side and its inside; a clump its own far side
            expo_g = sm(-0.45, 0.35, F["G"][ix] @ sunv)
            expo_l = sm(-0.4, 0.45, F["Lc"][ix] @ sunv)
            shade = 1 - expo_g * (0.5 + 0.5 * expo_l) * np.where(F["back"][ix], 0.6, 1.0)
            c = alb * (self.light(F["N"][ix], shade=shade, ao=F["ao"][ix]) + pools)
            # with the sun behind the tree, light comes through the leaves at the crown's rim and the clumps'
            rim = np.maximum(F["edge"][ix] ** 2, 0.3 * F["rim"][ix] ** 3 * F["edge"][ix] * (1 - F["back"][ix]))
            c = c + alb * np.array([1.2, 1.35, 0.6], np.float32) * self.sun_col * back_sun * 0.45 * rim[:, None]
            ls = (6.5 + 4.5 * F["fall"][ix]) * s * (0.55 + 0.45 * sm(0.0, 0.7, grow_ - appear + 0.3))
            rot = F["rot"][ix]
            ca, sa_ = np.cos(rot), np.sin(rot)
            lp = np.array(LEAF, np.float32)
            px = F["lx"][ix, None] + ls[:, None] * (lp[None, :, 0] * ca[:, None] - lp[None, :, 1] * sa_[:, None])
            py = F["ly"][ix, None] + ls[:, None] * (lp[None, :, 0] * sa_[:, None] + lp[None, :, 1] * ca[:, None])
            order = np.argsort(F["zl"][ix], kind="stable")
            polys = (ix, order, px, py, c)

        def draw_leaves(L, back):
            if not polys:
                return
            ix, order, px, py, c = polys
            sel = order[F["back"][ix][order] == back]
            P = L.P
            for i in sel:
                L.d.polygon([P(a, b) for a, b in zip(px[i], py[i])], fill=rgba(c[i]))

        L = Layer(self, *box)
        draw_leaves(L, True)
        L.composite()
        # the trunk, roots and limbs, per pixel
        B = bark_maps(W, H)
        x0, y0, x1, y1 = B["box"]
        sh = B["inside"] * dens * (0.75 + 0.25 * np.clip(B["dap"], -1, 1))
        if self.sun_alt > 0.5:
            # below the crown the trunk is in its shadow once the sun is high enough to look over it
            reach = np.maximum(B["Y"] - B["cb"], 0) / math.tan(math.radians(self.sun_alt))
            sh = np.maximum(sh, (1 - B["inside"]) * dens * sm(1.05 * B["Rx"], 0.7 * B["Rx"], reach + 30 * s * B["dap"]))
        col = np.zeros(B["cov"].shape + (3,), np.float32)
        col[B["idx"]] = B["alb"] * (self.light(B["nrm"], shade=np.clip(sh, 0, 1), ao=B["ao"])
                                    + (self.local(B["X"], B["Y"]) if self.pools else 0))
        self.over(y0, y1, x0, x1, col * B["cov"][..., None], B["cov"][..., None])
        L = Layer(self, *box)
        # thin branches and twigs, shaded inside a leafy crown
        bark_c = np.array([78, 64, 52], np.float32)
        thin_l = bark_c * (self.light(normalize([0, 1, 0.3]), shade=dens) + pools)
        for (xa, ya, xb, yb_, w0, w1, depth) in segs:
            if w0 < 3 * s:
                L.line([(xa, ya), (xb, yb_)], thin_l, max(0.6 * s, w0 * 0.9))
        twig = thin_l * 0.9
        for (xa, ya, xb, yb_) in twig_set(W, H):
            L.line([(xa, ya), (xb, yb_)], twig, 0.55 * s)
        if wx.snow_cover > 0.05:
            snowc = self.lit((236, 240, 246), [0, 0.3, 1])
            for (xa, ya, xb, yb_, w0, w1, depth) in segs:
                if depth <= 5 and abs(yb_ - ya) < 1.4 * abs(xb - xa):
                    L.line([(xa, ya - w0 * 0.7), (xb, yb_ - w1 * 0.7)], snowc, max(0.8 * s, w0 * 0.45), a=min(1.0, wx.snow_cover * 1.5) * (1 - 0.7 * se.leaves))
        # last year's nest shows once the leaves are down
        if se.leaves < 0.25:
            nx_, ny_ = ccx - 0.32 * Rx, ccy + 0.05 * Ry
            nc = self.lit((70, 56, 40), [0, 1, 0.4])
            L.ellipse(nx_, ny_, 11 * s, 5 * s, nc * 0.8, a=1 - se.leaves * 4)
            for k in range(7):
                a = k / 7 * math.pi
                L.line([(nx_ - 11 * s * math.cos(a), ny_ - 2 * s), (nx_ + 9 * s * math.cos(a + 0.4), ny_ + 3 * s)], nc, 1.0 * s, a=1 - se.leaves * 4)
        draw_leaves(L, False)
        L.composite()
