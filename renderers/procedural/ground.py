"""The ground's fine structure: tufts of grass, hummocks, and the worn path, as per-pixel fields.

None of this is light. The fields are coverage, albedo factors, normals and occlusion, which the hill
(land.py) turns into colour through the frame's own sun, moon and sky, so a tuft's lit side follows
the sun round and the night and the fog take it like everything else. They depend only on the frame
size, never on the date or the minute, so each process builds them once and keeps them (GROUND).
"""
import numpy as np
from scipy import ndimage as ndi

from core import fnoise, sample, sm

GROUND = {}          # (W, H, y0) -> the fields, built once per process

# the tuft lattice, in pixels of a 3840-wide frame at a perspective of 1 (land.persp)
CU, CV = 9.0, 5.5    # spacing across, and down the slope
HB, WB = 14.0, 7.0   # a tuft's height and half-width


def persp(y, H):
    """The hill's perspective scale at frame row y (the same as LandMixin.hill's persp)."""
    return 0.35 + 1.3 * np.clip((np.asarray(y, np.float64) / H - 0.6) / 0.4, 0, 1)


def tri(z):
    """A triangle wave, 1 at half-integers and 0 at integers."""
    return 1 - np.abs(2 * (z - np.floor(z)) - 1)


def path_field(pts, w0, w1, box, n=2400):
    """Across (-1 at one edge, 0 on the centre line, 1 at the other) and along (0 at the start, 1 at the
    end) coordinates of a ribbon (LandMixin.ribbon) for every pixel of box = (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    k = np.linspace(0, len(pts) - 1, n)
    P = np.stack([np.interp(k, np.arange(len(pts)), pts[:, i]) for i in (0, 1)], 1)
    w = w0 + (w1 - w0) * k / (len(pts) - 1)
    d = np.gradient(P, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
    nrm = np.stack([-d[:, 1], d[:, 0]], 1)
    h, wd = y1 - y0, x1 - x0
    lab = np.full((h, wd), -1, np.int32)
    c = np.floor(P[:, 0] - x0).astype(int)
    r = np.floor(P[:, 1] - y0).astype(int)
    ok = (c >= 0) & (c < wd) & (r >= 0) & (r < h)
    lab[r[ok], c[ok]] = np.arange(n)[ok]
    if not ok.any():
        return np.full((h, wd), 9.0, np.float32), np.zeros((h, wd), np.float32)
    _, (ir, ic) = ndi.distance_transform_edt(lab < 0, return_indices=True)
    j = lab[ir, ic]
    X = np.arange(x0, x1, dtype=np.float64)[None, :] + 0.5
    Y = np.arange(y0, y1, dtype=np.float64)[:, None] + 0.5
    across = ((X - P[j, 0]) * nrm[j, 0] + (Y - P[j, 1]) * nrm[j, 1]) / w[j]
    return across.astype(np.float32), (j / (n - 1)).astype(np.float32)


def build(W, H, y0, xk, path, trail, edge_y):
    """The fields for columns 0..xk of a W x H frame whose hill starts at row y0. path and trail are
    (points, w0, w1) of the two ribbons; edge_y(xn) is the hill's skyline (rows) at fractions of the width."""
    s = W / 3840
    hh = H - y0
    Yc = np.arange(y0, H, dtype=np.float64) + 0.5
    Xc = np.arange(xk, dtype=np.float64) + 0.5
    P = persp(Yc, H)
    F = {}

    # ---- the path to the door and the trail to the bench, in their own coordinates
    pts, w0, w1 = path
    pad = 1.6 * max(w0, w1)
    box = (max(0, int(pts[:, 0].min() - pad)), y0, min(xk, int(pts[:, 0].max() + pad) + 1), H)
    across, along = path_field(pts, w0, w1, box)
    A = np.full((hh, xk), 9.0, np.float32)
    T = np.zeros((hh, xk), np.float32)
    A[:, box[0]:box[2]], T[:, box[0]:box[2]] = across, along
    pts2, v0, v1 = trail
    pad2 = 3.0 * max(v0, v1)
    box2 = (max(0, int(pts2[:, 0].min() - pad2)), max(y0, int(pts2[:, 1].min() - pad2)),
            min(xk, int(pts2[:, 0].max() + pad2) + 1), min(H, int(pts2[:, 1].max() + pad2) + 1))
    a2, _ = path_field(pts2, v0, v1, box2)
    A2 = np.full((hh, xk), 9.0, np.float32)
    A2[box2[1] - y0:box2[3] - y0, box2[0]:box2[2]] = a2
    # a ragged edge: the grass wins a little here and loses a little there, along each side
    ragged = fnoise(8, 1024, 1.6, 1.0, 120)
    side = (A > 0).astype(np.int64) * 4
    rag = ragged[side, (np.clip(T, 0, 1) * 1023).astype(np.int64)] * 0.07 \
        + ragged[side + 2, (np.clip(T, 0, 1) * 1023 * 4).astype(np.int64) % 1024] * 0.035
    edge = 1.0 + rag
    a = np.abs(A)
    F["path"] = sm(edge + 0.07, edge - 0.05, a) * (A < 8)            # 1 on the path, 0 on the grass
    # a rut each side of the middle, coming and going along the path
    wander = np.interp(T, np.linspace(0, 1, 1024), fnoise(4, 1024, 2.2, 1.0, 121)[0]) * 0.05
    come = sm(-0.3, 0.6, np.interp(T, np.linspace(0, 1, 1024), fnoise(4, 1024, 2.6, 1.0, 122)[1]))
    rut = (np.exp(-((A - 0.42 - wander) / 0.07) ** 2) + np.exp(-((A + 0.40 - wander) / 0.07) ** 2)) * come
    rut = rut * sm(0.98, 0.9, T) * (A < 8)                             # none on the threshold
    F["rut"] = rut
    # the ruts' slopes, as a tilt that doesn't depend on how wide the path is where they run
    wpx = w0 + (w1 - w0) * T
    ry_, rx_ = np.gradient(rut)
    F["rut_x"], F["rut_y"] = rx_ * wpx * 0.02, ry_ * wpx * 0.02
    F["across"] = A
    F["trail"] = sm(1.3, 0.3, np.abs(A2)) * (np.abs(A2) < 8)

    # ---- hummocks: a height field in the ground's own perspective, lit through its normal
    v = np.cumsum(1 / (P * s)) - 0.5 / (P[0] * s)                     # down-slope distance, in ground px
    u = (Xc[None, :] - W / 2) / (np.sqrt(P)[:, None] * s)              # across (half perspective: no shear)
    hm = fnoise(256, 1024, 3.2, 1.8, 130)
    gy, gx = np.gradient(hm)
    cu_, cv_ = 512 / 2600.0, 256 / 1100.0                               # texture texels per ground px
    rr = np.broadcast_to((v * cv_)[:, None], (hh, xk))
    cc = u * cu_
    F["hum"] = sample(hm, rr, cc)
    sd = max(float(np.std(gx)), float(np.std(gy)), 1e-9)
    F["hum_x"] = sample(gx, rr, cc) / sd                               # slopes on the ground, not the screen
    F["hum_y"] = sample(gy, rr, cc) / sd
    # swathes: big, soft, lighter and darker bands that lie along the slope
    sw = fnoise(128, 512, 3.0, 3.0, 131)
    F["swathe"] = sample(sw, np.broadcast_to((v * 128 / 1400.0)[:, None], (hh, xk)), np.broadcast_to((Xc[None, :] - W / 2) / s * 512 / 6000.0, (hh, xk)))

    # clumps: tufts gather in patches with shorter, open grass between, a few ground-feet across
    wn = np.random.default_rng(133).standard_normal((256, 1024))
    cl = ndi.gaussian_filter(wn, 2.2, mode="wrap") - 0.6 * ndi.gaussian_filter(wn, 6.0, mode="wrap")
    cl = (cl - cl.mean()) / cl.std()
    F["clump"] = sample(cl.astype(np.float32), np.broadcast_to((v / 7.0)[:, None], (hh, xk)), u / 7.0)

    # ---- tufts, on a jittered lattice laid on the ground in perspective
    dens = 0.1 + 0.88 * sm(-0.5, 0.45, F["clump"] - 0.3 * F["swathe"])
    dens = dens * (1 - 0.97 * F["path"] * sm(1.03, 0.92, a)) * (1 - 0.75 * F["trail"])
    below = Yc[:, None] - edge_y(Xc / W)[None, :]                     # rows under where the grass starts
    dens *= below > 4 * s
    tall = (0.72 + 0.4 * sm(-0.3, 1.2, F["clump"])) * (0.5 + 0.5 * sm(4 * s, 40 * s, below))
    vb = np.concatenate([v, v[-1] + np.arange(1, 64) / (P[-1] * s)])   # carry on below the frame
    yb = np.concatenate([Yc, Yc[-1] + np.arange(1, 64)])
    NI = int(vb[-1] // CV) + 2
    Prow = persp(np.interp((np.arange(NI) + 0.5) * CV, vb, yb), H)
    umax = (W / 2) / (Prow.min() * s * CU)
    NJ = 2 * int(umax) + 6
    j0 = NJ // 2
    rng = np.random.default_rng(140)
    ju, jv, size, pres, tone, ph = (rng.random((NI, NJ)) for _ in range(6))
    nb = rng.integers(3, 7, (NI, NJ)).astype(np.float32)
    size = 0.75 + 0.45 * size
    yr = np.interp((np.arange(NI)[:, None] + jv) * CV, vb, yb)          # each tuft's root, in frame rows
    xr = (np.arange(NJ)[None, :] - j0 + ju) * CU * Prow[:, None] * s + W / 2
    Pr = persp(yr, H)
    ri = np.clip(np.floor(yr - y0).astype(int), 0, hh - 1)
    ci = np.clip(np.floor(xr).astype(int), 0, xk - 1)
    alive = (pres < dens[ri, ci]) & (xr > -20) & (xr < xk + 20)
    th = (np.minimum(HB * size * tall[ri, ci], 2.9 * CV) * Pr * s).astype(np.float32)   # within the rows looked at
    tw = (WB * size * Pr * s).astype(np.float32)
    tab = [a_.astype(np.float32).ravel() for a_ in (xr, yr, th, tw, nb, ph, tone)] + [alive.ravel()]
    cov = np.zeros((hh, xk), np.float32)
    tt, qq, to, st = (np.zeros((hh, xk), np.float32) for _ in range(4))
    iv = np.floor(v / CV).astype(int)
    step = 48
    for r0 in range(0, hh, step):
        r1 = min(hh, r0 + step)
        X = Xc[None, :].astype(np.float32)
        Y = Yc[r0:r1, None].astype(np.float32)
        c_, t_, q_, o_, s_ = cov[r0:r1], tt[r0:r1], qq[r0:r1], to[r0:r1], st[r0:r1]
        for di in range(4):                         # far to near: a nearer tuft hides the one behind
            ii = np.clip(iv[r0:r1] + di, 0, NI - 1)[:, None]
            jj = np.floor((X - W / 2) / (Prow[ii] * s * CU)).astype(int) + j0
            for dj in (-1, 0, 1):
                k = ii * NJ + np.clip(jj + dj, 0, NJ - 1)
                txr, tyr, h, w, n, p, o, ok = (t[k] for t in tab)
                dy = tyr - Y
                fh = np.clip(dy / h, 0, 1)
                half = w * (0.3 + 0.7 * np.minimum(1, fh * 2.2))   # splays from a narrow foot
                q = (X - txr) / half
                z = q * n * 0.5 + p
                bl = tri(z)
                tip = h * (0.42 + 0.58 * bl ** 1.4) * (1 - 0.45 * q * q)   # pointed blades, the middle tallest
                cv = np.clip((1 - np.abs(q)) * half + 0.5, 0, 1) * np.clip(tip - dy + 0.5, 0, 1) \
                    * np.clip(dy + 1.0, 0, 1) * ok
                c_ *= 1 - cv
                c_ += cv
                for out, val in ((t_, np.clip(dy / np.maximum(tip, 0.5), 0, 1)), (q_, np.clip(q, -1, 1)), (o_, o),
                                 (s_, bl)):
                    out += (val - out) * cv
    F.update(tuft=cov, tip=tt, lean=qq, tone=to, blade=st)
    F["dense"] = ndi.gaussian_filter(cov, 3.0 * s / 0.75)          # how crowded the tufts are about here
    return {k: np.ascontiguousarray(v_, np.float16) for k, v_ in F.items()}


def fields(W, H, y0, xk, path, trail, edge_y):
    """The fields for this frame size, built on first use and kept (float16: about 30 bytes a pixel)."""
    key = (W, H, y0, xk)
    if key not in GROUND:
        GROUND.clear()
        GROUND[key] = build(W, H, y0, xk, path, trail, edge_y)
    return GROUND[key]
