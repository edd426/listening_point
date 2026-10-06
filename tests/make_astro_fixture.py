"""Regenerate tests/fixtures/astro_reference.json with Skyfield + JPL DE421.

Not part of the renderer: run it in a separate venv (pip install skyfield numpy) from a directory
holding sf/de421.bsp, as  python tests/make_astro_fixture.py tests/fixtures/astro_reference.json
"""
import datetime as dt
import json
import sys
from zoneinfo import ZoneInfo

import numpy as np
import skyfield
from skyfield import almanac
from skyfield.api import Star, load, wgs84
from skyfield.earthlib import refract
from skyfield.framelib import ICRS_to_J2000
from skyfield.magnitudelib import _FUNCTIONS, _SATURN_POLE, planetary_magnitude

OUT = sys.argv[1]
LAT, LON, TZ = 47.4979, 19.0402, "Europe/Budapest"
UTC = dt.timezone.utc
eph = load("sf/de421.bsp")
ts = load.timescale()
earth, sun, moon = eph["earth"], eph["sun"], eph["moon"]
topos = wgs84.latlon(LAT, LON, elevation_m=0.0)
obs = earth + topos
PLANETS = dict(Mercury="mercury", Venus="venus", Mars="mars", Jupiter="jupiter barycenter",
               Saturn="saturn barycenter")
STARS = dict(Sirius=("06 45 08.91728", "-16 42 58.0171"), Vega=("18 36 56.33635", "+38 47 01.2802"),
             Polaris=("02 31 49.09456", "+89 15 50.7923"), Betelgeuse=("05 55 10.30536", "+07 24 25.4304"),
             Fomalhaut=("22 57 39.04625", "-29 37 20.0533"))


def sexa(s):
    sign = -1 if s.strip().startswith("-") else 1
    a, b, c = (abs(float(x)) for x in s.split())
    return sign * (a + b / 60 + c / 3600)


# ------------------------------------------------------------------ instants
rng = np.random.default_rng(20261005)
u0 = dt.datetime(2026, 1, 1, tzinfo=UTC).timestamp()
u1 = dt.datetime(2037, 1, 1, tzinfo=UTC).timestamp()
edges = np.linspace(u0, u1, 301)
unix = list(np.round(edges[:-1] + rng.random(300) * np.diff(edges)))      # stratified over 2026-2036
labels = [""] * 300
t0, t1 = ts.utc(2026, 1, 1), ts.utc(2027, 1, 1)
st, sy = almanac.find_discrete(t0, t1, almanac.seasons(eph))
for ti, yi in zip(st, sy):
    unix.append(round(ti.utc_datetime().timestamp()))
    labels.append(almanac.SEASON_EVENTS_NEUTRAL[yi] + " 2026")
pt, py = almanac.find_discrete(t0, t1, almanac.moon_phases(eph))
new = [ti for ti, yi in zip(pt, py) if yi == 0][0]
full = [ti for ti, yi in zip(pt, py) if yi == 2][0]
for ti, lab, off in ((new, "new moon", 0), (new, "new moon + 1 h", 3600), (full, "full moon", 0),
                     (full, "full moon - 1 h", -3600)):
    unix.append(round(ti.utc_datetime().timestamp()) + off)
    labels.append(lab + " " + ti.utc_strftime("%Y-%m-%d"))
unix = np.array(unix, float)
dts = [dt.datetime.fromtimestamp(u, UTC) for u in unix]
t = ts.from_datetimes(dts)
tp = ts.from_datetimes(dts)          # separate Time: reading .P caches over the method on that object


def r(x, n):
    return [round(float(v), n) for v in np.atleast_1d(x)]


def sig(x, n):
    return [float("%.*g" % (n, v)) for v in np.atleast_1d(x)]


inst = dict(label=labels, utc=[d.isoformat() for d in dts], unix=[int(u) for u in unix],
            gmst_h=r(t.gmst, 8), gast_h=r(t.gast, 8))

