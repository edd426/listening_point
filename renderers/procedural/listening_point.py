#!/usr/bin/env python3
"""The Listening Point: one scene, rendered for every minute of a real day.

A small stone observatory on a headland above the sea, with a tree, a bench for two, a lamp, a
pier, and a lighthouse across the bay. The sun, moon, planets and stars stand where they really
are over Budapest at that minute, the weather follows the forecast, and the season follows the
calendar; the clock on the tower says the time plainly.

usage: listening_point.py OUT_DIR [--date 2026-10-06] [--scale 0.75] [--minutes 0-1439 | --hours 0,6 | --times 06:30,21:15]
                          [--every N] [--jobs 3] [--step 10] [--weather auto|fair|synthetic|offline|clear|fog] [--sheet]
                          [--shore DIR] [--lamp FILE] [--reference]

Writes HHMM.jpg (local clock time) for each requested minute at 3840x2400 * scale.
The slow-changing near scenery (grass, tree, pier, bench, lamp) is rendered every --step minutes
and cross-faded; everything that moves is rendered fresh each minute.

--shore DIR draws the objects of a local shore cache (shorekit's layout: ledger.json, objects/,
reference/<id>/); --lamp FILE reads the listener's lamp state. --reference holds the scene still for
the shore kit's reference frames (see tools/shore_reference.py): no creatures, no rare events, no
grain, the tide at high water, and the same clear weather all day unless --weather fog.
"""
import argparse
import datetime as dt
import functools
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

from air import AirMixin
from core import FrameBase
from day import Day
from distant import DistantMixin
from fauna import FaunaMixin
from hillside import HillsideMixin
from land import LandMixin
from life import LifeMixin
from props import PropsMixin
from sea import SeaMixin
from sky import SkyMixin
from tower import TowerMixin
from tree import TreeMixin
from mystery import MysteryMixin
from shore import ShoreMixin
from weatherfx import WeatherFxMixin


class Frame(FrameBase, SkyMixin, DistantMixin, SeaMixin, LandMixin, HillsideMixin, TowerMixin, TreeMixin, PropsMixin, LifeMixin,
            FaunaMixin, WeatherFxMixin, MysteryMixin, ShoreMixin, AirMixin):
    def background(self):
        """Everything behind the near scenery, rendered every minute."""
        self.sky()
        self.lightning()
        self.rainbow()
        self.sky_extras()
        self.far_coast()
        self.ships()
        self.headland()
        self.far_lights()
        self.beams()
        self.plan_emitters()
        self.sea()
        self.whale()
        self.mist()
        self.boats()
        self.moored_boat()
        self.foam()

    def foreground(self):
        """The near scenery as premultiplied colour and coverage; it changes only with the light."""
        self.c = np.zeros((self.H, self.W, 3), np.float32)
        self.a = np.zeros((self.H, self.W), np.float32)
        self.shade, self.ao = self.shadow_masks()
        self.hill()
        self.pier()
        self.tree()
        self.bench()
        self.lamp()
        return self.c, self.a

    def front(self):
        """Things in front of the near scenery, rendered every minute, as a layer so the fog can veil it."""
        base = self.c
        self.c = np.zeros_like(base)
        self.a = np.zeros(base.shape[:2], np.float32)
        self.tower()
        self.shore()
        if not self.reference:      # creatures and rare events, in front of the shore's objects
            self._life = []         # the animals drawn so far, which hide the ones behind them (fauna.py)
            self.door_light()
            self.pier_gulls()
            self.footprints()
            self.bottle()
            self.book()
            self.sheep()
            self.hares()
            self.fox()
            self.crows()
            self.critters()
            self.cat()
            self.heron()
            self.owl()
            self.air_kite()
        C, A = self.fog_near(self.c, self.a), self.a
        self.c, self.a = base * (1 - A[..., None]) + C, None
        if getattr(self, "backlit", None):
            x, y, R, k = self.backlit
            self.glow(x, y, R * 1.3, (255, 240, 210), 0.5 * k, tail=0.5)
        self.night_lights()
        self.listener_glow()
        self.shore_glow()
        if not self.reference:
            self.falling_leaves()
        self.precipitation()

    def grade(self):
        H, W = self.H, self.W
        vig, grain = grade_maps(W, H)
        c = self.c
        c *= vig[..., None]
        tone(c, self.night)
        if not self.reference:
            c += np.roll(grain, (int(self.rng.integers(H)), int(self.rng.integers(W))), (0, 1))[..., None]
        c += 0.5
        np.clip(c, 0, 255, out=c)
        return c.astype(np.uint8)

    def render(self, fg):
        """fg is (lit colour, coverage, colour with the sun hidden or None), already blended in time."""
        self.background()
        self.fog_far()
        self.ghost_ship()
        C, A, Cs = fg
        if Cs is not None:
            C = Cs + (C - Cs) * self.sun_vis
        C = self.fog_near(C, A)
        self.c *= 1 - A[..., None]
        self.c += C
        self.light_shafts(A)
        self.front()
        return Image.fromarray(self.grade())


