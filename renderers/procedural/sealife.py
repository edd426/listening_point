"""The boats and animals of the bay (v3 phase 4, part 2), drawn: the creel boat at the pots, extra yachts,
the island ferry, seals on the skerry, a cormorant drying its wings, gannets diving and a pod of dolphins.
When and where each is comes from seaplan.py; this draws them.

The boats are small models in their own metres (a hull from a few stations, boxes for the deckhouses, sticks
for masts, flat sails), placed on the sea and projected with the frame's own camera, so they turn and
foreshorten as they would, each face lit by the scene's sun, moon and sky (with the cloud shadow on the
water where they are) and edged in ink, in the manner of a hand-drawn game background. They sit in the
water: a waterline, a wash or a wake, and a reflection broken by the ripples. The animals are sprites, as
the hillside's are (fauna.Sprite). No people: the wheelhouse and the ferry's windows are glass, lit at night.

None of it runs in reference mode, and none of it draws from the frame's shared generator.
"""
import math

import numpy as np

from core import *  # noqa: F401,F403
from events import catmull, smoothstep
from fauna import Sprite
from seaplan import (CREEL_B, CREEL_FROM, CREEL_IN, CREEL_L, CREEL_OUT, CORMORANT_KNOB, FERRY_B, FERRY_L, SEAL_SPOTS,
                     heading_of, skerry_point)
from water import sea_point

U = 15.0                 # metres in a world unit
CAM = np.array([0.0, 1.0, 0.0])


def unit(*k):
    return float(np.random.default_rng([int(v) % 2 ** 32 for v in k]).random())


class Model:
    """A boat as flat faces in its own metres: x forward, y up from the waterline, z to port. Each face has an
    outward hint (local), so it can be culled when it faces away, and a part: parts are drawn in order (the
    hull, then what stands on the deck, level by level), each part's faces far to near."""

    def __init__(self):
        self.faces = []      # (pts (n, 3), albedo, part, hint, two-sided, ink, tag)
        self.sticks = []     # (points (n, 3), width m, albedo, part, tag)

    def face(self, pts, alb, part=1, hint=(0, 1, 0), two=False, ink=True, tag=None):
        self.faces.append((np.asarray(pts, np.float64), np.asarray(alb, np.float32), part, np.asarray(hint, np.float64),
                           two, ink, tag))

    def box(self, x0, x1, y0, y1, z0, z1, alb, part=1, top=None, ink=True, tag=None, front=None):
        top = alb if top is None else top
        front = alb if front is None else front
        F = self.face
        F([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], top, part, (0, 1, 0), ink=ink, tag=tag)
        F([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], front, part, (1, 0, 0), ink=ink, tag=tag)
        F([(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)], alb, part, (-1, 0, 0), ink=ink, tag=tag)
        F([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], alb, part, (0, 0, 1), ink=ink, tag=tag)
        F([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], alb, part, (0, 0, -1), ink=ink, tag=tag)

    def hull(self, st, side, deck, transom=None, part=0):
        """A hull from stations (x deck, half-beam at the deck, half-beam at the waterline, deck height, x at the
        waterline), stern to bow; the last is the stem."""
        transom = side if transom is None else transom
        for zs in (1, -1):
            for a, b in zip(st[:-1], st[1:]):
                pts = [(a[4], 0, zs * a[2]), (b[4], 0, zs * b[2]), (b[0], b[3], zs * b[1]), (a[0], a[3], zs * a[1])]
                self.face(pts, side, part, (0, 0, zs), ink=False, tag="side")
        dk = [(p[0], p[3], p[1]) for p in st] + [(p[0], p[3], -p[1]) for p in st[::-1]]
        self.face(dk, deck, part, (0, 1, 0), ink=False, tag="deck")
        a = st[0]
        self.face([(a[4], 0, a[2]), (a[4], 0, -a[2]), (a[0], a[3], -a[1]), (a[0], a[3], a[1])], transom, part, (-1, 0, 0),
                  ink=False, tag="transom")
        self.st = st

    def stick(self, pts, w, alb, part=3, tag=None):
        self.sticks.append((np.asarray(pts, np.float64), w, np.asarray(alb, np.float32), part, tag))


class Placed:
    """A model set on the sea at world (X, Z) with a heading (a unit vector in world x, z) and a heel (radians,
    to port), as the frame sees it."""

    def __init__(self, fr, X, Z, h, heel=0.0, lift=0.0):
        self.fr, self.X, self.Z, self.h = fr, X, Z, h
        self.p = (-h[1], h[0])                      # port, in world x, z
        self.c, self.sn = math.cos(heel), math.sin(heel)
        self.lift = lift
        self.D = math.hypot(X, Z)
        fr_ = fr
        self.kx = fr_.W / math.radians(AZ_SPAN) / self.D / U       # px per metre across
        self.ky = VH * fr_.H / math.radians(ALT_TOP) / self.D / U  # px per metre up
        # which side the camera sees: port if it lies to port
        self.port_seen = (-X) * self.p[0] + (-Z) * self.p[1] > 0

    def rot(self, P):
        P = np.atleast_2d(np.asarray(P, np.float64))
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        y2 = y * self.c - z * self.sn
        z2 = z * self.c + y * self.sn
        hx, hz = self.h
        px, pz = self.p
        return np.stack([x * hx + z2 * px, y2, x * hz + z2 * pz], 1)

    def world(self, P, mirror=False):
        R = self.rot(P) / U
        R[:, 0] += self.X
        R[:, 2] += self.Z
        R[:, 1] += self.lift
        if mirror:
            R[:, 1] = -R[:, 1]
        return R

    def screen(self, P, mirror=False):
        Wp = self.world(P, mirror)
        x, y = self.fr.proj(Wp[:, 0], Wp[:, 1], Wp[:, 2])
        return np.stack([x, y], 1)

    def normal(self, pts, hint):
        Wp = self.world(pts)
        n = np.zeros(3)
        for i in range(len(Wp)):            # Newell's method: robust for any planar polygon
            a, b = Wp[i], Wp[(i + 1) % len(Wp)]
            n += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
        nn = np.linalg.norm(n)
        if nn < 1e-12:
            return None, Wp.mean(0)
        n /= nn
        hw = self.rot([hint])[0]
        if n @ hw < 0:
            n = -n
        return n, Wp.mean(0)


def enu(n):
    """World normal (x west, y up, z south) to the lights' east, north, up."""
    return np.array([-n[0], -n[2], n[1]], np.float32)


