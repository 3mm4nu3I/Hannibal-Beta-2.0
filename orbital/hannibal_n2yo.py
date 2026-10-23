"""N2YO REST API client (https://www.n2yo.com/api/).

    base   https://api.n2yo.com/rest/v1/satellite/
    auth   &apiKey=<key>  (a free key from your n2yo.com profile; SOAP keys do not work for REST)

Documented transaction limits per 60 minutes: tle 1000, positions 1000, visualpasses 100,
radiopasses 100, above 100. Cached copies are served first (they cost nothing), and live calls to the
100/h endpoints are counted locally and refused at 90 so the key is never locked out.

The key goes only in the request's query string. It is never cached, logged or printed: URLs and
exception text are redacted by hannibal_net, the cache key is derived from the path only, and the key
is registered with the secret masker as soon as it is known.
"""
import hashlib
import json
import math
import os
import re
import time
from collections import deque

from hannibal_net import Net, Result, default_net, home_location, resource_path, redact_text

BASE = "https://api.n2yo.com/rest/v1/satellite"
KEY_HELP = "press [K] in the menu to type your key, or set N2YO_API_KEY; free key: n2yo.com > your profile > API key"

# category id -> name (from the API documentation)
CATEGORIES = {
    1: "Brightest", 2: "ISS", 3: "Weather", 4: "NOAA", 5: "GOES", 6: "Earth resources", 7: "Search & rescue",
    8: "Disaster monitoring", 9: "TDRSS", 10: "Geostationary", 11: "Intelsat", 12: "Gorizont", 13: "Raduga",
    14: "Molniya", 15: "Iridium", 16: "Orbcomm", 17: "Globalstar", 18: "Amateur radio", 19: "Experimental",
    20: "GPS operational", 21: "Glonass operational", 22: "Galileo", 23: "SBAS", 24: "Navy navigation",
    25: "Russian LEO navigation", 26: "Space & Earth science", 27: "Geodetic", 28: "Engineering",
    29: "Education", 30: "Military", 31: "Radar calibration", 32: "CubeSats", 33: "XM and Sirius", 34: "TV",
    35: "Beidou", 36: "Yaogan", 37: "Westford Needles", 38: "Parus", 39: "Strela", 40: "Gonets",
    41: "Tsiklon", 42: "Tsikada", 43: "O3B Networks", 44: "Tselina", 45: "Celestis", 46: "IRNSS", 47: "QZSS",
    48: "Flock", 49: "Lemur", 50: "GPS constellation", 51: "Glonass constellation", 52: "Starlink",
    53: "OneWeb", 54: "Chinese Space Station", 55: "Qianfan", 56: "LEO", 57: "GeeSAT",
}
MILITARY, GLOBALSTAR = 30, 17
# the categories offered in the lookup menu, most interesting first
MENU_CATEGORIES = [30, 17, 44, 38, 36, 15, 50, 21, 22, 35, 52, 2, 18, 3, 4, 7, 32, 1]

TTL = {"above": 300, "tle": 6 * 3600, "positions": 10, "visualpasses": 1800, "radiopasses": 1800}
LOCAL_LIMIT = {"above": 90, "visualpasses": 90, "radiopasses": 90, "tle": 900, "positions": 900}

EARTH_R = 6371.0


