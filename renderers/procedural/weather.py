#!/usr/bin/env python3
"""Weather for The Listening Point: one local day, one value per clock minute.

day_weather() follows the real hourly forecast for Budapest from Open-Meteo (free, no key; only the
city's coordinates are sent). Without a network it uses the newest cached forecast that covers the
day, and failing that synthetic_day(): deterministic made-up weather with a Budapest-like climate.
fair_day() is a dry, calm, lightly clouded day for previews and release builds.

usage: weather.py [DATE] [--offline] [--synthetic] [--fair] [--cache DIR] [-v]
"""
import argparse
import datetime as dt
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, fields
from typing import Optional
from zoneinfo import ZoneInfo

import numpy as np

LAT, LON, TZ = 47.4979, 19.0402, "Europe/Budapest"
API = "https://api.open-meteo.com/v1/forecast"
HOURLY = ("temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation", "rain", "showers",
          "snowfall", "snow_depth", "weather_code", "cloud_cover", "cloud_cover_low", "cloud_cover_mid",
          "cloud_cover_high", "visibility", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m")
CACHE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "out", "weather"))
CA_FILES = ("/etc/ssl/cert.pem", "/opt/homebrew/etc/openssl@3/cert.pem", "/usr/local/etc/openssl@3/cert.pem",
            "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt")
RETRY_DELAYS = (3, 10)   # seconds before the second and the third attempt
AHEAD = 2                # extra days fetched after the wanted one, so the cache can cover offline nights
SPINUP = 3               # days before the wanted one used to spin up ground wetness, rime and lying snow
DAY = dt.timedelta(days=1)
EPOCH = dt.date(1970, 1, 1)
SNOW_CODES = (71, 73, 75, 77, 85, 86)
WIND_UNITS = {"m/s": 1.0, "km/h": 1 / 3.6, "mp/h": 0.44704, "kn": 0.514444}
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


@dataclass(eq=False, repr=False)
class DayWeather:
    """One local day of weather. Every array has 1440 entries indexed by local clock minute (00:00 = 0)."""
    date: dt.date
    tz_name: str
    source: str               # "forecast", "cache", "synthetic" or "fair"
    reason: str               # why this source was used
    fetched_at: Optional[str]  # when the forecast was fetched (ISO 8601 UTC), else None
    utc: np.ndarray           # float64 UTC seconds of each minute
    temp_c: np.ndarray
    rh: np.ndarray            # 0-1
    dew_c: np.ndarray
    precip_mmph: np.ndarray   # all precipitation, mm of water per hour
    rain_mmph: np.ndarray     # rain + showers
    snowfall_cmph: np.ndarray
    snow_depth_m: np.ndarray
    cloud_low: np.ndarray     # cloud fractions 0-1
    cloud_mid: np.ndarray
    cloud_high: np.ndarray
    cloud_total: np.ndarray
    visibility_m: np.ndarray
    wind_ms: np.ndarray
    gust_ms: np.ndarray
    wind_dir_deg: np.ndarray  # where the wind comes from
    code: np.ndarray          # int16 WMO code of the nearest hour
    fog: np.ndarray           # derived 0-1 signals from here on
    rain: np.ndarray
    snow: np.ndarray
    drizzle: np.ndarray
    thunder: np.ndarray
    wet: np.ndarray
    snow_cover: np.ndarray
    frost: np.ndarray

    def __repr__(self):
        return f"<DayWeather {self.date} {self.source}: {summary(self)}>"


ARRAYS = tuple(f.name for f in fields(DayWeather))[6:]


