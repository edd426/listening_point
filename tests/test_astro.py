#!/usr/bin/env python3
"""Check renderers/procedural/astro.py against Skyfield + JPL DE421 reference values.

usage: ./venv/bin/python tests/test_astro.py      (from the repo root; exits 1 if any check fails)

tests/fixtures/astro_reference.json holds about 300 instants spread over 2026-2036 at Budapest, 40 days of
sun events (including the DST changes) and a refraction table, all computed with Skyfield and DE421 by a
script kept outside the repo. Everything is recomputed here in vectorised calls. Sky positions are compared
as great-circle separations, because azimuth alone blows up near the zenith; the notes give the worst
|d alt| and |d az| cos(alt). The Sun and planets go through altaz() straight from their geocentric RA/Dec,
as the renderer will use them; the Moon goes through topocentric() first.
"""
import datetime as dt
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "renderers", "procedural"))
import astro  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "astro_reference.json")
SYNODIC = 29.530589
rows = []


def check(name, err, tol, unit="deg", note=""):
    err = np.abs(np.atleast_1d(np.asarray(err, float)))
    worst = float(err.max()) if err.size else 0.0
    rows.append((name, err.size, worst, tol, unit, bool(worst <= tol), note))


def sep(lat1, lon1, lat2, lon2):
    """Great-circle separation in degrees between (lat, lon) directions given in degrees."""
    p1, p2, dl = np.radians(lat1), np.radians(lat2), np.radians(np.asarray(lon1) - lon2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return np.degrees(2 * np.arcsin(np.sqrt(np.clip(a, 0, 1))))


def wrap(x, period):
    return (np.asarray(x) + period / 2) % period - period / 2


def altaz_check(name, alt, az, ref, tol):
    ra, rz = np.array(ref["alt"]), np.array(ref["az"])
    note = "|dalt| %.4f, |daz|cos(alt) %.4f" % (np.abs(alt - ra).max(),
                                                 np.abs(wrap(az - rz, 360) * np.cos(np.radians(ra))).max())
    check(name, sep(alt, az, ra, rz), tol, note=note)


def radec_check(name, ra_h, dec, ref_ra, ref_dec, tol):
    check(name, sep(dec, ra_h * 15, np.array(ref_dec), np.array(ref_ra) * 15), tol)


def main():
    doc = json.load(open(FIXTURE))
    meta, ins = doc["meta"], doc["instants"]
    lat, lon = meta["site"]["lat"], meta["site"]["lon"]
    dts = [dt.datetime.fromisoformat(s) for s in ins["utc"]]
    jd = astro.julian_day(dts)

    # time
    check("julian_day(datetimes) vs jd_from_unix", (jd - astro.jd_from_unix(ins["unix"])) * 86400, 1e-3, "s")
    check("gmst_hours", wrap(astro.gmst_hours(jd) - ins["gmst_h"], 24) * 3600, 0.5, "s",
          "UT1 taken as UTC")
    check("lst_hours (apparent, lon 0) vs GAST", wrap(astro.lst_hours(jd, 0.0) - ins["gast_h"], 24) * 3600,
          0.5, "s")

    # sun
    s = ins["sun"]
    ra, dec, dist = astro.sun_radec(jd)
    altaz_check("sun alt/az", *astro.altaz(ra, dec, jd, lat, lon), s, 0.01)
    radec_check("sun RA/Dec (geocentric, of date)", ra, dec, s["ra_h"], s["dec"], 0.01)
    check("sun distance", dist / np.array(s["dist_au"]) - 1, 1e-4, "rel")

    # moon
    m = ins["moon"]
    ra, dec, dist = astro.moon_radec(jd)
    tra, tdec = astro.topocentric(ra, dec, dist, jd, lat, lon)
    altaz_check("moon alt/az (topocentric)", *astro.altaz(tra, tdec, jd, lat, lon), m, 0.05)
    radec_check("moon RA/Dec (geocentric, of date)", ra, dec, m["ra_h"], m["dec"], 0.05)
    radec_check("moon RA/Dec (topocentric)", tra, tdec, m["topo_ra_h"], m["topo_dec"], 0.05)
    check("moon distance", dist - np.array(m["dist_km"]), 100.0, "km")
    ill = astro.moon_illumination(jd)
    check("moon illuminated fraction", ill["fraction"] - np.array(m["fraction"]), 0.01, "")
    check("moon phase angle", ill["phase_angle_deg"] - np.array(m["phase_angle"]), 0.1)
    check("moon elongation", ill["elongation_deg"] - np.array(m["elongation"]), 0.1)
    check("moon age (days since new moon)", wrap(ill["age_days"] - np.array(m["age_days"]), SYNODIC), 0.3, "d")
    pl = np.array(m["phase_lon"])
    clear = np.abs(wrap(pl, 180)) > 0.05                     # skip instants right at new or full moon
    check("moon waxing flag (mismatches)", np.sum(ill["waxing"][clear] != (pl[clear] < 180)), 0, "count",
          "%d instants within 0.05 deg of new/full skipped" % np.sum(~clear))

    # planets
    P = astro.planets_radec(jd)
    rd, dd = [], []
    for name, ref in ins["planets"].items():
        ra, dec, dist, mag = P[name]
        altaz_check("%s alt/az" % name, *astro.altaz(ra, dec, jd, lat, lon), ref, 0.1)
        rd.append(sep(dec, ra * 15, np.array(ref["dec"]), np.array(ref["ra_h"]) * 15))
        dd.append(dist / np.array(ref["dist_au"]) - 1)
        check("%s magnitude" % name, mag - np.array(ref["mag"]), 0.3, "mag",
              "vs heliocentric-geometry ref %.3f" % np.abs(mag - np.array(ref["mag_helio"])).max())
    check("planets RA/Dec (geocentric, of date)", np.concatenate(rd), 0.1)
    check("planets distance", np.concatenate(dd), 1e-3, "rel")

    # stars
    pe = []
    for name, ref in ins["stars"].items():
        alt, az = astro.star_vectors_to_altaz(ref["ra_h"], ref["dec"], jd, lat, lon)
        altaz_check("%s alt/az" % name, alt, az, ref, 0.02)
        mra, mdec = astro.precess(ref["ra_h"], ref["dec"], jd)
        pe.append(sep(mdec, mra * 15, np.array(ref["mean_dec"]), np.array(ref["mean_ra_h"]) * 15))
    check("precess() mean RA/Dec of date", np.concatenate(pe), 0.001)

    # sun events
    groups = dict(sunrise_sunset=("sunrise", "sunset"), civil=("civil_dawn", "civil_dusk"),
                  nautical=("nautical_dawn", "nautical_dusk"),
                  astronomical=("astronomical_dawn", "astronomical_dusk"), solar_noon=("solar_noon",))
    errs, bad = {g: [] for g in groups}, []
    for rec in doc["sun_events"]:
        got = astro.sun_events(dt.date.fromisoformat(rec["date"]), rec["tz"], lat, lon)
        for g, keys in groups.items():
            for k in keys:
                want = rec[k] and dt.datetime.fromisoformat(rec[k])
                if (got[k] is None) != (want is None) or (want and got[k].utcoffset() != want.utcoffset()):
                    bad.append("%s %s" % (rec["date"], k))
                elif want:
                    errs[g].append((got[k] - want).total_seconds())
    for g, e in errs.items():
        check("sun events: %s" % g, e, 60.0, "s")
    check("sun events: missing/extra or wrong UTC offset", len(bad), 0, "count", ", ".join(bad[:3]))

    # refraction
    ra_, rr = np.array(doc["refraction"]["alt"]), np.array(doc["refraction"]["refraction_deg"])
    check("refraction vs Skyfield (Bennett), alt >= -1", astro.refraction(ra_) - rr, 0.01)
    h = np.linspace(-6, 90, 9601)
    app = h + astro.refraction(h)
    bad_refr = np.sum(np.diff(app) <= 0) + np.sum(astro.refraction(h[h <= -3]) != 0) \
        + int(abs(float(astro.refraction(90.0))) > 1e-4)
    check("refraction: taper/monotonic violations", bad_refr, 0, "count")

    # scalars give the same answers as arrays
    i = 123
    one = [astro.sun_radec(jd[i]), astro.moon_radec(jd[i]), astro.planets_radec(jd[i])["Mars"][:2],
           astro.altaz(1.0, 2.0, jd[i], lat, lon)]
    many = [astro.sun_radec(jd), astro.moon_radec(jd), astro.planets_radec(jd)["Mars"][:2],
            astro.altaz(1.0, 2.0, jd, lat, lon)]
    check("scalar jd vs array jd", [float(a) - b[i] for o, mm in zip(one, many) for a, b in zip(o, mm)],
          1e-9, "")

    w = max(len(r[0]) for r in rows)
    print("astro.py vs Skyfield/DE421: %d instants %s .. %s, %d event days, %.4f N %.4f E" % (
        len(jd), min(ins["utc"])[:10], max(ins["utc"])[:10], len(doc["sun_events"]), lat, lon))
    print("%-*s %5s %11s %10s  %-5s %s" % (w, "quantity", "n", "max err", "tol", "unit", "status"))
    for name, n, worst, tol, unit, ok, note in rows:
        print("%-*s %5d %11.5f %10.4g  %-5s %-4s %s" % (w, name, n, worst, tol, unit, ["FAIL", "ok"][ok], note))
    fails = [r[0] for r in rows if not r[5]]
    print("%d checks, %d failed%s" % (len(rows), len(fails), (": " + ", ".join(fails)) if fails else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
