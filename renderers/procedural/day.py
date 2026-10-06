"""One calendar day as every frame needs it: when each minute is, where the sun, moon and planets
are, the weather, the season, and the day's schedule of events.

Minutes are local clock minutes (0 = 00:00 ... 1439 = 23:59); index 1440 is the next midnight,
which the last keyframe needs. On DST days the clock minutes map to the real instants: the
repeated hour in October uses its first pass, the missing hour in March runs on the old offset.
"""
import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np

import astro
import events
import weather as wxmod
from mystery import Mysteries
from season import Season

BUDAPEST = dict(lat=47.4979, lon=19.0402, tz="Europe/Budapest")
PLANETS = ("Mercury", "Venus", "Mars", "Jupiter", "Saturn")


class Day:
    def __init__(self, date, lat=BUDAPEST["lat"], lon=BUDAPEST["lon"], tz=BUDAPEST["tz"],
                 weather="auto", cache_dir=None):
        self.date, self.lat, self.lon, self.tzname = date, lat, lon, tz
        self.tz = ZoneInfo(tz)
        mid = dt.datetime.combine(date, dt.time(0, 0), self.tz)
        local = [mid + dt.timedelta(minutes=int(m)) for m in range(1441)]
        self.local = local
        self.utc = [t.astimezone(dt.timezone.utc) for t in local]
        self.jd = astro.jd_from_unix(np.array([t.timestamp() for t in self.utc]))
        jd = self.jd
        self.lst = astro.lst_hours(jd, lon)

        ra, dec, _ = astro.sun_radec(jd)
        alt, az = astro.altaz(ra, dec, jd, lat, lon)
        self.sun_alt, self.sun_az = alt + astro.refraction(alt), az
        ra, dec, dist = astro.moon_radec(jd)
        ra, dec = astro.topocentric(ra, dec, dist, jd, lat, lon)
        alt, az = astro.altaz(ra, dec, jd, lat, lon)
        self.moon_alt, self.moon_az = alt + astro.refraction(alt), az
        ill = astro.moon_illumination(jd)
        # a semi-diurnal tide that follows the moon's hour angle about three hours late, with spring
        # tides near new and full moon (0 = low water, 1 = high water)
        ha = np.radians((self.lst - ra) * 15)
        spring = 0.72 + 0.28 * np.cos(2 * np.radians(np.asarray(ill["elongation_deg"], np.float64)))
        self.tide = 0.5 + 0.5 * spring * np.cos(2 * (ha - np.radians(45)))
        self.moon_frac = np.asarray(ill["fraction"], np.float64)
        self.moon_waxing = np.asarray(ill["waxing"])
        self.moon_age = float(np.asarray(ill["age_days"])[720])
        self.planets = {}
        pl = astro.planets_radec(jd)
        for name in PLANETS:
            ra, dec, _, mag = pl[name]
            alt, az = astro.altaz(ra, dec, jd, lat, lon)
            self.planets[name] = (alt + astro.refraction(alt), az, np.asarray(mag, np.float64))
        self.sun_events = astro.sun_events(date, tz, lat, lon)

        self.season = Season(date)
        self.wx = self._weather(weather, cache_dir)
        # how far the air has carried the clouds since midnight (km east and north), minute by minute
        th = np.radians(np.asarray(self.wx.wind_dir_deg, np.float64))
        v = np.asarray(self.wx.wind_ms, np.float64)
        self.drift_e = np.concatenate([[0.0], np.cumsum(-v * np.sin(th)) * 0.06])
        self.drift_n = np.concatenate([[0.0], np.cumsum(-v * np.cos(th)) * 0.06])
        self.events = events.Schedule(self)
        self.mysteries = Mysteries(self)

    def _weather(self, mode, cache_dir):
        if mode == "fair":
            return wxmod.fair_day(self.date, self.tzname)
        if mode == "synthetic":
            return wxmod.synthetic_day(self.date, self.tzname, self.lat, self.lon)
        return wxmod.day_weather(self.date, self.tzname, self.lat, self.lon, cache_dir=cache_dir,
                                 offline=(mode == "offline"))

    def at(self, m):
        """Weather at clock minute m as plain floats (minute 1440 reuses 23:59)."""
        i = min(int(m), 1439)
        w = self.wx
        return SimpleNamespace(**{k: float(getattr(w, k)[i]) for k in WX_FIELDS}, code=int(w.code[i]))

    def rain_near(self, m, span=30):
        """The heaviest rain or drizzle within half an hour either side of minute m."""
        a, b = max(0, int(m) - span), min(1440, int(m) + span)
        return float(max(self.wx.rain[a:b].max(), self.wx.drizzle[a:b].max())) if b > a else 0.0

    def stamp(self, m):
        return self.local[int(m)].strftime("%Y-%m-%d %H:%M %Z")


WX_FIELDS = ("temp_c", "rh", "precip_mmph", "rain_mmph", "snowfall_cmph", "snow_depth_m", "cloud_low",
             "cloud_mid", "cloud_high", "cloud_total", "visibility_m", "wind_ms", "gust_ms", "wind_dir_deg",
             "fog", "rain", "snow", "drizzle", "thunder", "wet", "snow_cover", "frost")