ga = earth.at(t)
s_geo = ga.observe(sun).apparent()
s_top = obs.at(t).observe(sun).apparent()
ra, dec, dist = s_geo.radec(epoch="date")
alt, az, _ = s_top.altaz()
inst["sun"] = dict(alt=r(alt.degrees, 5), az=r(az.degrees, 5), ra_h=r(ra.hours, 7), dec=r(dec.degrees, 6),
                   dist_au=sig(dist.au, 9))

m_geo = ga.observe(moon).apparent()
m_top = obs.at(t).observe(moon).apparent()
ra, dec, dist = m_geo.radec(epoch="date")
alt, az, _ = m_top.altaz()
tra, tdec, _ = m_top.radec(epoch="date")
# age: time since the latest new moon at or before each instant
nt, ny = almanac.find_discrete(ts.utc(2025, 12, 1), ts.utc(2037, 1, 2), almanac.moon_phases(eph))
new_unix = np.array([x.timestamp() for x in nt[ny == 0].utc_datetime()])
age = (unix - new_unix[np.searchsorted(new_unix, unix, side="right") - 1]) / 86400
inst["moon"] = dict(alt=r(alt.degrees, 5), az=r(az.degrees, 5), ra_h=r(ra.hours, 7), dec=r(dec.degrees, 6),
                    dist_km=r(dist.km, 1), topo_ra_h=r(tra.hours, 7), topo_dec=r(tdec.degrees, 6),
                    fraction=r(m_geo.fraction_illuminated(sun), 6), phase_angle=r(m_geo.phase_angle(sun).degrees, 5),
                    elongation=r(m_geo.separation_from(s_geo).degrees, 5),
                    phase_lon=r(almanac.moon_phase(eph, t).degrees, 5), age_days=r(age, 5))

inst["planets"] = {}
for name, key in PLANETS.items():
    body = eph[key]
    p_geo = ga.observe(body)
    ra, dec, dist = p_geo.apparent().radec(epoch="date")
    alt, az, _ = obs.at(t).observe(body).apparent().altaz()
    # Mallama & Hilton via Skyfield, but with the true heliocentric geometry (Skyfield puts the Sun at the SSB)
    tl = ts.tt_jd(t.tt - p_geo.light_time)
    ph = body.at(tl).position.au - sun.at(tl).position.au
    se = earth.at(t).position.au - sun.at(t).position.au
    g = p_geo.position.au
    rr, dd = np.linalg.norm(ph, axis=0), np.linalg.norm(g, axis=0)
    pa = np.degrees(np.arccos(np.sum(ph * g, 0) / (rr * dd)))
    fn = _FUNCTIONS[body.target]
    if name == "Saturn":
        lat_s = np.degrees(np.arcsin(-_SATURN_POLE @ ph / rr))
        lat_e = np.degrees(np.arcsin(-_SATURN_POLE @ g / dd))
        mh = fn(rr, dd, pa, lat_s, lat_e)
    else:
        mh = fn(rr, dd, pa)
    inst["planets"][name] = dict(alt=r(alt.degrees, 4), az=r(az.degrees, 4), ra_h=r(ra.hours, 6),
                                 dec=r(dec.degrees, 5), dist_au=sig(dist.au, 7),
                                 mag=r(planetary_magnitude(p_geo), 3), mag_helio=r(mh, 3))

inst["stars"] = {}
PB = np.einsum("ijn,jk->nik", tp.P, ICRS_to_J2000)
for name, (ras, decs) in STARS.items():
    rh, dd_ = sexa(ras), sexa(decs)
    star = Star(ra_hours=rh, dec_degrees=dd_)
    alt, az, _ = obs.at(t).observe(star).apparent().altaz()
    v = np.array([np.cos(np.radians(dd_)) * np.cos(np.radians(rh * 15)),
                  np.cos(np.radians(dd_)) * np.sin(np.radians(rh * 15)), np.sin(np.radians(dd_))])
    mv = PB @ v
    mra = np.degrees(np.arctan2(mv[:, 1], mv[:, 0])) / 15 % 24
    mdec = np.degrees(np.arcsin(mv[:, 2]))
    inst["stars"][name] = dict(ra_h=round(rh, 9), dec=round(dd_, 8), alt=r(alt.degrees, 5), az=r(az.degrees, 5),
                               mean_ra_h=r(mra, 7), mean_dec=r(mdec, 6))

