"""The tree: a branching skeleton that fills the old canopy's outline, and leaves that come out in
April, darken through summer, turn and fall in October and November, and leave it bare for winter."""
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


class TreeMixin:
    def tree(self):
        s, W, H = self.s, self.W, self.H
        se, wx = self.season, self.wx
        r = np.random.default_rng(8)
        bx, by = TREE_BASE[0] * W, TREE_BASE[1] * H
        ccx, ccy = CANOPY[0] * W, CANOPY[1] * H
        Rx, Ry = CANOPY[2] * s, CANOPY[3] * s
        fx, fy = 0.452 * W, 0.575 * H
        segs, nodes = skeleton(W, H)
        tips = [(x, y, 1.0 if tip else 0.0, 7) for (x, y, w, tip) in nodes if tip or w < 2.6 * s]
        L = Layer(self, ccx - Rx * 1.35, ccy - Ry * 1.35, ccx + Rx * 1.35, by + 20 * s)
        back_sun = max(0.0, -float(self.sunv[1])) * self.sun_str
        pools = self.local(np.float32(bx), np.float32(by - 120 * s)) if self.pools else 0

        # every leaf has its own day to unfold, turn and fall, so the crown changes a little each day
        leaves = []
        for (tx, ty, tip, depth) in tips:
            n = int(r.integers(14, 22) if tip else r.integers(8, 14))
            for _ in range(n):
                ox, oy = r.normal(0, (14 if tip else 11) * s, 2)
                leaves.append((tx + ox, ty + oy * 0.85, r.uniform(0, 1), r.uniform(0, 1), r.uniform(0, 1), r.integers(0, 5), r.uniform(0, math.pi)))
        z = r.uniform(-1, 1, len(leaves))

        grow_ = se.leaf_out
        def draw_leaves(sel):
            for i in sel:
                lx, ly, appear, turn, fall, pal, rot = leaves[i]
                # out in spring (lowest buds last), gone in autumn (the first to turn falls first)
                if appear > grow_ * 1.15 - 0.05 or turn * 0.7 + fall * 0.3 < se.drop * 1.1 - 0.08:
                    continue
                nx, ny = (lx - ccx) / Rx, (ccy - ly) / Ry
                edge = min(1.0, math.hypot(nx, ny))
                cz = z[i]
                ao = (0.55 + 0.45 * (cz + 1) / 2) * (0.75 + 0.25 * edge)
                nrm = normalize([-nx * 0.7 + r.normal(0, 0.25), cz * 0.5 + 0.5 + r.normal(0, 0.2), ny * 0.7 + 0.25 + r.normal(0, 0.2)])
                g = np.array(GREENS[pal], np.float32) * (0.85 + 0.3 * appear)
                g = g * (1 - se.young) + np.array(YOUNG[pal % 3], np.float32) * se.young
                k = sm(turn - 0.12, turn + 0.12, se.autumn * 1.15 - 0.05)
                alb = g * (1 - k) + np.array(AUTUMN[pal], np.float32) * k
                c = alb * (self.light(nrm) * ao + pools)
                c = c + alb * np.array([1.2, 1.35, 0.6]) * self.sun_col * back_sun * 0.45 * edge ** 2
                ls = (6.5 + 4.5 * fall) * s * (0.55 + 0.45 * sm(0.0, 0.7, grow_ - appear + 0.3))
                ca, sa_ = math.cos(rot), math.sin(rot)
                L.poly([(lx + ls * (px * ca - py * sa_), ly + ls * (px * sa_ + py * ca)) for px, py in LEAF], c)

        def draw_masses(front):
            # dark interior of the crown, so it reads as volume rather than confetti
            if se.leaves < 0.15:
                return
            for (tx, ty, ang, depth) in tips[::6]:
                cz = (hash2(tx, ty) * 2 - 1)
                if (cz >= 0) != front:
                    continue
                nx, ny = (tx - ccx) / Rx, (ccy - ty) / Ry
                mass_n = normalize([-nx * 0.8, cz * 0.5 + 0.5, ny * 0.8 + 0.2])
                L.ellipse(tx, ty, 20 * s, 17 * s, np.array([46, 72, 34], np.float32) * (self.light(mass_n) * 0.6 + pools),
                          a=min(1.0, se.leaves * 1.3) * 0.9)

        order = np.argsort(z)
        back = [i for i in order if z[i] < -0.1]
        front = [i for i in order if z[i] >= -0.1]
        draw_leaves(back)
        # branches: rounded with a lit side; the snow sits along their tops
        bark = np.array([78, 64, 52], np.float32)
        for (x0, y0, x1, y1, w0, w1, depth) in segs:
            dx, dy = x1 - x0, y1 - y0
            ln = math.hypot(dx, dy) + 1e-6
            px, py = -dy / ln, dx / ln
            if w0 < 2.2 * s:
                L.line([(x0, y0), (x1, y1)], bark * (self.light(normalize([0, 1, 0.3])) + pools), max(0.6 * s, w0 * 0.9))
                continue
            edges = np.linspace(-1, 1, 6 if depth == 0 else 4)
            for a, b in zip(edges[:-1], edges[1:]):
                m = (a + b) / 2
                c = bark * (self.light(normalize([-m * px, math.sqrt(1 - min(0.99, m * m)), 0.15 - m * py])) + pools)
                L.poly([(x0 + px * w0 * a, y0 + py * w0 * a), (x1 + px * w1 * a, y1 + py * w1 * a),
                        (x1 + px * w1 * b, y1 + py * w1 * b), (x0 + px * w0 * b, y0 + py * w0 * b)], c)
            L.ellipse(x1, y1, w1, w1, bark * (self.light(normalize([0, 1, 0.15])) + pools))
        # fine twigs at the ends, which is most of what you see of a bare tree
        twig = bark * (self.light(normalize([0, 1, 0.3])) + pools) * 0.9
        for (x, y, w, tip) in nodes:
            if w < 1.6 * s:
                for _ in range(2 if tip else 1):
                    a = r.uniform(0, 2 * math.pi)
                    ln = r.uniform(5, 12) * s
                    L.line([(x, y), (x + ln * math.cos(a), y - ln * abs(math.sin(a)) * 0.8 - 1.5 * s)], twig, 0.55 * s)
        if wx.snow_cover > 0.05:
            snowc = self.lit((236, 240, 246), [0, 0.3, 1])
            for (x0, y0, x1, y1, w0, w1, depth) in segs:
                if depth <= 5 and abs(y1 - y0) < 1.4 * abs(x1 - x0):
                    L.line([(x0, y0 - w0 * 0.7), (x1, y1 - w1 * 0.7)], snowc, max(0.8 * s, w0 * 0.45), a=min(1.0, wx.snow_cover * 1.5) * (1 - 0.7 * se.leaves))
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
        # last year's nest shows once the leaves are down
        if se.leaves < 0.25:
            nx_, ny_ = ccx - 0.32 * Rx, ccy + 0.05 * Ry
            nc = self.lit((70, 56, 40), [0, 1, 0.4])
            L.ellipse(nx_, ny_, 11 * s, 5 * s, nc * 0.8, a=1 - se.leaves * 4)
            for k in range(7):
                a = k / 7 * math.pi
                L.line([(nx_ - 11 * s * math.cos(a), ny_ - 2 * s), (nx_ + 9 * s * math.cos(a + 0.4), ny_ + 3 * s)], nc, 1.0 * s, a=1 - se.leaves * 4)
        draw_leaves(front)
        L.composite()