def tone(c, night):
    """The tone curve of grade(), in place on float32 colour c: between the vignette and the grain."""
    # day for night: lift the shadows so the dark scene still reads, and cool it a little
    if night > 0:
        np.maximum(c, 0, out=c)
        c /= 255
        np.power(c, 1 / (1 + 0.28 * night), out=c)
        c *= 255 * (1 - night * np.array([0.06, 0.02, -0.04], np.float32))
    hi = c > 200      # roll the highlights off softly
    c[hi] = 200 + 55 * np.tanh((c[hi] - 200) / 55)


@functools.lru_cache(None)
def grade_maps(W, H):
    """Vignette and film grain, made once per process."""
    yy = (np.arange(H, dtype=np.float32)[:, None] + 0.5) / H
    xx = (np.arange(W, dtype=np.float32)[None, :] + 0.5) / W
    vig = 1 - 0.38 * (((xx - 0.5) * 1.1) ** 2 + ((yy - 0.52) * 1.3) ** 2)
    grain = np.random.default_rng(5).normal(0, 1.4, (H, W)).astype(np.float32)
    return vig.astype(np.float32), grain


# ------------------------------------------------------------------ workers --
W_ = {}


def init_worker(day, scale, step, out, quality=92):
    W_.update(day=day, scale=scale, step=step, out=out, keys={}, quality=quality)


def needs_shade(day, m):
    """Whether clouds may hide the sun around minute m, so the near scenery needs a shaded version too."""
    i0, i1 = max(0, m - 12), min(1440, m + 12)
    if day.sun_alt[i0:i1 + 1].max() < -3:
        return False
    wx = day.wx
    j0, j1 = min(i0, 1439), min(i1, 1439) + 1
    return bool((wx.cloud_low[j0:j1] + wx.cloud_mid[j0:j1]).max() > 0.02 or wx.fog[j0:j1].max() > 0.05)


def keyframe(m):
    keys = W_["keys"]
    if m not in keys:
        while len(keys) >= 2:       # a keyframe pair is all a run of minutes needs; half precision is plenty
            keys.pop(min(keys))
        day, sc = W_["day"], W_["scale"]
        half = lambda a: a.astype(np.float16)
        if needs_shade(day, m):
            C, A = Frame(day, m, sc, sun="on").foreground()
            C, A = half(C), half(A)
            Cs = half(Frame(day, m, sc, sun="off").foreground()[0])
        else:
            C, A = Frame(day, m, sc, sun="on").foreground()
            C, A, Cs = half(C), half(A), None
        keys[m] = (C, A, Cs)
    return keys[m]