class SeaLifeMixin:
    # ================================================================ models --
    def haze_of(self, D):
        return 0.5 * (1 - math.exp(-D / 70.0))

    def model_draw(self, M, pl, L, R=None, shade=None, glass=None, back=False):
        """Draw model M placed by pl into layer L (and its reflection into R): visible faces part by part, far to
        near, lit by their normals; an ink edge round each box face and round the hull's silhouette. glass: an
        override colour per tag (lit windows). Returns the hull's screen points (for the waterline)."""
        hz_k = self.haze_of(pl.D)
        hor = self.hor_col
        ink_w = max(0.45, min(0.95 * self.s / 0.75, 0.006 * pl.kx * 36))
        items = []
        for pts, alb, part, hint, two, ink, tag in M.faces:
            n, c = pl.normal(pts, hint)
            if n is None:
                continue
            to_cam = CAM - c
            facing = float(n @ to_cam)
            if facing <= 0 and not two:
                continue
            if two and facing < 0:
                n = -n
            col = self.lit(alb, enu(n), shade=shade)
            if two and self.sun_str > 0:     # a sail with the sun behind it glows through
                back_l = max(0.0, -float(enu(n) @ self.sunv)) * self.sun_str
                col = col + np.asarray(alb, np.float32) * self.sun_col * back_l * 0.45
            if glass is not None and tag in glass:
                col = glass[tag]
            col = col * (1 - hz_k) + hor * hz_k
            items.append((part, -float(np.linalg.norm(to_cam)), pts, col, ink, tag))
        for pts, w, alb, part, tag in M.sticks:
            items.append((part, -float(np.linalg.norm(CAM - pl.world(pts).mean(0))), pts, alb, w, "stick"))
        items.sort(key=lambda t: (t[0], t[1]))
        hull_pts = []
        outlined = False

        def outline():
            hp = hull(hull_pts) if hull_pts else []
            if len(hp) > 2:
                dark = self.lit((30, 30, 32), (0, 0.8, 0.5), shade=shade) * (1 - hz_k) + hor * hz_k
                L.line(hp + [hp[0]], dark, ink_w)
        for part, _, pts, col, ink, tag in items:
            if part > 0 and not outlined:
                outline()           # the hull's silhouette, before what stands on its deck
                outlined = True
            if tag == "stick":
                sc = pl.screen(pts)
                w = max(0.6 * self.s, ink * pl.kx)
                c = self.lit(col, (0, 0.8, 0.5), shade=shade) * (1 - hz_k) + hor * hz_k
                L.line([tuple(p) for p in sc], c, w)
                if R is not None:
                    R.line([tuple(p) for p in pl.screen(pts, mirror=True)], c * 0.55, w)
                continue
            sc = [tuple(p) for p in pl.screen(pts)]
            L.poly(sc, col)
            if ink:
                L.line(sc + [sc[0]], col * 0.5, ink_w)
                if len(sc) == 4 and tag != "sail":
                    # a hand-drawn touch: the top edge of an upright face catches the sky
                    k = min(range(4), key=lambda i: sc[i][1] + sc[(i + 1) % 4][1])
                    a, b = sc[k], sc[(k + 1) % 4]
                    if abs(b[0] - a[0]) > 2 * abs(b[1] - a[1]):
                        L.line([a, b], np.minimum(col * 1.2 + hor * 0.12, 255), ink_w, a=0.8)
            if part == 0:
                hull_pts += sc
            if R is not None:
                R.poly([tuple(p) for p in pl.screen(pts, mirror=True)], col * 0.55)
        if not outlined:
            outline()
        return hull_pts

    def side_line(self, M, pl, L, frac, col, w, x0=None, x1=None, dy=0.0):
        """A line along the seen side of a hull, at fraction frac of the way from the waterline to the deck
        edge (a rubbing strake, a boot top), from x0 to x1."""
        zs = 1 if pl.port_seen else -1
        pts = []
        for x, bd, bw, yd, xw in M.st:
            if (x0 is not None and x < x0) or (x1 is not None and x > x1):
                continue
            pts.append((xw + (x - xw) * frac, yd * frac + dy, zs * (bw + (bd - bw) * frac) * 1.01))
        if len(pts) > 1:
            L.line([tuple(p) for p in pl.screen(pts)], col, w)

    def on_side(self, pl, L, x0, x1, y0, y1, z, col, a=1.0):
        """A small panel (a window, a tyre, a name) on a face at local z, from x0..x1 and y0..y1 (metres)."""
        sc = pl.screen([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)])
        L.poly([tuple(p) for p in sc], col, a=a)

    def wake(self, pl, L, speed, length_m, beam_m, shade, k=1.0):
        """The boat's wake on the water: a bow wave down each side, two spreading arms and a churned band
        behind; stronger with speed (world units a minute)."""
        if speed <= 0.01 or k <= 0:
            return
        foam = self.lit((222, 230, 232), (0, 0.4, 1), shade=shade)
        hz_k = self.haze_of(pl.D)
        foam = foam * (1 - hz_k) + self.hor_col * hz_k
        a0 = min(1.0, speed / 0.6) * k
        half_l = length_m / 2
        reach = length_m * (1.5 + 3.0 * min(1.0, speed / 1.5))
        n = 9
        for zs in (1, -1):
            # the arm: from the bow quarter back and out at about 19 degrees
            arm = [(half_l * 0.55 - d, 0, zs * (beam_m * 0.5 + 0.36 * d)) for d in np.linspace(0, reach, n)]
            sc = [tuple(p) for p in pl.screen(arm)]
            for i in range(n - 1):
                L.line([sc[i], sc[i + 1]], foam, max(0.7 * self.s, 0.3 * pl.ky * (1 + i / 3)),
                       a=0.6 * a0 * (1 - i / (n - 1)) ** 1.2)
            # the bow wave, hugging the hull
            bw = [(half_l * 0.9 - d, 0.05, zs * beam_m * (0.15 + 0.35 * min(1, d / (0.3 * length_m)))) for d in np.linspace(0, 0.45 * length_m, 5)]
            L.line([tuple(p) for p in pl.screen(bw)], foam, max(0.6 * self.s, 0.35 * pl.ky), a=0.7 * a0)
        # the churned water astern: broken streaks that widen and fade
        ds = np.linspace(0, reach * 0.7, n)
        for zf in (-1.0, -0.4, 0.3, 0.9):
            for i in range(n - 1):
                if (i + int(3 * zf)) % 3 == 2:
                    continue          # gaps, so it reads as broken water and not a band
                w0 = beam_m * (0.3 + 0.25 * ds[i] / max(1.0, length_m)) * zf
                w1 = beam_m * (0.3 + 0.25 * ds[i + 1] / max(1.0, length_m)) * zf
                q = pl.screen([(-half_l - ds[i], 0, w0), (-half_l - ds[i + 1], 0, w1)])
                L.line([tuple(q[0]), tuple(q[1])], foam, max(0.6 * self.s, 0.22 * pl.ky), a=0.5 * a0 * (1 - i / (n - 1)) ** 1.5)

    def waterline(self, M, pl, L, shade, wash=0.25):
        """The wet dark line where the hull meets the water and a little lap of foam along it."""
        zs = 1 if pl.port_seen else -1
        pts = [(xw, 0.0, zs * bw * 1.02) for x, bd, bw, yd, xw in M.st]
        sc = [tuple(p) for p in pl.screen(pts)]
        dark = self.lit((24, 34, 36), (0, 0.6, 0.8), shade=shade)
        L.line(sc, dark, max(0.6 * self.s, 0.18 * pl.ky), a=0.7)
        if wash > 0:
            foam = self.lit((214, 224, 228), (0, 0.4, 1), shade=shade)
            sc2 = [(x, y + 0.25 * pl.ky) for x, y in sc]
            L.line(sc2, foam, max(0.5 * self.s, 0.12 * pl.ky), a=wash)

    def model_layers(self, pl, M, pad):
        P = np.concatenate([f[0] for f in M.faces] + [s[0] for s in M.sticks])
        sc = pl.screen(P)
        x0, y0 = sc.min(0) - pad
        x1, y1 = sc.max(0) + pad
        yw = float(pl.screen([(0, 0, 0)])[0, 1])
        L = Layer(self, x0, y0, x1, y1)
        R = Layer(self, x0, yw - 2 * self.s, x1, yw + (yw - y0) + pad)
        return L, R, yw

    # ----------------------------------------------------------- the ferry --
    def ferry_model(self):
        M = Model()
        black = (34, 36, 42)
        white, deck = (232, 232, 226), (92, 98, 92)
        st = [(-18.0, 4.1, 3.8, 2.4, -17.5), (-14.0, 4.5, 4.3, 2.4, -14.0), (-6.0, 4.5, 4.4, 2.5, -6.0),
              (2.0, 4.5, 4.4, 2.7, 2.0), (9.0, 4.3, 4.0, 3.0, 9.0), (13.0, 3.6, 2.9, 3.4, 12.6),
              (16.0, 2.2, 1.2, 3.8, 15.1), (18.2, 0.15, 0.0, 4.2, 16.4)]
        M.hull(st, black, deck)
        M.box(-9.5, 9.0, 2.5, 5.4, -4.25, 4.25, white, part=1, tag="lounge")
        M.box(-4.0, 6.0, 5.4, 7.6, -3.4, 3.4, white, part=2, tag="upper")
        M.box(3.6, 7.6, 7.6, 9.7, -3.0, 3.0, white, part=3, tag="bridge")
        M.box(-3.2, -1.0, 7.6, 10.0, -0.9, 0.9, (206, 160, 70), part=3, tag="funnel")
        M.box(-3.2, -1.0, 10.0, 10.9, -0.9, 0.9, (40, 38, 38), part=4, tag="funneltop")
        M.stick([(5.6, 9.7, 0), (5.6, 15.0, 0)], 0.35, (60, 60, 64), part=5)
        M.stick([(5.6, 13.4, -1.4), (5.6, 13.4, 1.4)], 0.22, (60, 60, 64), part=5)
        # the car deck's rails aft, and the bow's bulwark rail
        M.stick([(-17.8, 3.4, 0), (-9.5, 3.4, 0)], 0.12, (200, 200, 196), part=1)
        return M

    def ferry_now(self):
        if self.reference:
            return None
        if not hasattr(self, "_ferry_now"):
            self._ferry_now = self.day.sea.ferry_at(self.m)
        return self._ferry_now

    def ferry(self):
        f = self.ferry_now()
        if not f:
            return
        X, Z, h, speed, frac, back = f
        D = math.hypot(X, Z)
        # it slips into the island's harbour (or out of it) at the far end of its way
        far = 1 - sm(0.82, 0.985, frac)
        if far <= 0.02:
            return
        pl = Placed(self, X, Z, h, heel=0.0, lift=0.002 * math.sin(self.m * 1.3) / U)
        M = self.ferry_model()
        x, yw = pl.screen([(0, 0, 0)])[0]
        shade = self.local_shade(x, yw)
        L, R, yw = self.model_layers(pl, M, 8 * self.s + 0.5 * FERRY_L * pl.kx)
        on = self.lights_on
        self.wake(pl, L, speed, FERRY_L, FERRY_B, shade, k=1.0)
        self.model_draw(M, pl, L, R, shade=shade)
        zs = 4.26 if pl.port_seen else -4.26
        # windows: a row along the lounge and the upper deck, and the bridge's
        win = self.lit((52, 60, 72), (0, 0.6, 0.8), shade=shade)
        if on > 0:
            win = win * (1 - on) + np.array([255, 210, 140], np.float32) * on
        hz_k = self.haze_of(D)
        win = win * (1 - hz_k) + self.hor_col * hz_k
        for i in range(10):
            x0 = -8.6 + 1.7 * i
            self.on_side(pl, L, x0, x0 + 1.1, 3.6, 4.6, zs, win)
        for i in range(5):
            x0 = -3.3 + 1.8 * i
            self.on_side(pl, L, x0, x0 + 1.2, 6.2, 7.0, 3.41 if pl.port_seen else -3.41, win)
        self.on_side(pl, L, 4.0, 7.2, 8.5, 9.3, 3.01 if pl.port_seen else -3.01, win)
        # the boot top and the white line under the lounge
        red = self.lit((150, 40, 32), (0, 0.5, 0.85), shade=shade) * (1 - hz_k) + self.hor_col * hz_k
        self.side_line(M, pl, L, 0.12, red, max(0.6 * self.s, 0.3 * pl.ky))
        stripe = self.lit((214, 214, 210), (0, 0.5, 0.85), shade=shade) * (1 - hz_k) + self.hor_col * hz_k
        self.side_line(M, pl, L, 0.97, stripe, max(0.5 * self.s, 0.18 * pl.ky))
        self.waterline(M, pl, L, shade, wash=0.3)
        al = far
        if al < 1:
            rgb, a = L.arrays()
            self.over(L.y0, L.y1, L.x0, L.x1, rgb, a * al)
        else:
            L.composite()
        self.reflect(R)

    def ferry_lights(self):
        """The ferry's navigation lights after dark: masthead, the sidelight on the side we see (red to port,
        green to starboard) and the stern light from astern; drawn after the fog (render)."""
        on = self.lights_on
        f = self.ferry_now()
        if not f or on <= 0:
            return []
        X, Z, h, speed, frac, back = f
        far = 1 - sm(0.82, 0.985, frac)
        if far <= 0.02:
            return []
        pl = Placed(self, X, Z, h)
        to = heading_of(-X, -Z)
        rel = math.degrees(math.acos(max(-1.0, min(1.0, h[0] * to[0] + h[1] * to[1]))))
        out = []
        if rel < 112.5:
            out.append(((5.6, 15.1, 0), (255, 246, 226), 1.0))
            if pl.port_seen or rel < 6:
                out.append(((5.6, 9.2, 3.1), (255, 64, 52), 0.9))         # red to port
            if not pl.port_seen or rel < 6:
                out.append(((5.6, 9.2, -3.1), (70, 255, 120), 0.9))       # green to starboard
        else:
            out.append(((-17.8, 3.6, 0), (255, 246, 226), 0.9))
        lights = []
        for p, col, k in out:
            x, y = pl.screen([p])[0]
            yw = float(pl.screen([(p[0], 0, p[2])])[0, 1])
            lights.append((float(x), float(y), yw, col, k * on * far))
        return lights

    # -------------------------------------------------------------- yachts --
    HULLS = ((236, 234, 228), (40, 52, 84), (36, 72, 54), (150, 46, 40))
    SAILS = ((242, 238, 226), (242, 238, 226), (238, 232, 216), (178, 100, 62))

    def yacht_model(self, y, heel_side, boom):
        M = Model()
        hull_c = self.HULLS[y["hull"]]
        st = [(-5.0, 1.35, 1.0, 0.95, -4.7), (-3.5, 1.6, 1.35, 0.95, -3.5), (-1.0, 1.7, 1.45, 1.0, -1.0),
              (1.5, 1.6, 1.3, 1.05, 1.5), (3.3, 1.15, 0.75, 1.15, 3.2), (4.5, 0.55, 0.2, 1.25, 4.2), (5.1, 0.05, 0.0, 1.3, 4.5)]
        M.hull(st, hull_c, (190, 176, 150))
        M.box(-1.8, 1.6, 0.95, 1.5, -1.0, 1.0, (232, 228, 216), part=1)
        sail = self.SAILS[y["sails"]]
        side = heel_side                     # the leeward side (+1 port)
        b = math.radians(boom)
        clew = (0.9 - 4.6 * math.cos(b), 2.1, side * 4.6 * math.sin(b))
        mid = (0.9 - 2.6 * math.cos(b) - 0.35, 8.0, side * (2.6 * math.sin(b) + 0.25))
        M.face([(0.9, 2.1, 0), (0.9, 13.8, 0), mid, clew], sail, part=3, two=True, ink=True, tag="sail")
        bj = math.radians(min(70.0, boom * 0.9))
        jclew = (4.6 - 5.0 * math.cos(bj), 1.8, side * 5.0 * math.sin(bj))
        M.face([(4.6, 1.35, 0), (1.2, 11.6, 0), jclew], np.asarray(sail) * 0.97, part=4, two=True, ink=True, tag="sail")
        M.stick([(0.9, 1.5, 0), (0.9, 14.2, 0)], 0.16, (70, 64, 58), part=2)
        M.stick([(0.9, 2.1, 0), clew], 0.12, (70, 64, 58), part=2)
        return M

    def yachts(self):
        for y, (X, Z, h, speed) in self.day.sea.yachts_at(self.m):
            wx = self.wx
            th = math.radians(wx.wind_dir_deg)
            fx, fz = -math.sin(th), -math.cos(th)              # toward where the wind comes from (world x, z)
            p = (-h[1], h[0])
            from_port = fx * p[0] + fz * p[1] > 0
            twa = math.degrees(math.acos(max(-1.0, min(1.0, h[0] * fx + h[1] * fz))))
            boom = max(8.0, min(80.0, (twa - 30) * 0.6))
            side = -1 if from_port else 1
            heel = side * math.radians(min(18.0, 1.6 * wx.wind_ms * math.sin(math.radians(twa)) + 2))
            pl = Placed(self, X, Z, h, heel=heel)
            M = self.yacht_model(y, side, boom)
            x, yw = pl.screen([(0, 0, 0)])[0]
            shade = self.local_shade(x, yw)
            L, R, yw = self.model_layers(pl, M, 6 * self.s + 6 * pl.kx)
            self.wake(pl, L, speed * 4, 10.0, 3.3, shade, k=0.8)
            self.model_draw(M, pl, L, R, shade=shade)
            self.waterline(M, pl, L, shade, wash=0.3)
            L.composite()
            self.reflect(R)

    # ---------------------------------------------------------- creel boat --
    def creel_model(self, hauling, pot_up):
        M = Model()
        st = [(-3.75, 1.25, 1.12, 1.05, -3.68), (-2.6, 1.38, 1.27, 1.05, -2.6), (-1.0, 1.42, 1.31, 1.1, -1.0),
              (0.6, 1.42, 1.3, 1.18, 0.6), (1.9, 1.3, 1.1, 1.3, 1.9), (2.9, 0.95, 0.62, 1.45, 2.8),
              (3.5, 0.5, 0.14, 1.6, 3.2), (3.85, 0.05, 0.0, 1.72, 3.35)]
        M.hull(st, (132, 42, 34), (128, 120, 104))
        wh = (232, 230, 222)
        # the wheelhouse, its windscreen raked forward, under a roof with a little overhang
        for zs in (1, -1):
            M.face([(0.3, 1.15, zs * 0.88), (2.1, 1.15, zs * 0.88), (2.1, 2.1, zs * 0.88), (2.3, 2.95, zs * 0.88), (0.3, 2.95, zs * 0.88)],
                   wh, part=1, hint=(0, 0, zs), tag="wheelhouse")
        M.face([(2.1, 1.15, -0.88), (2.1, 1.15, 0.88), (2.1, 2.1, 0.88), (2.1, 2.1, -0.88)], wh, part=1, hint=(1, 0, 0))
        M.face([(2.1, 2.1, -0.88), (2.1, 2.1, 0.88), (2.3, 2.95, 0.88), (2.3, 2.95, -0.88)], (70, 84, 98), part=1, hint=(1, 0.2, 0), tag="screen")
        M.face([(0.3, 1.15, -0.88), (0.3, 1.15, 0.88), (0.3, 2.95, 0.88), (0.3, 2.95, -0.88)], wh, part=1, hint=(-1, 0, 0))
        M.box(0.15, 2.45, 2.95, 3.08, -0.97, 0.97, (190, 190, 186), part=2)
        for i, (cx, cz, tier) in enumerate(((-3.1, -0.55, 0), (-3.1, 0.55, 0), (-2.4, -0.55, 0), (-2.4, 0.55, 0),
                                             (-1.7, -0.55, 0), (-1.7, 0.55, 0), (-2.75, 0.0, 1), (-2.05, -0.3, 1))):
            y0 = 1.06 + 0.42 * tier
            M.box(cx - 0.32, cx + 0.32, y0, y0 + 0.4, cz - 0.42, cz + 0.42, (58 + 6 * (i % 3), 66, 60), part=1 + tier, tag="creel")
        M.stick([(1.0, 3.12, 0), (1.0, 5.1, 0)], 0.09, (70, 70, 74), part=3)
        M.stick([(1.0, 4.6, -0.4), (1.0, 4.6, 0.4)], 0.07, (70, 70, 74), part=3)
        # the hauler's davit on the starboard bow
        M.stick([(2.55, 1.3, -1.1), (2.55, 2.55, -1.1), (2.7, 2.5, -1.55)], 0.1, (150, 150, 150), part=3)
        if hauling:
            M.stick([(2.7, 2.5, -1.55), (2.8, 0.0, -1.85)], 0.04, (200, 190, 150), part=3)
        if pot_up:
            M.box(2.45, 3.05, 1.55, 2.05, -1.95, -1.45, (56, 60, 52), part=4, tag="pot")
        return M

    def creel_pose(self):
        """Where the creel boat is now: (X, Z, heading, speed units/min, state) or None."""
        c = self.day.sea.creel_at(self.m)
        if not c:
            return None
        what, pot, u, k = c
        floats = {m[1]: m for m in self.mark_positions() if m[0] == "pot"}
        sx, sz = self.set_on()
        n = math.hypot(sx, sz)
        h_set = heading_of(-sx, -sz) if n > 0.06 else (-1.0, 0.0)
        # it lies head to the stream and the wind, but never far off broadside to us (held by the hauler)
        X4, Z4, _ = sea_point(0.69, 0.75)
        side_on = math.atan2(-X4, Z4)                      # across our line of sight to the string
        a = math.atan2(h_set[1], h_set[0])
        base = side_on if math.cos(a - side_on) >= 0 else side_on + math.pi
        d = (a - base + math.pi) % (2 * math.pi) - math.pi
        d = max(-math.radians(30), min(math.radians(30), d))
        h_set = (math.cos(base + d), math.sin(base + d))
        hx, hz = h_set
        px, pz = -hz, hx
        W, H = self.W, self.H

        def at_pot(i):
            _, _, x, y, _, _, _ = floats[i]
            Xf, Zf, _ = sea_point(x / W, y / H)
            return Xf - (2.7 * hx - 1.75 * px) / U, Zf - (2.7 * hz - 1.75 * pz) / U
        Xs, Zs, _ = sea_point(*CREEL_FROM)

        def lerp_h(a, b, t):
            ang = math.atan2(a[1], a[0])
            d = (math.atan2(b[1], b[0]) - ang + math.pi) % (2 * math.pi) - math.pi
            ang += d * t
            return math.cos(ang), math.sin(ang)
        def along(pts, t):
            pos, tan = catmull(pts, min(1.0, max(0.0, t)))
            return float(pos[0]), float(pos[1]), heading_of(float(tan[0]), float(tan[1]))
        if what == "come":
            way = [(Xs, Zs)] + [sea_point(*q)[:2] for q in CREEL_IN] + [at_pot(0)]
            t = 1 - (1 - u) ** 1.6
            X, Z, h_mv = along(way, t)
            return X, Z, lerp_h(h_mv, h_set, smoothstep((u - 0.75) / 0.25)), 0.1 * (1 - t) + 0.02, what
        if what in ("alongside", "haul", "set"):
            X, Z = at_pot(pot)
            if what == "alongside":
                X, Z = X - 0.06 * (1 - u) * hx, Z - 0.06 * (1 - u) * hz
            return X, Z, h_set, 0.0 if what != "alongside" else 0.02, what
        if what == "next":
            Xa, Za = at_pot(pot)
            Xb, Zb = at_pot(pot + 1)
            t = smoothstep(u)
            return Xa + (Xb - Xa) * t, Za + (Zb - Za) * t, h_set, 0.03, what
        way = [at_pot(4)] + [sea_point(*q)[:2] for q in CREEL_OUT] + [(Xs, Zs)]
        if what == "turn":
            X, Z = at_pot(4)
            return X, Z, lerp_h(h_set, along(way, 0.02)[2], smoothstep(u)), 0.02, what
        if what == "go":
            t = u ** 1.25
            X, Z, h_mv = along(way, t)
            return X, Z, h_mv, 0.04 + 0.08 * t, what
        return None

    def creel_y(self):
        p = self.creel_pose()
        if not p:
            return None
        x, y = self.proj(p[0], 0, p[1])
        return float(y) / self.H

    def creel_boat(self):
        p = self.creel_pose()
        if not p:
            return
        X, Z, h, speed, what = p
        c = self.day.sea.creel_at(self.m)
        hauling = what == "haul"
        pot_up = hauling and c[2] > 0.55
        pl = Placed(self, X, Z, h, heel=math.radians(-2.5 if hauling else 0.0), lift=0.0)
        M = self.creel_model(hauling, pot_up)
        x, yw = pl.screen([(0, 0, 0)])[0]
        shade = self.local_shade(x, yw)
        L, R, yw = self.model_layers(pl, M, 10 * self.s + 4 * pl.kx)
        self.wake(pl, L, speed * 2.5, CREEL_L, CREEL_B, shade, k=1.0)
        if what == "set" and c[2] < 0.7:
            # the pot going back over the side: a splash and a ring
            sp = pl.screen([(-0.5, 0, -1.9 if not pl.port_seen else -1.9)])[0]
            foam = self.lit((226, 232, 234), (0, 0.4, 1), shade=shade)
            L.ellipse(sp[0], sp[1], 0.9 * pl.kx, 0.25 * pl.ky, foam, a=0.6)
            L.line([(sp[0] - 0.2 * pl.kx, sp[1]), (sp[0], sp[1] - 0.7 * pl.ky), (sp[0] + 0.2 * pl.kx, sp[1])], foam, max(0.6 * self.s, 0.12 * pl.kx), a=0.55)
        self.model_draw(M, pl, L, R, shade=shade)
        zs = 1 if pl.port_seen else -1
        # the wheelhouse's windows (sky in the glass), tyres hung over the side, a white rubbing strake,
        # black below the waterline, and the boat's number on the bow
        glass = self.lit((70, 84, 98), (0, 0.6, 0.8), shade=shade) + self.hor_col * 0.12
        self.on_side(pl, L, 1.15, 1.95, 2.15, 2.75, zs * 0.885, glass)
        self.on_side(pl, L, 0.45, 0.95, 2.15, 2.75, zs * 0.885, glass)
        to = heading_of(-X, -Z)
        if h[0] * to[0] + h[1] * to[1] > 0.05:
            mid = pl.screen([(2.12, 2.12, 0), (2.29, 2.93, 0)])
            L.line([tuple(p_) for p_ in mid], self.lit((232, 230, 222), (1, 0, 0.3), shade=shade), max(0.5, 0.08 * pl.kx))
        if h[0] * to[0] + h[1] * to[1] < 0.2:
            # the door at the back of the wheelhouse
            door = pl.screen([(0.299, 1.2, -0.35), (0.299, 1.2, 0.35), (0.299, 2.6, 0.35), (0.299, 2.6, -0.35)])
            L.poly([tuple(p_) for p_ in door], self.lit((150, 150, 146), (-1, 0, 0.3), shade=shade))
        # a lifebuoy on the wheelhouse side
        lb = pl.screen([(0.75, 1.9, zs * 0.9)])[0]
        L.ellipse(lb[0], lb[1], 0.2 * pl.kx, 0.2 * pl.ky, self.lit((226, 92, 40), (0, 0.6, 0.8), shade=shade))
        L.ellipse(lb[0], lb[1], 0.09 * pl.kx, 0.09 * pl.ky, self.lit((232, 230, 222), (0, 0.6, 0.8), shade=shade) * 0.9)
        # rust weeping from the scuppers, down the topsides
        rust = self.lit((96, 46, 30), (0, 0.6, 0.8), shade=shade)
        for rx in (-3.0, -1.9, -0.2, 1.4):
            a_ = pl.screen([(rx, 1.0, zs * 1.36), (rx + 0.05, 0.45, zs * 1.3)])
            L.line([tuple(a_[0]), tuple(a_[1])], rust, max(0.5, 0.07 * pl.kx), a=0.45)
        strake = self.lit((226, 224, 214), (0, 0.6, 0.8), shade=shade)
        self.side_line(M, pl, L, 0.93, strake, max(0.6 * self.s, 0.11 * pl.ky))
        boot = self.lit((26, 26, 28), (0, 0.5, 0.85), shade=shade)
        self.side_line(M, pl, L, 0.07, boot, max(0.6 * self.s, 0.14 * pl.ky))
        tyre = self.lit((26, 26, 28), (0, 0.6, 0.8), shade=shade)
        rim = self.lit((70, 70, 72), (0, 0.3, 0.95), shade=shade)
        for tx in (-2.2, -0.4):
            sc = pl.screen([(tx, 0.98, zs * 1.47)])[0]
            top = pl.screen([(tx, 1.2, zs * 1.42)])[0]
            L.line([tuple(top), tuple(sc)], tyre, max(0.4, 0.04 * pl.kx))
            L.ellipse(sc[0], sc[1], 0.2 * pl.kx, 0.22 * pl.ky, tyre)
            L.ellipse(sc[0], sc[1] - 0.06 * pl.ky, 0.12 * pl.kx, 0.08 * pl.ky, rim)
        num = self.lit((232, 230, 222), (0, 0.6, 0.8), shade=shade)
        for j in range(3):
            self.on_side(pl, L, 2.25 + 0.22 * j, 2.38 + 0.22 * j, 0.95, 1.25, zs * 1.12, num, a=0.85)
        self.waterline(M, pl, L, shade, wash=0.35 if speed > 0 else 0.2)
        L.composite()
        self.reflect(R)

    # ================================================================ seals --
    def skerry_px_per_m(self):
        _, _, D = sea_point(0.785, 0.686)
        return self.W / math.radians(AZ_SPAN) / D / U

    def seal_colours(self, which, x, y, shade, wet):
        if which == 0:             # the pale cow: silvery cream, blotched dark
            back, belly, spot = (186, 178, 160), (210, 204, 188), (96, 88, 80)
        else:                      # the others grey or brownish, darker when wet
            back, belly, spot = ((86, 90, 100), (168, 162, 150), (56, 58, 66)) if which % 2 else ((104, 96, 88), (176, 166, 148), (66, 60, 56))
        k = 1 - 0.35 * wet
        top = self.lit(np.array(back) * k, (0, 0.35, 0.94), shade=shade)
        side = self.lit(np.array(back) * k, (0, 0.85, 0.45), shade=shade)
        under = self.lit(np.array(belly) * k, (0, 0.6, -0.4), shade=shade)
        sp = self.lit(np.array(spot) * k, (0, 0.7, 0.6), shade=shade)
        return top, side, under, sp

    def draw_seal(self, L, x, y, M, f, which, pose, shade, wet, lean=0.0):
        """A grey seal hauled out. lean: how thin the pale cow still is, back from nursing her pup (0: as ever)."""
        top, side, under, spot = self.seal_colours(which, x, y, shade, wet)
        sp = Sprite(x, y, M, f)
        head_up = {"flat": 0.0, "banana": 0.35, "head": 0.55, "scratch": 0.15}[pose]
        tail_up = {"flat": 0.0, "banana": 0.32, "head": 0.05, "scratch": 0.05}[pose]
        # the body: a long, heavy spindle lying along the rock
        body = [(-0.95, 0.06 + 0.2 * tail_up), (-0.7, 0.2 + 0.1 * tail_up), (-0.3, 0.36), (0.15, 0.42), (0.5, 0.36),
                (0.72, 0.26 + 0.25 * head_up), (0.78, 0.0), (0.2, -0.02), (-0.4, 0.0), (-0.85, 0.0)]
        back = [(-0.7, 0.18 + 0.1 * tail_up), (-0.3, 0.34), (0.15, 0.4), (0.5, 0.34), (0.3, 0.3), (-0.2, 0.28)]
        if lean > 0:                 # her back sunk and her neck shown, the fat she nursed on gone
            k = 1 - 0.24 * lean
            body = [(u, v * k) if -0.75 < u < 0.6 else (u, v) for u, v in body]
            back = [(u, v * k) for u, v in back]
        sp.poly(body, side)
        sp.poly([(-0.6, 0.02), (0.6, 0.03), (0.7, 0.12), (-0.5, 0.12)], under, edge=False)
        sp.poly(back, top, edge=False)
        # hind flippers, a fan at the tail
        tx, ty = -0.95, 0.06 + 0.2 * tail_up
        sp.poly([(tx + 0.05, ty), (tx - 0.3, ty + 0.12 + 0.25 * tail_up), (tx - 0.22, ty - 0.02 + 0.2 * tail_up)], side)
        sp.poly([(tx + 0.05, ty - 0.03), (tx - 0.28, ty - 0.06 + 0.15 * tail_up), (tx - 0.12, ty - 0.1)], side)
        # the head, on a thick neck, raised by the pose
        hx, hy = 0.82 + 0.05 * head_up, 0.22 + 0.45 * head_up
        sp.ell(hx, hy, 0.17, 0.14, side)
        sp.poly([(hx + 0.08, hy + 0.08), (hx + 0.3, hy + 0.01), (hx + 0.29, hy - 0.08), (hx + 0.05, hy - 0.11)], side)
        sp.ell(hx + 0.04, hy + 0.04, 0.03, 0.03, (14, 14, 16), edge=False)
        # the fore flipper
        if pose == "scratch":
            sp.poly([(0.42, 0.18), (0.6, 0.45), (0.52, 0.48), (0.36, 0.22)], side)
        else:
            sp.poly([(0.38, 0.12), (0.58, 0.02), (0.5, -0.01), (0.32, 0.07)], under)
        # the coat: a grey seal's blotches
        r = np.random.default_rng([97, which])
        for _ in range(7 if which == 0 else 4):
            u_, v_ = r.uniform(-0.6, 0.55), r.uniform(0.12, 0.3)
            sp.ell(u_, v_, r.uniform(0.04, 0.09), r.uniform(0.025, 0.05), spot, edge=False)
        # the sky's sheen along the back: bright when wet, a soft gleam when dry
        sheen = top * (0.75 - 0.2 * wet) + self.hor_col * (0.3 + 0.3 * wet)
        ridge = [(-0.55, 0.3 + 0.08 * tail_up), (-0.1, 0.39), (0.35, 0.37), (0.62, 0.3 + 0.2 * head_up)]
        if lean > 0:
            ridge = [(u, v * k) if u < 0.6 else (u, v) for u, v in ridge]
        sp.limb(ridge, 0.04, sheen, edge=False)
        sp.draw(L, max(0.45, 0.7 * self.s))

    def skerry_life(self):
        """The seals hauled out on the skerry, and the cormorant on its top knob; drawn just after the rock."""
        if self.reference:
            return
        sea = self.day.sea
        wl = self.water_level()
        seals = [s for s in sea.seals_at(self.m, wl) if s[1] == "rock"]
        corm = sea.cormorant_at(self.m, wl)
        if not seals and not corm:
            return
        Mp = self.skerry_px_per_m() * 1.9
        things = []
        for j, _, pose, f, a, b in seals:
            X, Z, h = skerry_point(a, b)
            x, y = self.proj(X, h, Z)
            things.append((b, "seal", float(x), float(y), j, pose, f))
        if corm:
            X, Z, h = skerry_point(*CORMORANT_KNOB)
            x, y = self.proj(X, h, Z)
            things.append((CORMORANT_KNOB[1], "corm", float(x), float(y), 0, corm[0], corm[1]))
        xs = [t[2] for t in things]
        ys = [t[3] for t in things]
        L = Layer(self, min(xs) - 3 * Mp, min(ys) - 2.0 * Mp, max(xs) + 3 * Mp, max(ys) + 0.6 * Mp)
        shade = self.local_shade(float(np.mean(xs)), float(np.mean(ys)))
        for b, kind, x, y, j, pose, f in sorted(things, key=lambda t: -t[0]):
            if kind == "seal":
                # still wet just after it has hauled out (the tide has dropped but a little below its spot)
                _, _, h = skerry_point(*SEAL_SPOTS[j])
                wet = max(0.0, 1 - (h - wl) / 0.03)
                pale = sea.pale(self.m) if j == 0 else None
                self.draw_seal(L, x, y + 0.04 * Mp, Mp, f, j, pose, shade, wet, lean=pale["lean"] if pale else 0.0)
            else:
                self.draw_cormorant(L, x, y + 0.02 * Mp, Mp, f, pose, shade)
        L.composite()

    def seal_heads(self):
        """Seals' heads in the water: waiting for the rock to dry, just slipped off it, or out on their own."""
        sea = self.day.sea
        wl = self.water_level()
        heads = []
        for j, where, pose, f, a, b in sea.seals_at(self.m, wl):
            if where != "water":
                continue
            X, Z, h = skerry_point(a, b)
            # off the rock's near edge, a body length or so out
            X0, Z0, D0 = sea_point(0.785, 0.686)
            dx, dz = X - X0, Z - Z0
            n = math.hypot(dx, dz) or 1
            ang = unit(j, 41, int(self.m) // 3) * 0.6 - 0.3
            X, Z = X + (dx / n * math.cos(ang) - dz / n * math.sin(ang)) * 0.12, Z + (dz / n * math.cos(ang) + dx / n * math.sin(ang)) * 0.12 - 0.08
            heads.append((j, X, Z, f, 0))
        sw = sea.seal_swim_at(self.m, wl)
        if sw:
            j, X, Z, seed, k = sw
            X += 0.05 * math.sin(k * 0.9 + seed % 7)
            heads.append((j, X, Z, 1 if seed % 2 else -1, k))
        return heads

    def seal_heads_y(self):
        hs = self.seal_heads() if not self.reference else []
        return [(float(self.proj(X, 0, Z)[1]) / self.H, (j, X, Z, f, k)) for j, X, Z, f, k in hs]

    def draw_seal_head(self, head):
        j, X, Z, f, k = head
        D = math.hypot(X, Z)
        M = self.W / math.radians(AZ_SPAN) / D / U * 2.0
        x, y = self.proj(X, 0, Z)
        x, y = float(x), float(y)
        shade = self.local_shade(x, y)
        top, side, under, spot = self.seal_colours(j, x, y, shade, 1.0)
        L = Layer(self, x - 0.8 * M, y - 0.7 * M, x + 0.8 * M, y + 0.3 * M)
        R = Layer(self, x - 0.8 * M, y - 1, x + 0.8 * M, y + 0.7 * M)
        foam = self.lit((214, 222, 226), (0, 0.4, 1), shade=shade)
        L.ellipse(x, y + 0.02 * M, 0.42 * M, 0.07 * M, foam, a=0.25)
        sp = Sprite(x, y, M, f)
        b = 0.02 * math.sin(self.m * 1.9 + j)
        # the head up out of the water, looking about: a round crown, a long muzzle, a wet gleam on top
        head = [(-0.17, 0.0), (-0.18, 0.18 + b), (-0.12, 0.3 + b), (0.0, 0.36 + b), (0.12, 0.34 + b), (0.2, 0.28 + b),
                (0.33, 0.24 + b), (0.36, 0.19 + b), (0.3, 0.14 + b), (0.12, 0.1 + b), (0.1, 0.0)]
        sp.poly(head, side)
        sp.poly([(-0.1, 0.29 + b), (0.0, 0.335 + b), (0.1, 0.32 + b), (0.02, 0.3 + b)], top * 0.7 + self.hor_col * 0.25, edge=False)
        sp.poly([(0.14, 0.13 + b), (0.3, 0.15 + b), (0.34, 0.19 + b), (0.2, 0.2 + b)], under, edge=False)
        sp.ell(0.1, 0.26 + b, 0.028, 0.028, (12, 12, 14), edge=False)
        sp.ell(0.33, 0.21 + b, 0.015, 0.012, (20, 20, 22), edge=False)
        sp.draw(L, max(0.45, 0.65 * self.s))
        mr = Sprite(x, y, M, f)
        mr.poly([(p[0], -p[1]) for p in head], side * 0.55, edge=False)
        mr.draw(R, 0)
        L.composite()
        self.reflect(R)

    # ------------------------------------------------------------ cormorant --
    def draw_cormorant(self, L, x, y, M, f, pose, shade):
        sp = Sprite(x, y, M, f)
        dark = self.lit((32, 32, 28), (0, 0.85, 0.45), shade=shade)
        sheen = self.lit((70, 66, 48), (0, 0.4, 0.9), shade=shade)
        chin = self.lit((214, 208, 196), (0, 0.85, 0.45), shade=shade)
        face = self.lit((206, 164, 64), (0, 0.85, 0.45), shade=shade)
        sp.limb([(-0.02, 0.0), (-0.03, 0.1)], 0.035, dark)
        sp.limb([(0.04, 0.0), (0.05, 0.1)], 0.035, dark)
        if pose == "spread":
            # held out to dry: both wings open, seen from the front, a little drooped at the tips
            for e in (-1, 1):
                ww = [(0.0, 0.62), (e * 0.22, 0.68), (e * 0.5, 0.63), (e * 0.62, 0.48), (e * 0.6, 0.3),
                      (e * 0.5, 0.33), (e * 0.44, 0.24), (e * 0.32, 0.3), (e * 0.24, 0.22), (e * 0.1, 0.36), (0.0, 0.4)]
                sp.poly(ww, dark)
                for k in range(3):
                    t = 0.3 + 0.18 * k
                    sp.limb([(e * t, 0.6 - 0.04 * k), (e * (t + 0.1), 0.42 - 0.05 * k)], 0.02, sheen, edge=False)
        sp.poly([(-0.07, 0.1), (0.1, 0.1), (0.12, 0.42), (0.06, 0.6), (-0.08, 0.6), (-0.11, 0.4)], dark)
        sp.poly([(-0.1, 0.16), (-0.2, 0.0), (-0.07, 0.1)], dark)          # the stiff tail, down on the rock
        if pose == "fold":
            sp.poly([(-0.1, 0.55), (-0.13, 0.3), (-0.05, 0.14), (0.05, 0.3)], sheen, edge=False)
        if pose == "preen":
            hx, hy = 0.1, 0.48
            sp.limb([(0.02, 0.58), (0.1, 0.56), (hx, hy)], 0.07, dark)
            sp.ell(hx, hy, 0.065, 0.055, dark)
            sp.poly([(hx + 0.02, hy - 0.02), (hx + 0.06, hy - 0.02), (hx + 0.0, hy - 0.16)], self.lit((60, 56, 50), (0, 0.8, 0.5), shade=shade))
            sp.draw(L, max(0.45, 0.6 * self.s))
            return
        # the neck in its S, the head in profile, the hooked bill, the pale chin and the yellow face
        sp.limb([(0.0, 0.58), (-0.02, 0.72), (0.04, 0.82)], 0.07, dark)
        hx, hy = 0.06, 0.86
        sp.ell(hx, hy, 0.07, 0.06, dark)
        sp.poly([(hx + 0.05, hy + 0.01), (hx + 0.24, hy - 0.01), (hx + 0.25, hy - 0.035), (hx + 0.05, hy - 0.03)],
                self.lit((70, 64, 54), (0, 0.8, 0.5), shade=shade))
        sp.ell(hx + 0.03, hy - 0.035, 0.04, 0.025, chin, edge=False)
        sp.ell(hx + 0.05, hy - 0.005, 0.02, 0.015, face, edge=False)
        sp.ell(hx + 0.015, hy + 0.015, 0.012, 0.012, (180, 200, 120), edge=False)
        sp.draw(L, max(0.45, 0.6 * self.s))

    # ============================================================ dolphins --
    def dolphin_pod(self):
        """The pod's dolphins now: [(X, Z, pose, facing, i)] for those at the surface."""
        pod = self.day.sea.dolphins_at(self.m)
        if not pod:
            return []
        cx = self.day.sea.dolphin_x(pod, self.m)
        f = -1 if not pod["back"] else 1           # which way along the bay they go (screen sense)
        out = []
        for i in range(pod["n"]):
            r = np.random.default_rng([pod["seed"], i])
            dx, dy = r.uniform(-0.045, 0.045), r.uniform(-0.012, 0.012)
            q = unit(pod["seed"], i, self.m, 3)
            pose = "arch" if q < 0.3 else "fin" if q < 0.48 else "rise" if q < 0.6 else "leap" if q < 0.615 else None
            if pose is None:
                continue
            xn = cx + dx + 0.006 * math.sin(self.m * 0.7 + i)
            yn = 0.656 + dy
            X, Z, _ = sea_point(xn, yn)
            out.append((X, Z, pose, f, i))
        return out

    def dolphins_y(self):
        pod = [] if self.reference else self.dolphin_pod()
        return (float(np.mean([self.proj(X, 0, Z)[1] for X, Z, *_ in pod])) / self.H) if pod else None

    def dolphins(self):
        pod = self.dolphin_pod()
        if not pod:
            return
        for X, Z, pose, f, i in sorted(pod, key=lambda d: -math.hypot(d[0], d[1])):
            D = math.hypot(X, Z)
            M = self.W / math.radians(AZ_SPAN) / D / U * 2.0
            x, y = self.proj(X, 0, Z)
            x, y = float(x), float(y)
            shade = self.local_shade(x, y)
            grey = self.lit((70, 78, 88), (0, 0.6, 0.8), shade=shade)
            back = self.lit((54, 60, 70), (0, 0.3, 0.95), shade=shade)
            pale = self.lit((150, 156, 164), (0, 0.85, 0.4), shade=shade)
            foam = self.lit((220, 228, 232), (0, 0.4, 1), shade=shade)
            L = Layer(self, x - 1.6 * M, y - 1.6 * M, x + 1.6 * M, y + 0.4 * M)
            R = Layer(self, x - 1.6 * M, y - 1, x + 1.6 * M, y + 0.9 * M)
            sp = Sprite(x, y, M, f)
            mr = Sprite(x, y, M, f)
            # the dorsal fin: tall and swept back, its trailing edge hollowed (falcate)
            FIN = [(0.2, 0.0), (0.1, 0.16), (-0.06, 0.32), (-0.3, 0.44), (-0.22, 0.31), (-0.17, 0.15), (-0.2, 0.0)]
            if pose == "arch":
                body = [(-0.85, -0.02), (-0.55, 0.11), (-0.1, 0.19), (0.3, 0.16), (0.65, 0.06), (0.85, -0.02)]
                fin = [(x_, y_ + 0.17) for x_, y_ in FIN]
            elif pose == "fin":
                body = [(-0.5, -0.02), (-0.25, 0.07), (0.15, 0.08), (0.45, -0.02)]
                fin = [(x_ - 0.05, y_ + 0.06) for x_, y_ in FIN]
            elif pose == "rise":
                body = [(0.0, -0.02), (0.25, 0.12), (0.6, 0.2), (0.88, 0.1), (0.98, 0.04), (0.9, -0.02)]
                fin = None
            else:      # a leap, clear of the water
                with sp.turn(18, 0.0, 0.6):
                    sp.poly([(-0.8, 0.5), (-0.4, 0.68), (0.2, 0.74), (0.7, 0.64), (0.95, 0.56), (0.7, 0.48), (0.0, 0.46), (-0.6, 0.44)], grey)
                    sp.poly([(-0.1, 0.72), (0.2, 0.72), (-0.15, 0.95)], back)
                    sp.poly([(-0.8, 0.5), (-1.05, 0.66), (-0.95, 0.48), (-1.05, 0.34)], grey)
                    sp.poly([(-0.4, 0.47), (0.6, 0.5), (0.2, 0.55), (-0.3, 0.52)], pale, edge=False)
                L.ellipse(x - f * 0.4 * M, y + 0.02 * M, 0.7 * M, 0.1 * M, foam, a=0.5)
                for k in range(5):
                    sx = x - f * (0.2 + 0.15 * k) * M
                    L.line([(sx, y), (sx - f * 0.05 * M, y - (0.25 + 0.1 * (k % 2)) * M)], foam, max(0.5, 0.05 * M), a=0.5)
                body, fin = None, None
            if body:
                sp.poly(body, grey)
                sp.poly([(p[0], p[1] * 0.7) for p in body[1:-1]] + [(body[-1][0], 0.0), (body[0][0], 0.0)], back, edge=False)
                if fin:
                    sp.poly(fin, back)
                gleam = back * 0.75 + self.hor_col * 0.22 + self.sun_col * 25 * self.sun_str
                sp.limb([body[1], body[2], body[3]], 0.02, gleam, edge=False)
                mr.poly([(p[0], -p[1]) for p in body], grey * 0.5, edge=False)
                if pose == "rise":
                    # the blow: a soft puff from the blowhole
                    L.ellipse(x + f * 0.55 * M, y - 0.42 * M, 0.12 * M, 0.16 * M, foam, a=0.35)
                L.ellipse(x, y + 0.01 * M, 0.85 * M if pose == "arch" else 0.55 * M, 0.07 * M, foam, a=0.45)
            sp.draw(L, max(0.45, 0.6 * self.s))
            mr.draw(R, 0)
            L.composite()
            self.reflect(R)

    # ============================================================= gannets --
    def gannet_birds(self):
        """The gannets of the bouts now: [(X, Y, Z, pose, i, seed)] in world units; pose fly, dive, splash,
        ring or sit."""
        out = []
        for b in self.day.sea.gannets_at(self.m):
            k = self.m - b["m0"]
            for i in range(b["n"]):
                r = np.random.default_rng([b["seed"], i])
                rad, hgt, ph, sp = r.uniform(0.6, 2.4), r.uniform(0.8, 2.0), r.uniform(0, 6.3), r.uniform(0.4, 0.9) * r.choice([-1, 1])
                q = unit(b["seed"], i, self.m, 5)
                prev = unit(b["seed"], i, self.m - 1, 5)
                ang = ph + sp * k
                X = b["X"] + rad * math.cos(ang)
                Z = b["Z"] + 0.6 * rad * math.sin(ang)
                if prev < 0.14:           # it went in last minute: a ring of foam, or it sits on the water
                    out.append((X, 0.0, Z, "ring" if q < 0.6 else "sit", i, b["seed"]))
                elif q < 0.08:
                    out.append((X, hgt * (0.25 + 0.4 * unit(b["seed"], i, self.m, 6)), Z, "dive", i, b["seed"]))
                elif q < 0.14:
                    out.append((X, 0.0, Z, "splash", i, b["seed"]))
                else:
                    out.append((X, hgt, Z, "fly", i, b["seed"]))
        return out

    def gannets(self):
        birds = self.gannet_birds()
        if not birds:
            return
        sun = max(0.0, float(self.sunv[2])) * self.sun_str
        for X, Y, Z, pose, i, seed in sorted(birds, key=lambda b: -math.hypot(b[0], b[2])):
            D = math.hypot(X, Z)
            M = self.W / math.radians(AZ_SPAN) / D / U * 3.0
            x, y = self.proj(X, Y, Z)
            x, y = float(x), float(y)
            shade = self.local_shade(x, float(self.proj(X, 0, Z)[1]))
            hz_k = self.haze_of(D)
            white = (np.array([240, 240, 236], np.float32) * (self.amb * 1.1 + self.bounce * 0.4 + self.sun_col * (0.25 * self.sun_str + 0.6 * sun)))
            white = white * (1 - hz_k) + self.hor_col * hz_k
            black = np.array([30, 30, 34], np.float32) * (0.5 + 0.5 * self.amb.mean()) * (1 - hz_k) + self.hor_col * hz_k
            L = Layer(self, x - 2.2 * M, y - 2.2 * M, x + 2.2 * M, y + 1.2 * M)
            if pose == "fly":
                # long, narrow, straight wings with black tips, a pointed tail and a spear of a bill; the span
                # foreshortens as the bird turns on its circle, and the wings beat now and then
                a = (self.m * 0.9 + i * 1.7) % (2 * math.pi)
                fwd = 1 if math.cos(a) >= 0 else -1
                span = 0.92 * (0.4 + 0.6 * abs(math.sin(a)))
                beat = 0.12 * math.sin(self.m * 2.3 + i * 1.3)
                P = lambda u, v: (x + u * M, y - v * M)
                for e in (-1, 1):
                    root_f, root_b = P(0.12 * fwd + e * 0.04, 0.0), P(-0.08 * fwd + e * 0.04, 0.0)
                    wrist = P(e * span * 0.45 + 0.08 * fwd, 0.1 + beat)
                    tip = P(e * span - 0.12 * fwd, 0.04 + 1.6 * beat)
                    back = P(e * span * 0.45 - 0.06 * fwd, 0.06 + beat)
                    L.poly([root_f, wrist, tip, back, root_b], white)
                    t0 = (wrist[0] + (tip[0] - wrist[0]) * 0.45, wrist[1] + (tip[1] - wrist[1]) * 0.45)
                    t1 = (back[0] + (tip[0] - back[0]) * 0.45, back[1] + (tip[1] - back[1]) * 0.45)
                    L.poly([t0, tip, t1], black)
                L.poly([P(-0.5 * fwd, 0.0), P(-0.1 * fwd, 0.07), P(0.32 * fwd, 0.05), P(0.52 * fwd, 0.01),
                        P(0.32 * fwd, -0.04), P(-0.1 * fwd, -0.06)], white)
                L.ellipse(x + 0.34 * fwd * M, y - 0.02 * M, 0.07 * M, 0.05 * M, white * np.array([1.0, 0.94, 0.78], np.float32))
            elif pose == "dive":
                # wings folded back into an arrow, straight down at the sea
                tilt = 0.25 if seed % 2 else -0.25
                L.poly([(x + tilt * 0.6 * M, y + 0.55 * M), (x - 0.08 * M, y - 0.15 * M), (x - 0.2 * M - tilt * 0.3 * M, y - 0.6 * M),
                        (x, y - 0.35 * M), (x + 0.2 * M - tilt * 0.3 * M, y - 0.6 * M), (x + 0.08 * M, y - 0.15 * M)], white)
                L.poly([(x - 0.2 * M - tilt * 0.3 * M, y - 0.6 * M), (x - 0.13 * M - tilt * 0.3 * M, y - 0.42 * M), (x - 0.08 * M, y - 0.5 * M)], black)
                L.poly([(x + 0.2 * M - tilt * 0.3 * M, y - 0.6 * M), (x + 0.13 * M - tilt * 0.3 * M, y - 0.42 * M), (x + 0.08 * M, y - 0.5 * M)], black)
            elif pose == "splash":
                # the plume it throws up going in: a ragged column, spray thrown out, a ring of white water
                foam = self.lit((236, 240, 242), (0, 0.5, 0.85), shade=shade) * (1 - hz_k) + self.hor_col * hz_k
                r_ = np.random.default_rng([seed, i, self.m])
                pts = [(x - 0.3 * M, y)]
                for k in range(7):
                    u = k / 6
                    pts.append((x - 0.22 * M + 0.44 * M * u, y - (0.6 + 0.6 * math.sin(math.pi * u) + 0.25 * r_.random()) * M))
                pts.append((x + 0.3 * M, y))
                L.poly(pts, foam, a=0.7)
                for e in (-1, 1):
                    L.line([(x + e * 0.2 * M, y - 0.2 * M), (x + e * 0.7 * M, y - 0.75 * M)], foam, max(0.5 * self.s, 0.07 * M), a=0.45)
                for k in range(6):
                    L.ellipse(x + r_.uniform(-0.8, 0.8) * M, y - r_.uniform(0.6, 1.5) * M, 0.05 * M, 0.05 * M, foam, a=0.6)
                L.ellipse(x, y + 0.02 * M, 0.7 * M, 0.11 * M, foam, a=0.5)
            elif pose == "ring":
                foam = self.lit((226, 232, 236), (0, 0.4, 1), shade=shade) * (1 - hz_k) + self.hor_col * hz_k
                L.ellipse(x, y, 0.55 * M, 0.09 * M, foam, a=0.35)
            else:   # back up after its dive, sitting on the water, head up
                L.ellipse(x, y - 0.05 * M, 0.3 * M, 0.1 * M, white)
                L.ellipse(x + 0.22 * M, y - 0.16 * M, 0.08 * M, 0.07 * M, white * np.array([1.0, 0.94, 0.78], np.float32))
                L.line([(x + 0.28 * M, y - 0.16 * M), (x + 0.4 * M, y - 0.13 * M)], self.lit((120, 130, 140), (0, 0.6, 0.8)), max(0.5 * self.s, 0.04 * M))
            L.composite()

    # =========================================================== the hooks --
    def far_sea(self):
        """The boats and birds beyond the beacon: the ferry, the yachts and the gannets, far to near; drawn after
        the sea and before the beacon, so the mist and the fog veil them by distance."""
        if self.reference:
            return
        items = []
        f = self.ferry_now()
        if f:
            items.append((math.hypot(f[0], f[1]), self.ferry))
        for y, p in self.day.sea.yachts_at(self.m):
            items.append((math.hypot(p[0], p[1]), self.yachts))
            break
        if self.day.sea.gannets_at(self.m):
            items.append((14.0, self.gannets))
        for _, fn in sorted(items, key=lambda t: -t[0]):
            fn()

    def sea_items(self):
        """What bay() draws among the marks by its waterline (frame fraction): the creel boat, the dolphins and
        seals' heads in the water."""
        if self.reference:
            return []
        out = []
        y = self.creel_y()
        if y is not None:
            out.append((y, self.creel_boat))
        y = self.dolphins_y()
        if y is not None:
            out.append((y, self.dolphins))
        for y, head in self.seal_heads_y():
            out.append((y, lambda head=head: self.draw_seal_head(head)))
        return out

    def sea_emitters(self):
        """The ferry's lights, mirrored in the sea (plan_emitters)."""
        if self.reference:
            return
        for x, y, yw, col, k in self.ferry_lights():
            self.emitters.append((x, y, np.asarray(col, np.float32), 0.3 * k, yw))

    def sea_lights(self):
        """The ferry's lights through the fog (render, after fog_far)."""
        if self.reference:
            return
        wx = self.wx
        for x, y, yw, col, k in self.ferry_lights():
            f = self.ferry_now()
            D = math.hypot(f[0], f[1])
            through = 1.0
            if wx.fog >= 0.02 or wx.visibility_m <= 15000:
                through = math.exp(-3.9 / max(wx.visibility_m, 60.0) * D * 15)
            self.glow(x, y, 1.2 * self.s, col, 1.2 * k * (0.25 + 0.75 * through))
            self.glow(x, y, (4 + 8 * (1 - through)) * self.s, col, (0.12 + 0.1 * (1 - through)) * k)