def get_api_key(config=None):
    key = os.getenv("N2YO_API_KEY", "").strip()
    if key:
        return key
    try:
        from hannibal_creds import session_get
        key = session_get("n2yo_key").strip()
        if key:
            return key
    except ImportError:  # pragma: no cover
        pass
    cfg = config
    if cfg is None:
        try:
            with open(resource_path("norad_targets.json"), "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, ValueError):
            cfg = {}
    key = str((cfg or {}).get("n2yo_api_key", "")).strip()
    return "" if (not key or key.upper().startswith("YOUR_")) else key


def category_id(text):
    """'military' / '30' / 'Globalstar' -> 30 / 30 / 17, else None."""
    t = str(text).strip().lower()
    if t.isdigit():
        return int(t) if int(t) in CATEGORIES else None
    for cid, name in CATEGORIES.items():
        if name.lower() == t:
            return cid
    return None


def elevation_deg(ground_km, alt_km):
    """Elevation of a satellite at altitude alt_km whose sub-point is ground_km away (spherical Earth)."""
    gamma = ground_km / EARTH_R
    if gamma <= 1e-9:
        return 90.0
    ratio = EARTH_R / (EARTH_R + alt_km)
    return math.degrees(math.atan2(math.cos(gamma) - ratio, math.sin(gamma)))


def ground_distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def compass(az):
    names = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return names[int((float(az) % 360) / 22.5 + 0.5) % 16] if az is not None else "--"


def _f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# Altitude sanity ceiling (km). Real Earth-orbit altitudes top out far below this: the
# deepest objects we carry are the VELA pair near apogee (~160,000 km), and even the Moon
# is ~384,400 km away. N2YO sometimes serves a satalt propagated from a degenerate or
# immature element set -- near-zero mean motion, or eccentricity >= 1 (a parabolic/hyperbolic
# "escape" solution) -- which sends the derived altitude to absurd values (seen: ~2.4e12 km
# for a freshly catalogued object). The altitude is reported by N2YO, not computed here, so
# the guard belongs at ingestion: anything non-finite, negative, or above this ceiling is
# treated as unusable rather than printed as if it were a real orbit.
ALT_MAX_KM = 500_000.0


def sane_alt_km(alt):
    """Return (clean_alt_or_None, suspect_bool) for an altitude reported by N2YO.

    suspect is True when the value is missing, non-finite, negative, or above ALT_MAX_KM --
    i.e. a degenerate element set. A suspect altitude is returned as None so callers do not
    feed garbage into the elevation/geometry and do not display it as a real number.
    """
    a = _f(alt)
    if a is None or not math.isfinite(a) or a < 0.0 or a > ALT_MAX_KM:
        return None, True
    return a, False


def _utc(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(ts)))
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _problem(payload):
    """N2YO reports bad keys / limits inside a normal response: {"error": "..."}."""
    if isinstance(payload, dict) and payload.get("error"):
        return "N2YO: " + str(payload["error"])[:160]
    if not isinstance(payload, dict):
        return "N2YO returned an unexpected response"
    return ""