def frame_image(m):
    """The finished frame for minute m (a PIL image), from this worker's day, scale and keyframe step."""
    step = W_["step"]
    k0 = (m // step) * step
    f = (m - k0) / step
    C0, A0, S0 = keyframe(k0)
    f32 = lambda a: a.astype(np.float32)
    if f > 0:
        C1, A1, S1 = keyframe(k0 + step)
        S = None if S0 is None and S1 is None else \
            f32(C0 if S0 is None else S0) * (1 - f) + f32(C1 if S1 is None else S1) * f
        fg = (f32(C0) * (1 - f) + f32(C1) * f, f32(A0) * (1 - f) + f32(A1) * f, S)
    else:
        fg = (f32(C0), f32(A0), None if S0 is None else f32(S0))
    return Frame(W_["day"], m, W_["scale"]).render(fg)


def render_chunk(minutes):
    out = W_["out"]
    done = []
    for m in minutes:
        path = os.path.join(out, f"{m // 60:02d}{m % 60:02d}.jpg")
        tmp = path + ".tmp.jpg"
        frame_image(m).save(tmp, quality=W_["quality"])
        os.replace(tmp, path)
        done.append(path)
    return done


def parse_minutes(a):
    out = []
    if a.times:
        out = [int(t[:2]) * 60 + int(t[-2:]) for t in a.times.split(",")]
    elif a.hours:
        for part in a.hours.split(","):
            lo, _, hi = part.partition("-")
            out += [h * 60 for h in range(int(lo), int(hi or lo) + 1)]
    else:
        lo, _, hi = a.minutes.partition("-")
        out = list(range(int(lo), int(hi or lo) + 1, a.every))
    return sorted(set(m for m in out if 0 <= m < 1440))


def chunks(minutes, step, n):
    """Contiguous runs of minutes, split on keyframe boundaries so each worker reuses its keyframes."""
    runs, cur = [], []
    size = max(step, -(-len(minutes) // n))
    for m in minutes:
        if cur and (len(cur) >= size and m % step == 0 or m - cur[-1] > step):
            runs.append(cur)
            cur = []
        cur.append(m)
    if cur:
        runs.append(cur)
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--date", default=None, help="local date to render (default: today)")
    ap.add_argument("--scale", type=float, default=0.75)
    ap.add_argument("--minutes", default="0-1439")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--hours", default=None)
    ap.add_argument("--times", default=None)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--step", type=int, default=10, help="minutes between near-scenery keyframes")
    ap.add_argument("--weather", default="auto", choices=["auto", "fair", "synthetic", "offline", "clear", "fog"])
    ap.add_argument("--cache", default=os.path.expanduser("~/Library/Caches/listening-point"))
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--quality", type=int, default=92)
    ap.add_argument("--skip-existing", action="store_true", help="leave frames that are already rendered (to resume)")
    ap.add_argument("--shore", default=None, help="a local shore cache whose objects are drawn (default: none)")
    ap.add_argument("--lamp", default=None, help="the listener's lamp-state file (default: none, never lit)")
    ap.add_argument("--reference", action="store_true",
                    help="hold the scene still (no creatures, rare events or grain) as for the shore kit's reference frames")
    a = ap.parse_args()
    if a.reference and a.weather == "auto":
        a.weather = "clear"
    date = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    minutes = parse_minutes(a)
    os.makedirs(a.out, exist_ok=True)
    if a.skip_existing:
        minutes = [m for m in minutes if not os.path.exists(os.path.join(a.out, f"{m // 60:02d}{m % 60:02d}.jpg"))]
        if not minutes:
            print("nothing to do", flush=True)
            return
    t0 = time.time()
    day = Day(date, weather=a.weather, cache_dir=a.cache, reference=a.reference, shore=a.shore, lamp=a.lamp)
    print(f"{date}: weather {day.wx.source}; sunrise {day.events.sunrise:.2f} sunset {day.events.sunset:.2f}; "
          f"moon {day.moon_frac[720]:.0%} lit", flush=True)
    # scattered minutes each get their own near-scenery; runs of minutes share keyframes
    step = 1440 if (a.times or a.hours or a.every > 1 or len(minutes) == 1) else a.step
    runs = chunks(minutes, a.step, a.jobs * 3) if step != 1440 else [[m] for m in minutes]
    paths = []
    with ProcessPoolExecutor(a.jobs, initializer=init_worker, initargs=(day, a.scale, a.step if step != 1440 else 1, a.out, a.quality)) as ex:
        for done in ex.map(render_chunk, runs):
            paths += done
            print(f"{len(paths)}/{len(minutes)} {done[-1]}", flush=True)
    print(f"rendered {len(paths)} frames in {time.time() - t0:.0f} s", flush=True)
    if a.sheet:   # a contact sheet of small thumbnails
        pick = paths if len(paths) <= 24 else paths[::max(1, len(paths) // 24)][:24]
        w, h = 480, 300
        ims = [Image.open(p).resize((w, h), Image.LANCZOS) for p in pick]
        cols = min(6, len(ims))
        rows = (len(ims) + cols - 1) // cols
        sheet = Image.new("RGB", (w * cols, h * rows))
        for i, im in enumerate(ims):
            sheet.paste(im, ((i % cols) * w, (i // cols) * h))
        sheet.save(os.path.join(a.out, "sheet.jpg"), quality=88)


if __name__ == "__main__":
    main()
