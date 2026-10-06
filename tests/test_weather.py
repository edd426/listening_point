#!/usr/bin/env python3
"""Offline tests for renderers/procedural/weather.py.

usage: ./venv/bin/python tests/test_weather.py      (from the repo root; exits 1 if any test fails)

tests/fixtures/open_meteo_sample.json is one live Open-Meteo response for Budapest, saved verbatim:
local dates 2026-10-03 .. 2026-10-09 in unix time, fetched 2026-10-05T18:06:36Z, with evening rain on
2026-10-08. The network is switched off for the whole run; fetching is tested with a fake transport.
"""
import datetime as dt
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
import urllib.error
from zoneinfo import ZoneInfo

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
import weather  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "open_meteo_sample.json")
FIXTURE_NAME = "open-meteo-2026-10-03-2026-10-09-20261005T180636Z.json"
TZ = ZoneInfo(weather.TZ)
UNIT = ("rh", "cloud_low", "cloud_mid", "cloud_high", "cloud_total", "fog", "rain", "snow", "drizzle", "thunder",
        "wet", "snow_cover", "frost")
WMO = {0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}
D = dt.date


def no_network(url, timeout):
    raise urllib.error.URLError("network disabled in tests")


weather._get = no_network
weather.RETRY_DELAYS = (0, 0)


def fixture():
    with open(FIXTURE) as f:
        return json.load(f)


def utc(y, mo, d, h=0, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc).timestamp()