class N2YO:
    def __init__(self, net=None, key=None, clock=time.time):
        self.net = net or default_net()
        self._key = get_api_key() if key is None else key
        self._clock = clock
        self._live = {k: deque() for k in LOCAL_LIMIT}
        self.last_count = None      # "transactionscount" from the latest live response
        if self._key:
            try:
                from secret_masking import register_secret
                register_secret(self._key)
            except ImportError:
                pass

    @property
    def configured(self):
        return bool(self._key)

    def _budget_left(self, kind):
        now = self._clock()
        q = self._live[kind]
        while q and now - q[0] > 3600:
            q.popleft()
        return len(q) < LOCAL_LIMIT[kind]

    def _call(self, kind, path):
        """GET /<path>?apiKey=...; cache-first, budget-guarded. Returns Result(data=dict)."""
        url = f"{BASE}/{path}"
        ckey = "n2yo:" + hashlib.sha256(url.encode()).hexdigest()   # path only: the key is never part of it
        hit = self.net.peek("GET", url, ttl=TTL[kind], cache_key=ckey)
        if hit:
            return hit
        if not self._key:
            old = self.net.peek("GET", url, ttl=float("inf"), cache_key=ckey)
            if old:
                old.cached, old.stale, old.note = False, True, "no N2YO key; showing cached copy"
                return old
            return Result(None, error="no N2YO API key (" + KEY_HELP + ")")
        if not self._budget_left(kind):
            old = self.net.peek("GET", url, ttl=float("inf"), cache_key=ckey)
            if old:
                old.cached, old.stale, old.note = False, True, f"N2YO {kind} limit (100/h) reached; showing cached copy"
                return old
            return Result(None, error=f"N2YO {kind} limit reached for this hour (100/h); try again later")
        self._live[kind].append(self._clock())
        res = self.net.request("GET", url, params={"apiKey": self._key}, ttl=TTL[kind], cache_key=ckey,
                               validate=_problem, retries=2)
        if res.ok and isinstance(res.data, dict):
            info = res.data.get("info") if isinstance(res.data.get("info"), dict) else res.data
            self.last_count = info.get("transactionscount", self.last_count)
        return res

    @staticmethod
    def _obs(lat, lon, alt_km):
        return f"{float(lat):.5f}/{float(lon):.5f}/{int(round(float(alt_km) * 1000))}"

    # -- endpoints ----------------------------------------------------------
    def tle(self, norad):
        res = self._call("tle", f"tle/{int(norad)}")
        if not res.ok:
            return res
        d = res.data
        lines = [l.strip() for l in str(d.get("tle", "")).replace("\r", "").split("\n") if l.strip()]
        res.data = {"satid": d.get("info", {}).get("satid", d.get("satid")), "name": d.get("info", {}).get("satname", d.get("satname")),
                    "line1": lines[0] if lines else "", "line2": lines[1] if len(lines) > 1 else ""}
        return res

    def position(self, norad, lat=None, lon=None, alt_km=None):
        h = home_location()
        lat, lon, alt_km = (h["lat"] if lat is None else lat), (h["lon"] if lon is None else lon), (h["alt_km"] if alt_km is None else alt_km)
        res = self._call("positions", f"positions/{int(norad)}/{self._obs(lat, lon, alt_km)}/1")
        if not res.ok:
            return res
        pos = (res.data.get("positions") or [None])[0]
        if not pos:
            return Result(None, error="N2YO returned no position")
        info = res.data.get("info", {})
        alt_p, alt_p_suspect = sane_alt_km(pos.get("sataltitude"))
        res.data = {"satid": info.get("satid"), "name": info.get("satname"), "lat": _f(pos.get("satlatitude")),
                    "lon": _f(pos.get("satlongitude")), "alt_km": alt_p, "alt_suspect": alt_p_suspect, "az": _f(pos.get("azimuth")),
                    "el": _f(pos.get("elevation")), "time": _utc(pos.get("timestamp")), "up": (_f(pos.get("elevation"), -1) or -1) > 0}
        return res

    def _passes(self, kind, key, norad, lat, lon, alt_km, days, third):
        h = home_location()
        lat, lon, alt_km = (h["lat"] if lat is None else lat), (h["lon"] if lon is None else lon), (h["alt_km"] if alt_km is None else alt_km)
        days = max(1, min(10, int(days)))
        res = self._call(kind, f"{kind}/{int(norad)}/{self._obs(lat, lon, alt_km)}/{days}/{int(third)}")
        if not res.ok:
            return res
        info = res.data.get("info", {})
        rows = []
        for p in res.data.get("passes") or []:
            rows.append({"start": _utc(p.get("startUTC")), "start_az": _f(p.get("startAz")), "start_dir": p.get("startAzCompass") or compass(p.get("startAz")),
                         "max": _utc(p.get("maxUTC")), "max_el": _f(p.get("maxEl")), "max_dir": p.get("maxAzCompass") or compass(p.get("maxAz")),
                         "end": _utc(p.get("endUTC")), "end_dir": p.get("endAzCompass") or compass(p.get("endAz")),
                         "mag": (lambda m: None if m is None or m >= 99999 else m)(_f(p.get("mag"))), "duration": p.get("duration")})
        res.data = {"satid": info.get("satid"), "name": info.get("satname"), "count": info.get("passescount", len(rows)), "passes": rows}
        return res

    def visual_passes(self, norad, lat=None, lon=None, alt_km=None, days=5, min_visibility=60):
        return self._passes("visualpasses", "visual", norad, lat, lon, alt_km, days, min_visibility)

    def radio_passes(self, norad, lat=None, lon=None, alt_km=None, days=5, min_elevation=10):
        return self._passes("radiopasses", "radio", norad, lat, lon, alt_km, days, min_elevation)

    def above(self, category=MILITARY, radius=90, lat=None, lon=None, alt_km=None):
        """Satellites of a category currently above the observer, nearest first (elevation computed locally)."""
        h = home_location()
        lat, lon, alt_km = (h["lat"] if lat is None else lat), (h["lon"] if lon is None else lon), (h["alt_km"] if alt_km is None else alt_km)
        radius = max(0, min(90, int(radius)))
        category = int(category)
        res = self._call("above", f"above/{self._obs(lat, lon, alt_km)}/{radius}/{category}")
        if not res.ok:
            return res
        info = res.data.get("info", {})
        rows = []
        for s in res.data.get("above") or []:
            slat, slon = _f(s.get("satlat")), _f(s.get("satlng"))
            if slat is None or slon is None:
                continue
            alt, alt_suspect = sane_alt_km(s.get("satalt"))
            dist = ground_distance_km(lat, lon, slat, slon)
            # Without a trustworthy altitude the geometric elevation is meaningless, so leave
            # it None (the object is still "above" per N2YO's own server-side filter).
            el = round(elevation_deg(dist, alt), 1) if alt is not None else None
            rows.append({"norad": int(s.get("satid", 0) or 0), "name": str(s.get("satname") or "UNKNOWN").strip(),
                         "designator": s.get("intDesignator") or "", "launched": s.get("launchDate") or "",
                         "lat": slat, "lon": slon, "alt_km": alt, "alt_suspect": alt_suspect,
                         "distance_km": round(dist), "el": el,
                         "az": round(bearing_deg(lat, lon, slat, slon)), "dir": compass(bearing_deg(lat, lon, slat, slon))})
        # Highest elevation first; suspect rows (no usable altitude -> no elevation) sink to the bottom.
        rows.sort(key=lambda r: (r["el"] is None, -(r["el"] if r["el"] is not None else 0.0)))
        res.data = {"category": category, "category_name": CATEGORIES.get(category, str(category)),
                    "count": int(_f(info.get("satcount"), len(rows)) or len(rows)), "rows": rows}
        return res