# ----------------------------------------------------------------- helpers ---
def sm(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _smooth(x, n):
    """Centred moving average over n (odd) samples."""
    return np.convolve(np.pad(np.asarray(x, float), n // 2, mode="edge"), np.ones(n) / n, "valid")


def _doy(d):
    return d.timetuple().tm_yday


def _midnight(date, tz_name):
    return dt.datetime.combine(date, dt.time(), ZoneInfo(tz_name)).timestamp()


def _minutes(date, tz_name):
    """UTC seconds of each local clock minute of date: a repeated hour keeps its first pass, a skipped
    hour is interpolated across the jump."""
    z = ZoneInfo(tz_name)
    w0 = dt.datetime.combine(date, dt.time())
    a, b = w0.replace(tzinfo=z), (w0 + dt.timedelta(minutes=1439)).replace(tzinfo=z)
    if a.utcoffset() == b.utcoffset():
        return a.timestamp() + 60.0 * np.arange(1440)
    t, ok = np.empty(1440), np.ones(1440, bool)
    for m in range(1440):
        w = w0 + dt.timedelta(minutes=m)
        t[m] = w.replace(tzinfo=z).timestamp()
        ok[m] = dt.datetime.fromtimestamp(t[m], z).replace(tzinfo=None) == w
    t[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), t[ok])
    return t


def _sun_alt(t, lat, lon):
    """Solar altitude in degrees at UTC seconds t (low-precision almanac, good to about 0.1 deg)."""
    n = np.asarray(t, float) / 86400 - 10957.5
    g = np.radians(357.528 + .9856003 * n)
    lam = np.radians(280.460 + .9856474 * n + 1.915 * np.sin(g) + .020 * np.sin(2 * g))
    eps = np.radians(23.439 - 4e-7 * n)
    ra = np.arctan2(np.cos(eps) * np.sin(lam), np.cos(lam))
    dec = np.arcsin(np.sin(eps) * np.sin(lam))
    ha = np.radians(280.46061837 + 360.98564736629 * n + lon) - ra
    la = np.radians(lat)
    return np.degrees(np.arcsin(np.sin(la) * np.sin(dec) + np.cos(la) * np.cos(dec) * np.cos(ha)))


def _dew(t, rh):
    g = np.log(np.clip(rh, 1, 100) / 100) + 17.625 * t / (243.04 + t)
    return 243.04 * g / (17.625 - g)


def _rh(t, td):
    return np.clip(100 * np.exp(17.625 * td / (243.04 + td) - 17.625 * t / (243.04 + t)), 1, 100)


def _nearest(th, t):
    j = np.clip(np.searchsorted(th, t), 1, len(th) - 1)
    return j - ((t - th[j - 1]) < (th[j] - t))


def _snowpack(th, snow_cm, temp, liquid, sun=None):
    """Hourly snow depth (m) from snowfall, settling, and a degree-hour melt helped by sun and rain."""
    sun = np.zeros(len(th)) if sun is None else sun
    hrs = np.diff(th, prepend=th[0] - 3600) / 3600
    d, out = 0.0, np.empty(len(th))
    for i, (s, t, r, z, h) in enumerate(zip(*(v.tolist() for v in (snow_cm, temp, liquid, sun, hrs)))):
        if d > 0 or s > 0:
            d = max(0.0, d * .996 ** h + s / 100 - ((.0008 + .001 * z) * max(t, 0) + .0004 * r) * h)
        out[i] = d
    return out


# ---------------------------------------------------------------- fetching ---
class ForecastError(RuntimeError):
    """Open-Meteo could not be reached, refused the request, or sent unusable data."""


_CTX = []


def _contexts():
    """Verifying SSL contexts to try: Python's defaults, certifi, system CA bundles, the macOS keychain."""
    yield ssl.create_default_context()
    try:
        import certifi
        yield ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    for f in CA_FILES:
        if os.path.exists(f):
            try:
                yield ssl.create_default_context(cafile=f)
            except Exception:
                pass
    if sys.platform == "darwin":
        try:
            pem = subprocess.run(["/usr/bin/security", "find-certificate", "-a", "-p",
                                  "/System/Library/Keychains/SystemRootCertificates.keychain"],
                                 capture_output=True, text=True, timeout=30).stdout
            yield ssl.create_default_context(cadata=pem)
        except Exception:
            pass


def _get(url, timeout):
    """Body of url. Other CA bundles are tried only when certificate verification fails."""
    err = None
    for ctx in (list(_CTX) or _contexts()):
        try:
            with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
                body = r.read()
            _CTX[:] = [ctx]
            return body
        except urllib.error.URLError as e:
            if not isinstance(e.reason, ssl.SSLCertVerificationError):
                raise
            err = e
    raise err


def _request(url, timeout):
    """Body of url, with two retries for network and server errors (not for a refused request)."""
    err = None
    for i in range(len(RETRY_DELAYS) + 1):
        if i:
            time.sleep(RETRY_DELAYS[i - 1])
        try:
            return _get(url, timeout)
        except urllib.error.HTTPError as e:
            try:
                why = json.loads(e.read()).get("reason") or e.reason
            except Exception:
                why = e.reason
            err = ForecastError(f"Open-Meteo HTTP {e.code}: {why}")
            if 400 <= e.code < 500 and e.code != 429:
                raise err from None
        except Exception as e:
            why = getattr(e, "reason", None) or e
            err = ForecastError(f"Open-Meteo unreachable: {str(why) or repr(why)}")
    raise ForecastError(f"{err} (after {len(RETRY_DELAYS) + 1} attempts)")


def _url(lat, lon, tz_name, a, b):
    return API + "?" + urllib.parse.urlencode(dict(
        latitude=f"{lat:.4f}", longitude=f"{lon:.4f}", hourly=",".join(HOURLY), timezone=tz_name,
        start_date=a.isoformat(), end_date=b.isoformat(), wind_speed_unit="ms", timeformat="unixtime"))


def fetch_forecast(lat, lon, tz_name, start_date, end_date, cache_dir, timeout=20):
    """Open-Meteo hourly forecast for the local dates start_date-SPINUP .. end_date+1, as a parsed dict.

    The raw response is saved as cache_dir/open-meteo-<start>-<end>-<fetched-at>.json (dates as
    requested, the stamp in UTC). Raises ForecastError when the API can't be reached or refuses."""
    a, b = start_date - SPINUP * DAY, end_date + DAY
    try:
        raw = _request(_url(lat, lon, tz_name, a, b), timeout)
    except ForecastError as e:   # padding days beyond the API's range: clamp to it and ask once more
        m = re.search(r"range from (\d{4}-\d\d-\d\d) to (\d{4}-\d\d-\d\d)", str(e))
        lo, hi = (dt.date.fromisoformat(x) for x in m.groups()) if m else (a, b)
        if not m or (max(a, lo), min(b, hi)) == (a, b) or not lo <= start_date <= end_date <= hi:
            raise
        a, b = max(a, lo), min(b, hi)
        raw = _request(_url(lat, lon, tz_name, a, b), timeout)
    try:
        data = json.loads(raw)
        _hourly(data)
    except Exception as e:
        raise ForecastError(f"Open-Meteo sent unusable data: {e}") from None
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    data["_fetched_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if cache_dir:
        path = os.path.join(cache_dir, f"open-meteo-{a}-{b}-{now:%Y%m%dT%H%M%SZ}.json")
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(path + ".part", "wb") as f:
                f.write(raw)
            os.replace(path + ".part", path)
            data["_cache"] = path
        except OSError:
            pass
    return data


def _cached(date, cache_dir):
    """Cached responses whose date range includes date, newest fetch first."""
    pat = re.compile(r"open-meteo-(\d{4}-\d\d-\d\d)-(\d{4}-\d\d-\d\d)-(\d{8}T\d{6}Z)\.json$")
    try:
        names = os.listdir(cache_dir)
    except (OSError, TypeError):
        return []
    hits = [(m[3], n) for n in names for m in [pat.match(n)] if m and m[1] <= date.isoformat() <= m[2]]
    return [(os.path.join(cache_dir, n), dt.datetime.strptime(s, "%Y%m%dT%H%M%SZ").strftime("%Y-%m-%dT%H:%M:%SZ"))
            for s, n in sorted(hits, reverse=True)]


# ------------------------------------------------------- hourly to minutes ---
def _hourly(data):
    """UTC seconds and {variable: float64 array} from an Open-Meteo response, gaps filled in time.

    ISO times are wall-clock labels at ONE fixed offset (utc_offset_seconds) for the whole response,
    even across a DST change, so they are converted with it, not with the time zone."""
    h = data["hourly"]
    tt = h["time"]
    if tt and isinstance(tt[0], str):
        th = np.array(tt, "datetime64[s]").astype(np.int64) - int(data.get("utc_offset_seconds") or 0)
    else:
        th = np.array(tt, np.int64)
    th, keep = np.unique(th.astype(float), return_index=True)
    if len(th) < 2:
        raise ValueError("fewer than two hours of data")
    hv = {}
    for k in HOURLY:
        v = np.array([np.nan if x is None else x for x in h.get(k) or [None] * len(tt)], float)[keep]
        ok = np.isfinite(v)
        if ok.all():
            pass
        elif not ok.any():
            if k not in ("visibility", "snow_depth", "wind_gusts_10m", "dew_point_2m"):
                raise ValueError(f"no {k} values")
            v = None
        elif k == "wind_direction_10m":
            v[~ok] = np.degrees(np.interp(th[~ok], th[ok], np.unwrap(np.radians(v[ok])))) % 360
        elif k == "weather_code":
            v[~ok] = v[ok][_nearest(th[ok], th[~ok])] if ok.sum() > 1 else v[ok][0]
        else:
            v[~ok] = np.interp(th[~ok], th[ok], v[ok])
        hv[k] = v
    units = data.get("hourly_units") or {}
    for k in ("wind_speed_10m", "wind_gusts_10m"):
        if hv[k] is not None:
            hv[k] = hv[k] * WIND_UNITS.get(units.get(k, "m/s"), 1.0)
    if hv["dew_point_2m"] is None:
        hv["dew_point_2m"] = _dew(hv["temperature_2m"], hv["relative_humidity_2m"])
    if hv["wind_gusts_10m"] is None:
        hv["wind_gusts_10m"] = 1.6 * hv["wind_speed_10m"]
    if hv["visibility"] is None:
        hv["visibility"] = 24000 * (1 - .95 * sm(96, 100, hv["relative_humidity_2m"]))
    if hv["snow_depth"] is None:
        hv["snow_depth"] = _snowpack(th, hv["snowfall"], hv["temperature_2m"], hv["rain"] + hv["showers"])
    return th, hv


def _bucket(inp, out, cap):
    """Water (mm) in a bucket filled at inp and emptied at out (mm/h), in one-minute steps."""
    w, r = 0.0, np.empty(len(inp))
    for i, (a, b) in enumerate(zip((inp / 60).tolist(), (out / 60).tolist())):
        w = min(cap, max(0.0, w + a - b))
        r[i] = w
    return r


def _grow(form, loss):
    """Cover 0-1 that grows toward 1 at rate form and decays at rate loss (per hour), one-minute steps."""
    f, r = 0.0, np.empty(len(form))
    for i, (a, b) in enumerate(zip((form / 60).tolist(), (loss / 60).tolist())):
        f = min(1.0, max(0.0, f + a * (1 - f) - b * f))
        r[i] = f
    return r


def _lag(x, up, down):
    """First-order follower of x with separate rates for rising and falling (per step)."""
    c, r = float(x[0]), np.empty(len(x))
    for i, v in enumerate(x.tolist()):
        c += (v - c) * (up if v > c else down)
        r[i] = c
    return r


def _build(date, tz_name, lat, lon, th, hv, source, reason, fetched_at=None):
    """DayWeather for date from hourly values at UTC seconds th (Open-Meteo names and units)."""
    t = _minutes(date, tz_name)
    if th[0] > t[0] + 3600 or th[-1] < t[-1] - 3600:
        raise ValueError(f"hourly data does not cover {date}")
    tc = th - 1800.0   # sums (and gust maxima) over the preceding hour act at the middle of that hour

    def lin(k, x=t):
        return np.interp(x, th, hv[k])

    def mid(v, x=t):
        return np.interp(x, tc, v)

    code_h = np.rint(hv["weather_code"]).astype(np.int16)
    snowy = np.isin(code_h, SNOW_CODES)
    liq = hv["rain"] + hv["showers"]
    drz = np.where((code_h >= 51) & (code_h <= 57), hv["rain"], 0.0)   # light large-scale rain
    rain_h = np.where(snowy, 0.0, liq - drz)
    snow_h = hv["snowfall"] + np.where(snowy, .7 * liq, 0.0)          # snow-coded hours: all of it is snow, cm
    code = code_h[_nearest(th, t)]
    vis = np.maximum(lin("visibility"), 1.0)
    fog = np.clip(np.log(1e4 / vis) / np.log(1e4 / 150), 0, 1) * (1 - .75 * sm(.05, .6, mid(hv["precipitation"])))
    fog = np.maximum(fog, _smooth(.65 * np.isin(code, (45, 48)), 61))
    wind = np.maximum(lin("wind_speed_10m"), 0)
    wdir = np.degrees(np.interp(t, th, np.unwrap(np.radians(hv["wind_direction_10m"])))) % 360

    # ground: wetness, rime and lying snow, integrated on a minute grid from SPINUP days before
    g = np.arange(max(_midnight(date - SPINUP * DAY, tz_name), th[0]), t[-1] + 60, 60.0)
    temp, ws = lin("temperature_2m", g), lin("wind_speed_10m", g)
    rh, cc = lin("relative_humidity_2m", g) / 100, lin("cloud_cover", g) / 100
    alt = _sun_alt(g, lat, lon)
    sun = np.sin(np.radians(np.clip(alt, 0, 90)))
    wet_in = mid(np.where(snowy, 0.0, liq), g)
    depth = np.maximum(lin("snow_depth", g), 0)
    melt = .15 * np.maximum(temp, 0) * sm(0, .01, depth)   # mm/h; degree-hours, not depth steps (1 cm, noisy)
    inp = wet_in + mid(snow_h, g) / .7 * sm(.5, 2.5, temp) + melt
    es = .6108 * np.exp(17.27 * temp / (temp + 237.3))
    dry = (.03 + .5 * sun * (1 - .7 * cc) + .2 * es * (1 - rh) + .02 * ws) * (.3 + .7 * sm(-2, 2, temp))
    dry *= 1 - .85 * sm(.02, .3, inp)   # little drying while it rains
    wet = 1 - np.exp(-_bucket(inp, dry, 4.0) / 1.2)
    clear = sm(3, -3, alt) * (1 - cc) ** 1.5 * sm(5, 2, ws)
    form = np.maximum.reduce([sm(1, -1, temp) * sm(.88, .97, rh), sm(1.5, -.5, temp) * clear,
                              code_h[_nearest(th, g)] == 48]) / 1.5
    loss = sm(1, 4, temp) / .5 + sm(0, 12, alt) * (1 - .6 * cc) * sm(-6, 0, temp) / .75 + sm(.05, .5, wet_in) / .25
    frost = _grow(form, loss)
    cover = _lag(1 - np.exp(-depth / .012), 1 - np.exp(-1 / 30), 1 - np.exp(-1 / 180))

    def f32(v):
        return np.asarray(v, np.float32)

    def at(v):
        return f32(np.interp(t, g, v))

    wdir = f32(wdir)
    wdir[wdir >= 360] = 0
    lo, mi, hi, tot = (f32(np.clip(lin(k) / 100, 0, 1))
                       for k in ("cloud_cover_low", "cloud_cover_mid", "cloud_cover_high", "cloud_cover"))
    return DayWeather(
        date=date, tz_name=tz_name, source=source, reason=reason, fetched_at=fetched_at, utc=t,
        temp_c=f32(lin("temperature_2m")), rh=f32(np.clip(lin("relative_humidity_2m") / 100, 0, 1)),
        dew_c=f32(lin("dew_point_2m")), precip_mmph=f32(mid(hv["precipitation"])), rain_mmph=f32(mid(liq)),
        snowfall_cmph=f32(mid(hv["snowfall"])), snow_depth_m=f32(np.maximum(lin("snow_depth"), 0)),
        cloud_low=lo, cloud_mid=mi, cloud_high=hi, cloud_total=tot, visibility_m=f32(vis), wind_ms=f32(wind),
        gust_ms=f32(np.maximum(mid(hv["wind_gusts_10m"]), wind)), wind_dir_deg=wdir, code=code,
        fog=f32(fog), rain=f32(1 - np.exp(-mid(rain_h) / 1.5)), snow=f32(1 - np.exp(-mid(snow_h) / .8)),
        drizzle=f32(1 - np.exp(-mid(drz) / .35)),
        thunder=f32(code_h[np.clip(np.searchsorted(th, t, "right"), 0, len(th) - 1)] >= 95),
        wet=at(wet), snow_cover=at(cover), frost=at(frost))


def _from(data, date, tz_name, lat, lon, source, reason):
    th, hv = _hourly(data)
    return _build(date, tz_name, lat, lon, th, hv, source, reason, data.get("_fetched_at"))


# --------------------------------------------------------------- synthetic ---
CLEAR, FAIR, CLOUDY, FOG, SHOWERS, RAIN = range(6)
# share of days in each state by month (Budapest-like), and how strongly each state persists
SHARE = np.array([[.12, .18, .36, .16, .02, .16], [.14, .22, .30, .12, .04, .18], [.18, .30, .20, .06, .10, .16],
                  [.20, .32, .12, .03, .18, .15], [.20, .33, .08, .02, .24, .13], [.25, .35, .06, .01, .23, .10],
                  [.32, .36, .04, .01, .20, .07], [.32, .36, .05, .02, .18, .07], [.28, .32, .10, .06, .10, .14],
                  [.22, .26, .18, .13, .05, .16], [.12, .18, .32, .18, .03, .17], [.10, .16, .38, .18, .02, .16]])
STAY = np.array([.45, .30, .55, .55, .35, .30])
TMAX = np.array([3, 5.5, 11, 17, 22, 25.5, 27.5, 27.5, 22.5, 16, 9.5, 4], float)
TMIN = np.array([-2.5, -1.5, 2, 6.5, 11.5, 15, 16.5, 16.5, 12, 7, 3, -1], float)
MID = 15.2 + 30.44 * np.arange(12)   # mid-month day of year
BURN = 14                            # days the Markov chain runs before the days it is asked for


def _clim(table, doy):
    return np.interp(doy, MID, table, period=365.25)


def _share(doy):
    p = np.array([_clim(SHARE[:, j], doy) for j in range(6)])
    return p / p.sum()


def _rng(day, salt):
    return np.random.default_rng([day.toordinal(), salt])


def _plan(first, last):
    """Daily weather plans for first..last. Each day's dice are seeded by its own date, and the chain of
    states starts BURN days early, so neighbouring days share their history and agree."""
    d = first - (BURN + 1) * DAY
    s = int(_rng(d, 0).choice(6, p=_share(_doy(d))))
    a = pack = 0.0
    pers, out = False, []
    while d < last:
        d += DAY
        r = _rng(d, 1)
        u, z, nz = r.random(20), r.standard_normal(4), r.random((6, 24))
        doy = _doy(d)
        w = .5 + .5 * np.cos(2 * np.pi * (doy - 15) / 365.25)   # 1 in mid-January, 0 in mid-July
        sh = _share(doy)
        p = sh * (1 - STAY)                # fresh picks, weighted so persistence gives the shares back
        p = p / p.sum() * (1 - STAY[s])
        p[s] += STAY[s]
        s = min(int(np.searchsorted(np.cumsum(p), u[0])), 5)
        a = .8 * a + .6 * (2.5 + w) * z[0]
        cov = 1 - np.exp(-pack / .03)
        dx = np.array([1, 0, -2.5, -.5 - 3 * w, -1, -3.5])     # state offsets, zero on average
        dn = np.array([-1.5 - w, 0, 1.5, .5 * w, .5, 1.5])
        tx = _clim(TMAX, doy) + a + dx[s] - sh @ dx - 1.5 * cov
        tn = _clim(TMIN, doy) + a + dn[s] - sh @ dn - 1.0 * cov
        snow = s in (SHOWERS, RAIN) and tx + tn < .5
        if snow:
            tx = min(tx, 1.5 - 2 * u[1])
            tn = min(tn, tx - 1.5 - 2 * u[2])
        prev, pers = pers, s == FOG and u[3] < .45 * w
        if pers:
            tx = tn + .5 + 1.5 * u[4]
        tx = max(tx, tn + .5)
        ev = []   # (start hour, hours, peak mm/h, kind: 0 rain, 1 shower, 2 thunderstorm, 3 drizzle)
        if s == RAIN:
            st, du = 1 + 19 * u[5], 3 + 8 * u[6]
            ev.append((st, du, (.4 + 1.6 * u[7]) * (1.6 - .8 * w), 0))
            if u[8] < .35:
                ev.append((st + du + 2 + 6 * u[9], 2 + 4 * u[10], .4 + 1.2 * u[11], 0))
        elif s == SHOWERS:
            if u[5] < .6 * sm(110, 150, doy) * sm(265, 225, doy):
                ev.append((13 + 6 * u[6], 1.5 + 1.5 * u[7], 6 + 14 * u[8], 2))
            else:
                for i in range(1 + int(2.99 * u[9])):
                    ev.append((10.5 + 8 * u[10 + i], .8 + 1.2 * u[13 + i], .5 + 3 * u[16 + i], 1))
        elif s == CLOUDY and u[5] < .4 * w:
            ev.append((24 * u[6], 2 + 5 * u[7], .1 + .25 * u[8], 3))
        fog = None
        if s == FOG:
            lift = 25.0 if pers else 8 + 4 * u[13] if w > .5 else 6.5 + 3 * u[13]
            fog = (-1.0 if prev else -5 + 9 * u[12], lift, 120 + 600 * u[14] ** 2)
        cl = ((0, 0, .15 * u[15]), (.1 * u[15], .2 * u[16], .4 * u[17]),
              (.7 + .3 * u[15], .3 + .6 * u[16], .2 + .6 * u[17]), (.9 if pers else .1 + .6 * w * u[15], .05, .3 * u[17]),
              (.1 + .15 * u[15], .1 + .3 * u[16], .2 + .4 * u[17]), (.5 + .3 * u[15], .5 + .4 * u[16], .5 + .4 * u[17]))[s]
        if d >= first:
            out.append(dict(d=d, s=s, tx=tx, tn=tn, snow=snow, ev=ev, fog=fog, cl=cl, nz=nz,
                            cu=(0, .1 + .2 * u[18], 0, 0, .3 + .3 * u[18], 0)[s],
                            dep=(2.5, 1.8, .8, .2, 1.2, .3)[s] + abs(z[3]),
                            wind=(2.2, 2.6, 3.0, 1.0, 3.2, 4.5)[s] * np.exp(.3 * z[1]),
                            wdir=360 * u[19] if s == FOG else (235 if s == RAIN else 315) + 40 * z[2],
                            vis=(42000, 32000, 18000, 6000, 26000, 15000)[s] * (1 - .35 * w) * (.8 + .4 * u[19])))
        total = sum(e[1] * e[2] * .62 for e in ev)
        pdh = 24 * (max(tx, 0) ** 2 / (2 * (tx - tn)) if tn < 0 else (tx + tn) / 2)
        pack = max(0.0, pack * .92 + (.007 * total if snow else 0) - .0012 * pdh)
    return out


def _diurnal(x, K, sr, tn, tx, peak=14.5):
    """Temperature at solar hours x: minimum at sunrise, maximum mid-afternoon, cooling fastest in the evening."""
    kt = np.ravel(np.column_stack([K * 24 + sr, K * 24 + peak]))
    kv = np.ravel(np.column_stack([tn, tx]))
    j = np.clip(np.searchsorted(kt, x) - 1, 0, len(kt) - 2)
    f = np.clip((x - kt[j]) / (kt[j + 1] - kt[j]), 0, 1)
    f = np.where(j % 2 == 0, f, f ** .6)
    return kv[j] + (kv[j + 1] - kv[j]) * (1 - np.cos(np.pi * f)) / 2


def _sunrise(K, lat):
    doy = np.array([_doy(EPOCH + dt.timedelta(int(k))) for k in K])
    dec = np.radians(-23.44 * np.cos(2 * np.pi * (doy + 10) / 365.25))
    return 12 - np.degrees(np.arccos(np.clip(-np.tan(np.radians(lat)) * np.tan(dec), -1, 1))) / 15, doy


def _codes(total, vis, temp, rain, showers, snowfall, frontal, storm):
    """WMO codes the way Open-Meteo assigns them: drizzle codes simply mean light rain."""
    code = np.select([total < .2, total < .5, total < .8], [0, 1, 2], 3)
    code = np.where(vis < 1000, np.where(temp < 0, 48, 45), code)
    code = np.where(rain >= .1, np.select([rain < .5, rain < 1, rain < 1.3, rain < 2.5, rain < 7.6],
                                          [51, 53, 55, 61, 63], 65), code)
    code = np.where((showers >= .1) & (showers >= rain), np.select([showers < 2.5, showers < 7.6], [80, 81], 82), code)
    code = np.where(snowfall >= .05, np.where(frontal, np.select([snowfall < .2, snowfall < 1], [71, 73], 75),
                                              np.where(snowfall < 1, 85, 86)), code)
    return np.where(storm, 95, code)


def _synthetic_hourly(date, tz_name, lat, lon):
    """Made-up hourly weather, Open-Meteo style, from 15 days before date to 2 days after."""
    t0 = _midnight(date, tz_name)
    th = np.arange(t0 - 15 * 86400, t0 + 3 * 86400 + 1, 3600.0)
    x = th / 3600 + lon / 15                    # solar hours since the epoch
    k = np.floor(x / 24).astype(int)
    hs = x - 24 * k
    plan = _plan(EPOCH + dt.timedelta(int(k[0]) - 1), EPOCH + dt.timedelta(int(k[-1]) + 1))
    K = np.array([(p["d"] - EPOCH).days for p in plan])
    i, h = k - K[0], hs.astype(int)

    def col(key):
        return np.array([p[key] for p in plan], float)

    nz = np.array([p["nz"] for p in plan])[i, :, h].T   # (6, hours) of uniform noise
    sr, _ = _sunrise(K, lat)
    temp = _diurnal(x, K, sr, col("tn"), col("tx"))
    sub = x[:, None] - np.array([.875, .625, .375, .125])
    amt, cloud_ev, cool, gust_ev = np.zeros((4, len(x))), np.zeros((3, len(x))), np.zeros(len(x)), np.zeros(len(x))
    for p, kk in zip(plan, K):
        for st, du, pk, kind in p["ev"]:
            S = kk * 24 + st
            f = (sub - S) / du
            amt[kind] += pk * np.where((f > 0) & (f < 1), np.sin(np.pi * np.clip(f, 0, 1)) ** .7, 0).mean(1)
            c, lead = (0, 0, 1, 2)[kind], (3, 3, 1.5, 2)[kind]
            cloud_ev[c] = np.maximum(cloud_ev[c], sm(S - lead, S - .3, x) * sm(S + du + 1, S + du, x))
            if kind == 2:
                env = sm(S, S + 1, x) * np.exp(-np.maximum(x - S - 1, 0) / 5)
                cool += (3 + 4 * pk / 20) * env
                gust_ev += (6 + pk / 2) * sm(S - .5, S + .5, x) * sm(S + du + .5, S + du - .5, x)
    amt *= .6 + .8 * nz[0]
    tot = amt.sum(0)
    temp = temp - cool - 1.5 * sm(.2, 2, tot)
    sf = np.where(col("snow")[i] > 0, sm(2.5, .5, temp), sm(0, -1.5, temp))   # snow days snow; others only below 0
    rain = np.round((amt[0] + amt[3]) * (1 - sf), 1)
    showers = np.round((amt[1] + amt[2]) * (1 - sf), 1)
    snowfall = np.round(tot * sf * .7, 2)
    precip = np.round(rain + showers + snowfall / .7, 1)
    fg, vmin = np.zeros(len(x)), np.full(len(x), 1e4)
    for p, kk in zip(plan, K):
        if p["fog"]:
            on, lift, vm = p["fog"]
            e = sm(kk * 24 + on - .5, kk * 24 + on + .5, x) * sm(kk * 24 + lift + .5, kk * 24 + lift - .5, x)
            fg, vmin = np.maximum(fg, e), np.where(e > 0, np.minimum(vmin, vm), vmin)
    td = np.minimum(np.interp(x, K * 24 + 12, col("tn") - col("dep")), temp - .2)
    td = np.where(tot > .05, np.maximum(td, temp - 1.2 + .9 * sm(.1, 1, tot)), td)
    td = np.where(fg > .5, temp - .1, td)
    rh = np.round(_rh(temp, td))
    cl = np.array([p["cl"] for p in plan])[i].T
    bump = sm(9, 13, hs) * sm(19, 16, hs) * col("cu")[i]
    ev = cloud_ev.T @ np.array([[.95, .95, .8], [.55, .45, .7], [.85, .8, .95]])   # frontal, shower, storm
    low = np.maximum.reduce([_smooth(cl[0] + bump + .2 * (nz[1] - .5), 5), ev[:, 0], fg])
    mid = np.maximum(_smooth(cl[1] + .2 * (nz[2] - .5), 5), ev[:, 1])
    high = np.maximum(_smooth(cl[2] + .2 * (nz[3] - .5), 5), ev[:, 2])
    low, mid, high = (np.clip(v, 0, 1) for v in (low, mid, high))
    total = 1 - (1 - low) * (1 - mid) * (1 - high)
    vis = np.exp(_smooth(np.log(col("vis")[i]), 7)) * (1 - .6 * sm(85, 98, rh))
    vis = np.minimum(np.minimum(vis, 25000 / (1 + 1.5 * (rain + showers))), 9000 / (1 + 3 * snowfall / .7))
    vis = np.exp(np.log(vis) * (1 - fg) + np.log(np.minimum(vmin, vis)) * fg)
    vis = np.clip(np.round(vis, -1), 50, 50000)
    ws = np.exp(_smooth(np.log(col("wind")[i]), 7)) * (.65 + .6 * np.clip(np.sin(np.pi * (hs - 7) / 13), 0, 1))
    ws = ws * (1 - .5 * fg) * (.85 + .3 * nz[4])
    wd = np.degrees(np.interp(x, K * 24 + 12, np.unwrap(np.radians(col("wdir"))))) + 30 * (nz[5] - .5)
    alt = _sun_alt(th, lat, lon)
    depth = _snowpack(th, snowfall, temp, rain + showers, np.sin(np.radians(np.clip(alt, 0, 90))) * (1 - total))
    code = _codes(total, vis, temp, rain, showers, snowfall, amt[0] + amt[3] >= amt[1] + amt[2], amt[2] * (1 - sf) >= 1)
    return th, dict(temperature_2m=np.round(temp, 1), relative_humidity_2m=rh, dew_point_2m=np.round(td, 1),
                    precipitation=precip, rain=rain, showers=showers, snowfall=snowfall, snow_depth=depth,
                    weather_code=code.astype(float), cloud_cover=np.round(100 * total), cloud_cover_low=np.round(100 * low),
                    cloud_cover_mid=np.round(100 * mid), cloud_cover_high=np.round(100 * high), visibility=vis,
                    wind_speed_10m=np.round(ws, 2), wind_direction_10m=np.round(wd) % 360,
                    wind_gusts_10m=np.round(ws * (1.4 + .4 * nz[0]) + gust_ev, 2))


def synthetic_day(date, tz_name=TZ, lat=LAT, lon=LON):
    """Deterministic made-up weather for date with a seasonal, Budapest-like climate."""
    th, hv = _synthetic_hourly(date, tz_name, lat, lon)
    return _build(date, tz_name, lat, lon, th, hv, "synthetic", "made-up weather seeded by the date")


def fair_day(date, tz_name=TZ):
    """A dry, calm, lightly clouded day at seasonal temperatures (never below 3 C), deterministic per date.
    For previews and release builds."""
    t0 = _midnight(date, tz_name)
    th = np.arange(t0 - 2 * 86400, t0 + 3 * 86400 + 1, 3600.0)
    x = th / 3600 + LON / 15
    hs = x % 24
    K = np.arange(np.floor(x[0] / 24) - 1, np.floor(x[-1] / 24) + 2)
    sr, doy = _sunrise(K, LAT)

    def wave(*periods):   # smooth wiggle between 0 and 1 made of a few incommensurate periods (hours)
        return .5 + .5 * np.mean([np.sin(2 * np.pi * x / q + 2.1 * n) for n, q in enumerate(periods)], 0)

    tn = np.maximum(_clim(TMIN, doy) + 1.5 * np.sin(1.7 * K), 3.5)
    tx = np.maximum(_clim(TMAX, doy) + 1.5 * np.sin(2.3 * K + 1), tn + 6)
    temp = _diurnal(x, K, sr, tn, tx)
    td = np.minimum(np.interp(x, K * 24 + 12, tn - 3), temp - 2)
    low = .14 * wave(4.3, 9.7) * sm(9, 13, hs) * sm(19, 16, hs)
    mid = .34 * wave(7.1, 17.3, 31.1) ** 2
    high = .05 + .53 * wave(5.3, 11.7, 23.9)
    total = 1 - (1 - low) * (1 - mid) * (1 - high)
    ws = 2.1 + 2.8 * np.clip(.15 + .45 * np.clip(np.sin(np.pi * (hs - 7) / 13), 0, 1) + .4 * wave(6.7, 13.3), 0, 1)
    zero = np.zeros(len(x))
    hv = dict(temperature_2m=temp, relative_humidity_2m=_rh(temp, td), dew_point_2m=td, precipitation=zero,
              rain=zero, showers=zero, snowfall=zero, snow_depth=zero,
              weather_code=np.select([total < .2, total < .5], [0, 1], 2).astype(float),
              cloud_cover=100 * total, cloud_cover_low=100 * low, cloud_cover_mid=100 * mid, cloud_cover_high=100 * high,
              visibility=22000 + 26000 * wave(9.1, 27.7), wind_speed_10m=ws,
              wind_direction_10m=(250 + 60 * np.sin(2 * np.pi * x / 61) + 40 * np.sin(2 * np.pi * x / 23.3 + 1)) % 360,
              wind_gusts_10m=1.5 * ws)
    return _build(date, tz_name, LAT, LON, th, hv, "fair", "fair weather for previews and release builds")


# ------------------------------------------------------------------ public ---
def day_weather(date, tz_name=TZ, lat=LAT, lon=LON, cache_dir=CACHE, offline=False, forecast=None):
    """Weather for one local day: the live Open-Meteo forecast (or the forecast dict passed in), else the
    newest cached forecast covering the day, else synthetic_day(). Never raises for network trouble."""
    why = "offline"
    if forecast is not None:
        try:
            return _from(forecast, date, tz_name, lat, lon, "forecast", "forecast passed in")
        except Exception as e:
            why = f"forecast passed in is unusable ({e})"
    elif not offline:
        try:
            fc = fetch_forecast(lat, lon, tz_name, date, date + AHEAD * DAY, cache_dir)
            return _from(fc, date, tz_name, lat, lon, "forecast", "fetched from Open-Meteo")
        except Exception as e:
            why = f"fetch failed: {e}"
    for path, stamp in _cached(date, cache_dir):
        try:
            with open(path) as f:
                fc = json.load(f)
            fc["_fetched_at"] = stamp
            return _from(fc, date, tz_name, lat, lon, "cache", f"{why}; using the forecast fetched {stamp}")
        except Exception:
            continue
    dw = synthetic_day(date, tz_name, lat, lon)
    dw.reason = f"{why}; no cached forecast covers {date}"
    return dw


def _spans(on, gap=0):
    """[start, end) minute runs where on is true, joining runs less than gap minutes apart."""
    d = np.diff(np.r_[0, np.asarray(on, np.int8), 0])
    out = []
    for a, b in zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()):
        if out and a - out[-1][1] < gap:
            out[-1][1] = b
        else:
            out.append([a, b])
    return out


def summary(dw):
    """One line for logs, e.g. "fog until 09:40, overcast, light rain 14-17, 6..11 C, wind SW 6 m/s"."""
    def hm(m):
        return f"{m // 60:02d}:{m % 60:02d}"

    out = []
    for name, x in (("fog", dw.fog), ("frost", dw.frost)):
        for a, b in _spans(x > .5, 30)[:2]:
            out.append(f"{name} all day" if b - a == 1440 else f"{name} until {hm(b)}" if a == 0
                       else f"{name} from {hm(a)}" if b == 1440 else f"{name} {hm(a)}-{hm(b)}")
    c = float(dw.cloud_total[420:1140].mean())
    out.append("clear" if c < .15 else "fair" if c < .4 else "partly cloudy" if c < .7
               else "mostly cloudy" if c < .9 else "overcast")
    for name, x in (("rain", np.maximum(dw.rain, dw.drizzle)), ("snow", dw.snow), ("thunder", dw.thunder)):
        for a, b in _spans(x > .05, 60)[:3]:
            r, d = float(dw.rain[a:b].max()), float(dw.drizzle[a:b].max())
            word = ("drizzle" if d > r else "rain") if name == "rain" else name
            peak, lim = {"rain": (r, (.81, .99)), "drizzle": (d, (.6, .95))}.get(word, (float(x[a:b].max()), (.71, .97)))
            size = "" if name == "thunder" else "light " if peak < lim[0] else "" if peak < lim[1] else "heavy "
            out.append(f"{size}{word} {a // 60:02d}-{-(-b // 60):02d}")
    cover = float(dw.snow_cover.max())
    if cover > .15:
        out.append("snow cover" if cover > .5 else "patchy snow")
    out.append(f"{dw.temp_c.min():.0f}..{dw.temp_c.max():.0f} C")
    r = np.radians(dw.wind_dir_deg)
    d = np.degrees(np.arctan2((dw.wind_ms * np.sin(r)).sum(), (dw.wind_ms * np.cos(r)).sum())) % 360
    out.append(f"wind {COMPASS[int((d + 22.5) // 45) % 8]} {dw.wind_ms.mean():.0f} m/s")
    if dw.gust_ms.max() >= 12:
        out[-1] += f", gusts {dw.gust_ms.max():.0f}"
    return ", ".join(out)


def main():
    ap = argparse.ArgumentParser(description="Print one day of Listening Point weather.")
    ap.add_argument("date", nargs="?", help="YYYY-MM-DD, default tomorrow")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--fair", action="store_true")
    ap.add_argument("--cache", default=CACHE)
    ap.add_argument("-v", action="store_true", help="also print every hour")
    a = ap.parse_args()
    d = dt.date.fromisoformat(a.date) if a.date else dt.datetime.now(ZoneInfo(TZ)).date() + DAY
    w = fair_day(d) if a.fair else synthetic_day(d) if a.synthetic else day_weather(d, cache_dir=a.cache, offline=a.offline)
    print(f"{d} {w.source} ({w.reason})\n{summary(w)}")
    for m in range(0, 1440, 60) if a.v else ():
        print(f"{m // 60:02d}:00 {w.temp_c[m]:5.1f}C rh {w.rh[m]:.2f} cloud {w.cloud_low[m]:.2f}/{w.cloud_mid[m]:.2f}/"
              f"{w.cloud_high[m]:.2f} vis {w.visibility_m[m]:5.0f} wind {w.wind_ms[m]:4.1f} {w.wind_dir_deg[m]:3.0f} "
              f"code {w.code[m]:2d} fog {w.fog[m]:.2f} rain {w.rain[m]:.2f} drizzle {w.drizzle[m]:.2f} "
              f"snow {w.snow[m]:.2f} thunder {w.thunder[m]:.0f} wet {w.wet[m]:.2f} cover {w.snow_cover[m]:.2f} "
              f"frost {w.frost[m]:.2f}")


if __name__ == "__main__":
    main()