# ---------------------------------------------------------------- sun events
tz = ZoneInfo(TZ)
fdt = almanac.dark_twilight_day(eph, topos)
fdt.step_days = 0.01
names = {(0, 1): "astronomical_dawn", (1, 2): "nautical_dawn", (2, 3): "civil_dawn", (3, 4): "sunrise",
         (4, 3): "sunset", (3, 2): "civil_dusk", (2, 1): "nautical_dusk", (1, 0): "astronomical_dusk"}
days = [dt.date(2026, 3, 29), dt.date(2026, 10, 25), dt.date(2027, 3, 28), dt.date(2027, 10, 31)]
days += sorted({ti.utc_datetime().astimezone(tz).date() for ti in st})
rd = np.random.default_rng(99)
days += sorted(dt.date(2026, 1, 1) + dt.timedelta(days=int(k)) for k in rd.choice(4017, 32, replace=False))
events = []
for day in days:
    a = ts.from_datetime(dt.datetime.combine(day, dt.time(0), tz))
    b = ts.from_datetime(dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0), tz))
    tt_, yy = almanac.find_discrete(a, b, fdt)
    prev, rec = int(fdt(a)), dict(date=day.isoformat(), tz=TZ)
    for ti, yi in zip(tt_, yy):
        rec[names[(prev, int(yi))]] = ti.utc_datetime().astimezone(tz).isoformat(timespec="milliseconds")
        prev = int(yi)
    tr = almanac.find_transits(obs, sun, a, b)
    rec["solar_noon"] = tr[0].utc_datetime().astimezone(tz).isoformat(timespec="milliseconds")
    for k in names.values():
        rec.setdefault(k, None)
    events.append(rec)

# --------------------------------------------------------------- refraction
ralt = [-1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 75.0, 89.0]
refr = [round(float(refract(h, 10.0, 1010.0) - h), 6) for h in ralt]

d0, d1 = np.min(t.delta_t), np.max(t.delta_t)
meta = dict(
    generator="Skyfield %s + JPL DE421 (scratch script outside the repo)" % skyfield.__version__,
    generated=dt.date.today().isoformat(),
    site=dict(lat=LAT, lon=LON, elevation_m=0.0, ellipsoid="WGS84", tz=TZ),
    time="Instants are UTC. Skyfield's built-in Delta T / UT1 predictions were used (UT1 - UTC within "
         "+-0.25 s); astro.py assumes UT1 = UTC.",
    altaz="Topocentric apparent alt/az without refraction (geometric), azimuth from north through east.",
    radec="Geocentric apparent RA/Dec of date (true equator and equinox); moon topo_* are topocentric.",
    moon="fraction/phase_angle/elongation are geocentric; phase_lon is Skyfield moon_phase (deg); age_days is "
         "the time since the previous new moon from almanac.moon_phases.",
    planets="Jupiter and Saturn are their system barycentres. mag is skyfield planetary_magnitude (Mallama & "
            "Hilton 2018, Sun placed at the solar-system barycentre); mag_helio uses the same formulas with the "
            "true heliocentric geometry.",
    stars="ICRS/J2000 positions with zero proper motion and parallax; mean_* are precessed to the mean "
          "equator and equinox of date (IAU 2006 + frame bias).",
    sun_events="Topocentric geometric altitude crossings: -0.8333 deg (sunrise/sunset) and -6/-12/-18 deg "
               "(almanac.dark_twilight_day), solar_noon from almanac.find_transits; local ISO times.",
    refraction="skyfield.earthlib.refract(alt, 10 C, 1010 hPa) - alt, degrees, for geometric altitudes.",
    delta_t_range_s=[round(float(d0), 3), round(float(d1), 3)],
    n_instants=len(unix))
doc = dict(meta=meta, instants=inst, sun_events=events, refraction=dict(alt=ralt, refraction_deg=refr))
with open(OUT, "w") as f:
    json.dump(doc, f, separators=(",", ":"))
    f.write("\n")
print("wrote", OUT, len(unix), "instants,", len(events), "event days")