def fake(t0, n, iso_offset=None, **over):
    """An Open-Meteo-shaped response of n hours from UTC second t0; keyword arrays override the defaults."""
    th = t0 + 3600 * np.arange(n)
    base = dict(temperature_2m=10.0, relative_humidity_2m=80, dew_point_2m=6.7, precipitation=0.0, rain=0.0,
                showers=0.0, snowfall=0.0, snow_depth=0.0, weather_code=2, cloud_cover=50, cloud_cover_low=20,
                cloud_cover_mid=20, cloud_cover_high=20, visibility=30000.0, wind_speed_10m=3.0,
                wind_direction_10m=200, wind_gusts_10m=6.0)
    h = {k: np.broadcast_to(np.asarray(over.get(k, v), float), (n,)).tolist() for k, v in base.items()}
    if iso_offset is None:
        h["time"] = [int(x) for x in th]
    else:   # Open-Meteo style: wall-clock labels at one fixed offset for the whole response
        h["time"] = [dt.datetime.fromtimestamp(x + iso_offset, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M") for x in th]
    return {"utc_offset_seconds": iso_offset or 0, "hourly": h}


def around(date, days_before=4, days_after=2, **over):
    t0 = weather._midnight(date - dt.timedelta(days_before), weather.TZ) // 3600 * 3600
    return t0, fake(t0, 24 * (days_before + days_after + 1), **over)


def check(dw, date, source=None):
    """Shapes, dtypes and ranges every DayWeather must satisfy."""
    assert dw.date == date and dw.tz_name == weather.TZ, (dw.date, dw.tz_name)
    assert dw.source in ("forecast", "cache", "synthetic", "fair") and dw.reason, (dw.source, dw.reason)
    if source:
        assert dw.source == source, (dw.source, dw.reason)
    assert dw.utc.shape == (1440,) and dw.utc.dtype == np.float64
    assert (np.diff(dw.utc) > 0).all(), "minute times must increase"
    for k in weather.ARRAYS:
        v = getattr(dw, k)
        assert v.shape == (1440,), (k, v.shape)
        assert v.dtype == (np.int16 if k == "code" else np.float32), (k, v.dtype)
        assert np.isfinite(v).all(), k
    for k in UNIT:
        v = getattr(dw, k)
        assert v.min() >= 0 and v.max() <= 1, (k, v.min(), v.max())
    for k in ("precip_mmph", "rain_mmph", "snowfall_cmph", "snow_depth_m", "visibility_m", "wind_ms", "gust_ms"):
        assert getattr(dw, k).min() >= 0, k
    assert set(np.unique(dw.thunder).tolist()) <= {0.0, 1.0}
    assert ((dw.wind_dir_deg >= 0) & (dw.wind_dir_deg < 360)).all()
    assert (dw.gust_ms >= dw.wind_ms).all()
    assert -45 < dw.temp_c.min() and dw.temp_c.max() < 45
    assert (dw.dew_c <= dw.temp_c + .5).all()
    assert set(np.unique(dw.code).tolist()) <= WMO, set(np.unique(dw.code).tolist()) - WMO
    assert isinstance(weather.summary(dw), str) and weather.summary(dw)


# ------------------------------------------------------------------- tests ---
def test_fixture_parses():
    fc = fixture()
    h = fc["hourly"]
    assert len(h["time"]) >= 72 and all(k in h for k in weather.HOURLY)
    th, hv = weather._hourly(fc)
    assert (np.diff(th) == 3600).all()
    for d in (D(2026, 10, 6), D(2026, 10, 7), D(2026, 10, 8)):
        dw = weather.day_weather(d, forecast=fc, cache_dir=None)
        check(dw, d, "forecast")
        # at whole local hours the minute values are the hourly instants themselves
        for m in range(0, 1440, 60):
            i = int(np.flatnonzero(th == dw.utc[m])[0])
            assert abs(dw.temp_c[m] - hv["temperature_2m"][i]) < 1e-4
            assert abs(dw.rh[m] - hv["relative_humidity_2m"][i] / 100) < 1e-6
            assert dw.code[m] == hv["weather_code"][i]


def test_fixture_rain_day():
    """2026-10-08: hourly sums are spread over their preceding hour and keep their total."""
    fc = fixture()
    th, hv = weather._hourly(fc)
    d = D(2026, 10, 8)
    dw = weather.day_weather(d, forecast=fc, cache_dir=None)
    t0, t1 = weather._midnight(d, weather.TZ), weather._midnight(d + dt.timedelta(1), weather.TZ)
    inside = (th - 3600 >= t0) & (th <= t1)
    total = float(hv["precipitation"][inside].sum())
    assert total > 1, total
    assert abs(dw.precip_mmph.sum() / 60 - total) < .05, (dw.precip_mmph.sum() / 60, total)
    k = int(np.argmax(hv["precipitation"] * inside))   # the wettest hour peaks half an hour before its stamp
    assert dw.utc[int(np.argmax(dw.precip_mmph))] == th[k] - 1800
    assert dw.rain.max() > .2 and dw.thunder.max() == 0 and dw.snow.max() == 0
    assert dw.wet[:840].max() < .05 and dw.wet[-30:].min() > .5, "dry before the rain, wet after it"
    assert "rain" in weather.summary(dw)


def test_iso_times_match_unix_times():
    """Open-Meteo's ISO labels use one fixed utc_offset_seconds for the whole response."""
    fc = fixture()
    iso = json.loads(json.dumps(fc))
    off = fc["utc_offset_seconds"]
    iso["hourly"]["time"] = [dt.datetime.fromtimestamp(t + off, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")
                             for t in fc["hourly"]["time"]]
    for d in (D(2026, 10, 6), D(2026, 10, 8)):
        a = weather.day_weather(d, forecast=fc, cache_dir=None)
        b = weather.day_weather(d, forecast=iso, cache_dir=None)
        for k in weather.ARRAYS:
            assert np.array_equal(getattr(a, k), getattr(b, k)), k


def test_minute_index():
    d = D(2026, 11, 10)
    for dw in (weather.synthetic_day(d), weather.fair_day(d), weather.day_weather(d, forecast=around(d)[1])):
        assert np.array_equal(dw.utc, weather._midnight(d, weather.TZ) + 60.0 * np.arange(1440))
        for m in (0, 1, 59, 60, 719, 1439):
            lt = dt.datetime.fromtimestamp(dw.utc[m], TZ)
            assert (lt.date(), lt.hour * 60 + lt.minute) == (d, m)


def test_wind_direction_circular():
    d = D(2026, 11, 10)
    fc = around(d, wind_direction_10m=np.where(np.arange(24 * 7) % 2, 10.0, 350.0))[1]
    dw = weather.day_weather(d, forecast=fc)
    w = dw.wind_dir_deg
    assert ((w >= 350) | (w <= 10)).all(), "350 -> 10 must turn through north"
    northish = np.minimum(w, 360 - w)
    for m in range(30, 1440, 60):
        assert northish[m] < .01, (m, w[m])   # half-way is due north
    assert {round(float(w[m])) % 360 for m in range(0, 1440, 60)} == {350, 10}
    assert np.abs(np.diff(np.unwrap(np.radians(w)))).max() < np.radians(.4)


def test_hour_alignment():
    """Instants interpolate; sums cover the preceding hour; thunder follows the hour its code describes."""
    d = D(2026, 11, 10)
    t15 = weather._midnight(d, weather.TZ) + 15 * 3600
    t0, fc = around(d)
    i = int((t15 - t0) // 3600)
    for k, v in (("precipitation", 1.2), ("rain", 1.2), ("weather_code", 95), ("wind_gusts_10m", 20.0)):
        fc["hourly"][k][i] = v
    dw = weather.day_weather(d, forecast=fc)
    p = dw.precip_mmph
    assert p[14 * 60 + 30] == np.float32(1.2) and p[:13 * 60 + 31].max() == 0 and p[15 * 60 + 30:].max() == 0
    assert abs(p.sum() / 60 - 1.2) < 1e-4
    assert dw.gust_ms[14 * 60 + 30] == np.float32(20)
    assert dw.thunder[14 * 60:15 * 60].min() == 1 and dw.thunder.sum() == 60, "thunder 14:00-15:00"
    assert dw.code[14 * 60 + 29] == 2 and dw.code[14 * 60 + 30] == 95 and dw.code[15 * 60 + 29] == 95
    assert dw.code[15 * 60 + 30] == 2, "code is the nearest hour's"


def test_snow_coded_hours_fall_as_snow():
    d = D(2027, 1, 12)
    t0, fc = around(d, temperature_2m=-1.0, dew_point_2m=-2.0, relative_humidity_2m=93)
    i = int((weather._midnight(d, weather.TZ) + 10 * 3600 - t0) // 3600)
    for k, v in (("precipitation", 0.9), ("rain", 0.5), ("snowfall", 0.3), ("weather_code", 73)):
        fc["hourly"][k][i] = v
    dw = weather.day_weather(d, forecast=fc)
    assert dw.rain.max() == 0 and dw.drizzle.max() == 0
    assert abs(dw.snow.max() - (1 - np.exp(-(0.3 + 0.7 * 0.5) / .8))) < 1e-4
    assert dw.rain_mmph.max() == np.float32(.5) and dw.snowfall_cmph.max() == np.float32(.3)


def test_dst_fall_back():
    d = D(2026, 10, 25)
    ramp = dict(temperature_2m=.01 * np.arange(24 * 7), dew_point_2m=.01 * np.arange(24 * 7) - 3)
    t0, fc = around(d, **ramp)
    dw = weather.day_weather(d, forecast=fc)
    check(dw, d, "forecast")
    assert dw.utc[0] == utc(2026, 10, 24, 22)
    assert dw.utc[150] == utc(2026, 10, 25, 0, 30), "02:30 is its first pass (CEST)"
    assert dw.utc[179] == utc(2026, 10, 25, 0, 59) and dw.utc[180] == utc(2026, 10, 25, 2)
    assert dw.utc[1439] == utc(2026, 10, 25, 22, 59)
    assert np.allclose(dw.temp_c, .01 * (dw.utc - t0) / 3600, atol=1e-5)
    iso = around(d, iso_offset=7200, **ramp)[1]
    assert np.array_equal(weather.day_weather(d, forecast=iso).temp_c, dw.temp_c)
    for f in (weather.synthetic_day, weather.fair_day):
        check(f(d), d)


def test_dst_spring_forward():
    d = D(2027, 3, 28)
    ramp = dict(temperature_2m=.01 * np.arange(24 * 7), dew_point_2m=.01 * np.arange(24 * 7) - 3)
    t0, fc = around(d, **ramp)
    dw = weather.day_weather(d, forecast=fc)
    check(dw, d, "forecast")
    assert dw.utc[119] == utc(2027, 3, 28, 0, 59) and dw.utc[180] == utc(2027, 3, 28, 1)
    gap = dw.utc[120:180]
    assert (gap > dw.utc[119]).all() and (gap < dw.utc[180]).all(), "02:00-02:59 is filled between its neighbours"
    t = dw.temp_c
    assert (t[120:180] >= min(t[119], t[180]) - 1e-6).all() and (t[120:180] <= max(t[119], t[180]) + 1e-6).all()
    assert np.allclose(t, .01 * (dw.utc - t0) / 3600, atol=1e-5)
    assert dw.utc[1439] == utc(2027, 3, 28, 21, 59)
    iso = around(d, iso_offset=3600, **ramp)[1]
    assert np.array_equal(weather.day_weather(d, forecast=iso).temp_c, dw.temp_c)
    for f in (weather.synthetic_day, weather.fair_day):
        check(f(d), d)


def test_synthetic_deterministic():
    for d in (D(2026, 12, 24), D(2027, 7, 4), D(2027, 3, 28)):
        a, b = weather.synthetic_day(d), weather.synthetic_day(d)
        check(a, d, "synthetic")
        for k in weather.ARRAYS:
            assert np.array_equal(getattr(a, k), getattr(b, k)), (d, k)
    a, b = weather.synthetic_day(D(2027, 7, 4)), weather.synthetic_day(D(2027, 7, 5))
    assert not np.array_equal(a.temp_c, b.temp_c)
    assert abs(float(b.temp_c[0]) - float(a.temp_c[-1])) < .5, "consecutive days join at midnight"


SEASON = {}


def season(first, last):
    days = []
    d = first
    while d <= last:
        if d not in SEASON:
            SEASON[d] = weather.synthetic_day(d)
        days.append(SEASON[d])
        d += dt.timedelta(1)
    return days


def test_synthetic_winter():
    days = season(D(2026, 12, 1), D(2027, 2, 28))
    for dw in days[::15]:
        check(dw, dw.date, "synthetic")
    snow = [dw.snowfall_cmph.sum() / 60 >= 1 for dw in days]
    fog = [dw.fog.max() > .5 for dw in days]
    lying = [dw.snow_cover[720] > .5 for dw in days]
    assert 1 <= sum(snow) <= 30, sum(snow)
    assert 3 <= sum(fog) <= 60, sum(fog)
    run = max(len(m) for m in re.findall("1+", "".join("1" if x else "0" for x in lying)) or [""])
    assert run >= 3, f"snow should lie for several days in a row (longest run {run})"
    jan = [dw for dw in days if dw.date.month == 1]
    assert -9 < np.mean([dw.temp_c.min() for dw in jan]) < 2 and -3 < np.mean([dw.temp_c.max() for dw in jan]) < 9
    assert any(dw.frost.max() > .5 for dw in days)
    assert any("fog" in weather.summary(dw) for dw in days)


def test_synthetic_summer():
    days = season(D(2027, 6, 1), D(2027, 8, 31))
    thunder = [dw.thunder.sum() > 0 for dw in days]
    assert 1 <= sum(thunder) <= 40, sum(thunder)
    assert all(dw.snow.max() == 0 and dw.frost.max() == 0 and dw.snow_cover.max() == 0 for dw in days)
    jul = [dw for dw in days if dw.date.month == 7]
    assert 22 < np.mean([dw.temp_c.max() for dw in jul]) < 34 and 10 < np.mean([dw.temp_c.min() for dw in jul]) < 21


def test_synthetic_mostly_dry():
    days = season(D(2026, 12, 1), D(2027, 2, 28)) + season(D(2027, 6, 1), D(2027, 8, 31))
    days += [weather.synthetic_day(D(2027, 3, 1) + dt.timedelta(i)) for i in range(0, 92, 3)]
    days += [weather.synthetic_day(D(2026, 9, 1) + dt.timedelta(i)) for i in range(0, 91, 3)]
    dry = sum(dw.rain.max() == 0 for dw in days)
    assert dry > .6 * len(days), (dry, len(days))


def test_fair_day():
    for d in (D(2027, 1, 15), D(2027, 7, 15), D(2026, 10, 25), D(2027, 3, 28), D(2026, 12, 24)):
        a, b = weather.fair_day(d), weather.fair_day(d)
        check(a, d, "fair")
        for k in weather.ARRAYS:
            assert np.array_equal(getattr(a, k), getattr(b, k)), (d, k)
        for k in ("precip_mmph", "rain_mmph", "snowfall_cmph", "snow_depth_m", "fog", "rain", "snow", "drizzle",
                  "thunder", "wet", "snow_cover", "frost"):
            assert getattr(a, k).max() == 0, (d, k)
        assert a.cloud_low.max() <= .15 and a.cloud_mid.max() <= .35 and a.cloud_high.max() <= .6
        assert a.cloud_high.max() - a.cloud_high.min() > .05 and a.cloud_mid.max() - a.cloud_mid.min() > .02
        assert a.wind_ms.min() >= 2 and a.wind_ms.max() <= 5
        assert a.temp_c.min() > 3 and a.visibility_m.min() >= 20000
        turn = np.degrees(np.abs(np.diff(np.unwrap(np.radians(a.wind_dir_deg))))) / (np.diff(a.utc) / 60)
        assert turn.max() < .5 and np.ptp(np.unwrap(np.radians(a.wind_dir_deg))) > np.radians(5), (d, turn.max())
        assert not any(w in weather.summary(a) for w in ("rain", "drizzle", "snow", "fog", "frost", "thunder"))
    assert not np.array_equal(weather.fair_day(D(2027, 7, 15)).cloud_high, weather.fair_day(D(2027, 7, 16)).cloud_high)
    jan, jul = weather.fair_day(D(2027, 1, 15)), weather.fair_day(D(2027, 7, 15))
    assert jul.temp_c.mean() > jan.temp_c.mean() + 10, "seasonal temperatures"


def test_offline_and_cache():
    tmp = tempfile.mkdtemp()
    try:
        d = D(2026, 10, 7)
        dw = weather.day_weather(d, offline=True, cache_dir=tmp)
        check(dw, d, "synthetic")
        assert "offline" in dw.reason
        shutil.copy(FIXTURE, os.path.join(tmp, FIXTURE_NAME))
        shutil.copy(FIXTURE, os.path.join(tmp, "open-meteo-2026-10-03-2026-10-09-20261001T000000Z.json"))
        with open(os.path.join(tmp, "open-meteo-2026-10-03-2026-10-09-20261006T000000Z.json"), "w") as f:
            f.write("{not json")
        dw = weather.day_weather(d, offline=True, cache_dir=tmp)
        check(dw, d, "cache")
        assert dw.fetched_at == "2026-10-05T18:06:36Z", dw.fetched_at   # newest readable file wins
        ref = weather.day_weather(d, forecast=fixture())
        for k in weather.ARRAYS:
            assert np.array_equal(getattr(dw, k), getattr(ref, k)), k
        dw = weather.day_weather(d, cache_dir=tmp)            # the network is down
        assert dw.source == "cache" and "fetch failed" in dw.reason, dw.reason
        dw = weather.day_weather(D(2026, 12, 1), cache_dir=tmp)
        assert dw.source == "synthetic" and "fetch failed" in dw.reason, dw.reason
        dw = weather.day_weather(d, forecast={"hourly": {}}, cache_dir=tmp)
        assert dw.source == "cache" and "unusable" in dw.reason, dw.reason
        dw = weather.day_weather(D(2026, 12, 1), forecast=fixture(), cache_dir=None)
        assert dw.source == "synthetic", "a forecast that misses the day is not used"
    finally:
        shutil.rmtree(tmp)


class Fake:
    """Stands in for weather._get: plays a script of exceptions and bodies, records the URLs."""

    def __init__(self, *script):
        self.script, self.urls = list(script), []

    def __call__(self, url, timeout):
        self.urls.append(url)
        x = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(x, Exception):
            raise x
        return x


def http_error(code, reason):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(json.dumps({"error": True, "reason": reason}).encode()))


def test_fetch_retries_and_caches():
    raw = open(FIXTURE, "rb").read()
    tmp = tempfile.mkdtemp()
    try:
        weather._get = f = Fake(urllib.error.URLError("down"), urllib.error.URLError("still down"), raw)
        fc = weather.fetch_forecast(weather.LAT, weather.LON, weather.TZ, D(2026, 10, 6), D(2026, 10, 8), tmp)
        assert len(f.urls) == 3, "two retries"
        u = f.urls[0]
        for part in ("latitude=47.4979", "longitude=19.0402", "timezone=Europe%2FBudapest", "wind_speed_unit=ms",
                     "start_date=2026-10-03", "end_date=2026-10-09", "timeformat=unixtime"):
            assert part in u, part
        assert all(k in u for k in weather.HOURLY) and u.startswith("https://api.open-meteo.com/v1/forecast?")
        names = os.listdir(tmp)
        assert len(names) == 1 and re.fullmatch(r"open-meteo-2026-10-03-2026-10-09-\d{8}T\d{6}Z\.json", names[0]), names
        assert open(os.path.join(tmp, names[0]), "rb").read() == raw, "the cache holds the raw response"
        assert fc["hourly"]["time"] == fixture()["hourly"]["time"] and fc["_fetched_at"].endswith("Z")
        dw = weather.day_weather(D(2026, 10, 7), cache_dir=tmp)    # the fake keeps answering with the fixture
        assert dw.source == "forecast" and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", dw.fetched_at), dw.reason

        weather._get = f = Fake(urllib.error.URLError("down"))
        try:
            weather.fetch_forecast(weather.LAT, weather.LON, weather.TZ, D(2026, 10, 6), D(2026, 10, 6), tmp)
            raise AssertionError("no exception")
        except weather.ForecastError as e:
            assert "3 attempts" in str(e) and "down" in str(e), e
        assert len(f.urls) == 3

        # a padding day past the forecast horizon: clamp to the range the API names, ask once more
        weather._get = f = Fake(http_error(400, "Parameter 'end_date' is out of allowed range from 2026-07-04 to 2026-10-08"), raw)
        weather.fetch_forecast(weather.LAT, weather.LON, weather.TZ, D(2026, 10, 6), D(2026, 10, 8), None)
        assert len(f.urls) == 2 and "end_date=2026-10-08" in f.urls[1], f.urls
        # the wanted day itself is out of range: no retries, a clear error, and day_weather falls back
        weather._get = f = Fake(http_error(400, "Parameter 'start_date' is out of allowed range from 2026-07-04 to 2026-10-20"))
        try:
            weather.fetch_forecast(weather.LAT, weather.LON, weather.TZ, D(2026, 11, 30), D(2026, 11, 30), None)
            raise AssertionError("no exception")
        except weather.ForecastError as e:
            assert "HTTP 400" in str(e) and "out of allowed range" in str(e), e
        assert len(f.urls) == 1
        weather._get = Fake(http_error(400, "Parameter 'start_date' is out of allowed range from 2026-07-04 to 2026-10-20"))
        dw = weather.day_weather(D(2026, 11, 30), cache_dir=tmp)
        assert dw.source == "synthetic" and "out of allowed range" in dw.reason, dw.reason
    finally:
        weather._get = no_network
        shutil.rmtree(tmp)


def test_summary():
    fc = fixture()
    s = weather.summary(weather.day_weather(D(2026, 10, 8), forecast=fc))
    assert re.search(r"rain \d\d-\d\d", s) and "wind" in s and " C" in s, s
    fog = [dw for dw in season(D(2026, 12, 1), D(2027, 2, 28)) if dw.fog.max() > .5]
    assert fog and all("fog" in weather.summary(dw) for dw in fog)
    assert repr(fog[0]).startswith("<DayWeather 20")


def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = []
    for name, f in tests:
        t0 = time.time()
        try:
            f()
            print(f"ok    {name} ({time.time() - t0:.1f}s)")
        except Exception:
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"{len(tests) - len(failed)}/{len(tests)} passed" + (": failed " + ", ".join(failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
