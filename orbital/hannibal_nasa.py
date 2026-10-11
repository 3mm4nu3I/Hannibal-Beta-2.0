"""NASA / JPL Solar System Dynamics clients.

  Horizons          https://ssd.jpl.nasa.gov/api/horizons.api         ephemerides (observer, vectors)
  Small-body sats   https://ssd-api.jpl.nasa.gov/sb_sat.api           moons of asteroids / comets
  Radar astrometry  https://ssd-api.jpl.nasa.gov/sb_radar.api         radar delay / Doppler measurements
  Periodic orbits   https://ssd-api.jpl.nasa.gov/periodic_orbits.api  three-body periodic orbit families

No API key is needed for any of these (they are open JPL services). Everything goes
through hannibal_net, so URLs/errors are masked, responses are cached and calls are
spaced out politely.

JPL quirk handled here: nearly every number comes back as a *string*
("count": "6", "i": "93.4"), sometimes with padding (" 1.02e+00"), so all numeric
fields go through num().
"""
import math
import re
from datetime import datetime, timedelta, timezone

from hannibal_net import Net, Result, default_net, home_location

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
SB_SAT_URL = "https://ssd-api.jpl.nasa.gov/sb_sat.api"
SB_RADAR_URL = "https://ssd-api.jpl.nasa.gov/sb_radar.api"
PERIODIC_URL = "https://ssd-api.jpl.nasa.gov/periodic_orbits.api"

AU_KM = 149_597_870.7

# Horizons major-body ids
BODIES = {
    "sun": "10", "moon": "301", "mercury": "199", "venus": "299", "mars": "499",
    "jupiter": "599", "saturn": "699", "uranus": "799", "neptune": "899", "pluto": "999",
    "earth": "399",
}
SKY_BODIES = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"]

# Families that REQUIRE a libration point (from the periodic_orbits docs)
FAMILIES = ["halo", "vertical", "axial", "lyapunov", "longp", "short", "butterfly", "dragonfly",
            "resonant", "dro", "dpo", "lpo"]
LIBR_REQUIRED = {"lyapunov": range(1, 6), "halo": range(1, 4), "longp": range(4, 6),
                 "short": range(4, 6), "axial": range(1, 6), "vertical": range(1, 6)}

TTL_SKY = 600
TTL_EPHEM = 3600
TTL_SMALLBODY = 7 * 86400
TTL_RADAR = 86400
TTL_PERIODIC = 7 * 86400


def num(value, default=None):
    """float() that tolerates JPL's padded strings, blanks and nulls."""
    try:
        if value is None:
            return default
        text = str(value).strip()
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------- Horizons ----
def _q(value):
    """Horizons wants string values wrapped in single quotes (COMMAND='499')."""
    return "'" + str(value) + "'"


def resolve_command(text):
    """Turn user input into a Horizons COMMAND value.

    mars / moon / sun ...  -> major-body id          'id:499' / 'MB' pass through
    433 / 99942            -> small body by IAU number  ('433;')
    Apophis                -> small body by name        ('Apophis;')
    1999 AN10              -> small body by designation ('DES=1999 AN10;')
    """
    t = str(text or "").strip()
    if not t:
        raise ValueError("empty target")
    if t.lower() in BODIES:
        return BODIES[t.lower()]
    if t.lower().startswith("id:"):
        return t[3:].strip()
    if t.upper() == "MB" or ";" in t or "=" in t:
        return t
    if re.fullmatch(r"\d+", t):
        return t + ";"
    if re.fullmatch(r"\d{4}\s?[A-Za-z]{2}\d*", t):
        return f"DES={t.upper()};"
    return t + ";"


def extract_table(result_text):
    """Parse the CSV table between $$SOE and $$EOE of a Horizons CSV_FORMAT result.

    The header is the nearest comma-containing line above $$SOE. Returns a list of
    dicts keyed by stripped header names (blank headers -> '_flag<N>'), or [] if
    there is no table.
    """
    lines = str(result_text).splitlines()
    try:
        soe = next(i for i, l in enumerate(lines) if l.strip() == "$$SOE")
        eoe = next(i for i, l in enumerate(lines) if l.strip() == "$$EOE")
    except StopIteration:
        return []
    header = None
    for l in reversed(lines[:soe]):
        s = l.strip()
        if not s or set(s) <= {"*"}:
            continue
        if "," in s:
            header = s
        break
    if header is None:
        return []
    names = [h.strip() for h in header.split(",")]
    if names and names[-1] == "":
        names.pop()
    names = [n or f"_flag{i}" for i, n in enumerate(names)]
    rows = []
    for l in lines[soe + 1:eoe]:
        if not l.strip():
            continue
        cells = [c.strip() for c in l.split(",")]
        if cells and cells[-1] == "":
            cells.pop()
        rows.append(dict(zip(names, cells)))
    return rows


def _pick(row, *prefixes):
    """First column whose header starts with any prefix (case-insensitive)."""
    for key in row:
        low = key.lower()
        if any(low.startswith(p.lower()) for p in prefixes):
            return row[key]
    return None


def _horizons_error(payload):
    """Horizons reports problems either in 'error' or inside the text. Return a short message or ''."""
    if not isinstance(payload, dict):
        return "unexpected Horizons response"
    if payload.get("error"):
        return str(payload["error"])[:200]
    text = str(payload.get("result", ""))
    if "$$SOE" in text:
        return ""
    for marker in ("No matches found", "Multiple major-bodies match", "Matching small-bodies",
                   "No ephemeris", "ERROR", "Cannot", "cannot"):
        if marker in text:
            snippet = " | ".join(l.strip() for l in text.splitlines() if l.strip())[:300]
            return snippet
    return "Horizons returned no ephemeris table"


class Horizons:
    def __init__(self, net=None):
        self.net = net or default_net()

    def _call(self, params, ttl):
        res = self.net.get_json(HORIZONS_URL, params=params, ttl=ttl)
        if res.error:
            return res
        err = _horizons_error(res.data)
        if err:
            return Result(None, error=err)
        return res

    def observer(self, target, lat, lon, alt_km=0.0, start=None, stop=None, step="10 m",
                 quantities="4,9,20", ttl=TTL_SKY):
        """Apparent az/el, magnitude and range for `target` as seen from a ground site.

        Returns Result(data=list of row dicts) with Horizons' own column names
        (e.g. 'Azi_(a-app)', 'Elev_(a-app)', 'APmag', 'delta').
        """
        now = datetime.now(timezone.utc)
        start = start or (now - timedelta(minutes=now.minute % 10, seconds=now.second,
                                          microseconds=now.microsecond)).strftime("%Y-%m-%d %H:%M")
        if stop is None:
            stop = (datetime.strptime(start, "%Y-%m-%d %H:%M") + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M")
        params = {
            "format": "json", "COMMAND": _q(resolve_command(target)), "OBJ_DATA": _q("NO"),
            "MAKE_EPHEM": _q("YES"), "EPHEM_TYPE": _q("OBSERVER"), "CENTER": _q("coord@399"),
            "COORD_TYPE": _q("GEODETIC"), "SITE_COORD": _q(f"{lon},{lat},{alt_km}"),
            "START_TIME": _q(start), "STOP_TIME": _q(stop), "STEP_SIZE": _q(step),
            "QUANTITIES": _q(quantities), "ANG_FORMAT": _q("DEG"), "CSV_FORMAT": _q("YES"),
        }
        res = self._call(params, ttl)
        if not res.ok:
            return res
        rows = extract_table(res.data.get("result", ""))
        if not rows:
            return Result(None, error="Horizons returned no observer rows")
        res.data = rows
        return res

    def vectors(self, target, center="500@399", start=None, stop=None, step="1 d", ttl=TTL_EPHEM):
        """Geometric state vectors (km, km/s) of `target` relative to `center` (default: Earth centre)."""
        now = datetime.now(timezone.utc)
        start = start or now.strftime("%Y-%m-%d")
        stop = stop or (now + timedelta(days=2)).strftime("%Y-%m-%d")
        params = {
            "format": "json", "COMMAND": _q(resolve_command(target)), "OBJ_DATA": _q("NO"),
            "MAKE_EPHEM": _q("YES"), "EPHEM_TYPE": _q("VECTORS"), "CENTER": _q(center),
            "START_TIME": _q(start), "STOP_TIME": _q(stop), "STEP_SIZE": _q(step),
            "VEC_TABLE": _q("3"), "OUT_UNITS": _q("KM-S"), "CSV_FORMAT": _q("YES"),
        }
        res = self._call(params, ttl)
        if not res.ok:
            return res
        rows = extract_table(res.data.get("result", ""))
        if not rows:
            return Result(None, error="Horizons returned no vector rows")
        res.data = rows
        return res

    def sky_now(self, lat=None, lon=None, alt_km=None, bodies=None):
        """Sun/Moon/planets as seen from home. Returns (rows, errors).

        rows: [{name, az, el, mag, range_au, range_km, up, as_of}]
        """
        home = home_location()
        lat = home["lat"] if lat is None else lat
        lon = home["lon"] if lon is None else lon
        alt_km = home["alt_km"] if alt_km is None else alt_km
        out, errors = [], []
        for name in (bodies or SKY_BODIES):
            res = self.observer(name, lat, lon, alt_km)
            if not res.ok:
                errors.append(f"{name}: {res.error}")
                continue
            row = res.data[0]
            az, el = num(_pick(row, "azi")), num(_pick(row, "elev"))
            delta = num(_pick(row, "delta"))
            out.append({
                "name": name.title(), "az": az, "el": el, "mag": num(_pick(row, "apmag")),
                "range_au": delta, "range_km": delta * AU_KM if delta is not None else None,
                "up": (el is not None and el > 0), "as_of": _pick(row, "date") or "",
                "stale": res.stale,
            })
        return out, errors


# --------------------------------------------------- small bodies (SBDB) ----
class SmallBody:
    def __init__(self, net=None):
        self.net = net or default_net()

    def satellites(self, des=None, spk=None, kind=None, orbit=True, phys=False):
        """Moons of asteroids/comets. Returns Result(data=list of normalized dicts)."""
        params = {}
        if des:
            params["des"] = des
        if spk:
            params["spk"] = spk
        if kind:
            params["kind"] = kind
        if orbit:
            params["orb"] = "1"
        if phys:
            params["phys-par"] = "1"
        res = self.net.get_json(SB_SAT_URL, params=params, ttl=TTL_SMALLBODY)
        if not res.ok:
            return res
        if not isinstance(res.data, dict) or not isinstance(res.data.get("data"), list):
            return Result(None, error="unexpected sb_sat response shape")
        rows = []
        for rec in res.data["data"]:
            sat, orb = rec.get("sat") or {}, rec.get("orbit") or {}
            rows.append({
                "name": sat.get("sat_fullname") or sat.get("iau_name") or sat.get("pdes"),
                "primary": sat.get("pdes"), "class": sat.get("class"), "kind": sat.get("kind"),
                "confirmed": sat.get("confirmed"), "ref": sat.get("ref"),
                "a_km": num(orb.get("a")), "e": num(orb.get("e")), "i_deg": num(orb.get("i")),
                "period_d": num(orb.get("per")), "epoch_jd": num(orb.get("tp")),
                "phys": rec.get("phys_par"),
            })
        res.data = rows
        return res

    def browse(self, cls=None, query=None, kind=None, confirmed="all"):
        """Every small body with known satellites, grouped by primary (sb_sat with no designation).

        Returns Result(data={'moons': N, 'bodies': [...]}) sorted by number of moons then name.
        cls: class code (MBA, TNO, APO, ...); query: text found in a primary or moon name;
        kind: 'a' asteroids / 'c' comets; confirmed: 'all' | 'Y' | 'N'. One cached request (7 days).
        """
        params = {"orb": "1", "fullname": "1", "class": "1"}
        res = self.net.get_json(SB_SAT_URL, params=params, ttl=TTL_SMALLBODY)
        if not res.ok:
            return res
        if not isinstance(res.data, dict) or not isinstance(res.data.get("data"), list):
            return Result(None, error="unexpected sb_sat response shape")
        groups, total = {}, 0
        q = str(query or "").strip().lower()
        for rec in res.data["data"]:
            sat, orb = rec.get("sat") or {}, rec.get("orbit") or {}
            if cls and str(sat.get("class", "")).upper() != str(cls).upper():
                continue
            if kind and not str(sat.get("kind", "")).lower().startswith(str(kind).lower()):
                continue
            if confirmed in ("Y", "N") and sat.get("confirmed") != confirmed:
                continue
            primary = " ".join(str(sat.get("fullname") or sat.get("pdes") or "").split())
            moon = {"name": sat.get("sat_fullname") or sat.get("iau_name") or "unnamed", "confirmed": sat.get("confirmed"),
                    "a_km": num(orb.get("a")), "e": num(orb.get("e")), "i_deg": num(orb.get("i")),
                    "period_d": num(orb.get("per")), "ref": sat.get("ref")}
            if q and q not in primary.lower() and q not in str(moon["name"]).lower():
                continue
            g = groups.setdefault(str(sat.get("pdes")), {"pdes": str(sat.get("pdes")), "name": primary, "class": sat.get("class"),
                                                           "class_name": sat.get("class_name"), "kind": sat.get("kind"), "moons": []})
            g["moons"].append(moon)
            total += 1
        bodies = sorted(groups.values(), key=lambda g: (-len(g["moons"]), g["name"]))
        res.data = {"moons": total, "bodies": bodies}
        return res

    def radar(self, des=None, spk=None, kind=None, limit=25, observer=True):
        """Radar astrometry (delay in us / Doppler in Hz), newest first.

        Returns Result(data={'count': int, 'rows': [...]}) -- rows are trimmed to `limit`
        (an unfiltered query returns thousands of rows).
        """
        params = {"fullname": "1"}
        if observer:
            params["observer"] = "1"
        if des:
            params["des"] = des
        if spk:
            params["spk"] = spk
        if kind:
            params["kind"] = kind
        res = self.net.get_json(SB_RADAR_URL, params=params, ttl=TTL_RADAR)
        if not res.ok:
            return res
        d = res.data
        if not isinstance(d, dict) or not isinstance(d.get("fields"), list) or not isinstance(d.get("data"), list):
            return Result(None, error="unexpected sb_radar response shape")
        fields = d["fields"]
        rows = [dict(zip(fields, r)) for r in d["data"]]
        for r in rows:
            r["value"], r["sigma"] = num(r.get("value")), num(r.get("sigma"))
            r["kind_of"] = {"us": "delay", "Hz": "doppler"}.get(str(r.get("units")), str(r.get("units")))
        rows.sort(key=lambda r: str(r.get("epoch", "")), reverse=True)
        res.data = {"count": int(num(d.get("count"), len(rows))), "rows": rows[:limit]}
        return res


# ------------------------------------------------- three-body periodic orbits ----
class PeriodicOrbits:
    def __init__(self, net=None):
        self.net = net or default_net()

    @staticmethod
    def validate(system, family, libr=None, branch=None):
        """Return an error string or ''. Catches the common mistakes before a round trip."""
        if not re.fullmatch(r"[a-z0-9]+-[a-z0-9]+", str(system or "").lower()):
            return "system must look like 'earth-moon' (primary-secondary)"
        if family not in FAMILIES:
            return f"family must be one of: {', '.join(FAMILIES)}"
        if family in LIBR_REQUIRED:
            if libr is None:
                allowed = LIBR_REQUIRED[family]
                return f"family '{family}' needs a libration point ({allowed.start}-{allowed.stop - 1})"
            if int(libr) not in LIBR_REQUIRED[family]:
                allowed = LIBR_REQUIRED[family]
                return f"family '{family}' only supports L{allowed.start}-L{allowed.stop - 1}"
        return ""

    def query(self, system, family, libr=None, branch=None, periodmin=None, periodmax=None,
              periodunits=None, jacobimin=None, jacobimax=None, stabmin=None, stabmax=None, limit=10):
        err = self.validate(system, family, libr, branch)
        if err:
            return Result(None, error=err)
        params = {"sys": system.lower(), "family": family}
        for key, val in (("libr", libr), ("branch", branch), ("periodmin", periodmin), ("periodmax", periodmax),
                         ("periodunits", periodunits), ("jacobimin", jacobimin), ("jacobimax", jacobimax),
                         ("stabmin", stabmin), ("stabmax", stabmax)):
            if val is not None:
                params[key] = val
        res = self.net.get_json(PERIODIC_URL, params=params, ttl=TTL_PERIODIC)
        if not res.ok:
            return res
        d = res.data
        if not isinstance(d, dict) or not isinstance(d.get("fields"), list):
            msg = d.get("message") if isinstance(d, dict) else None
            return Result(None, error=str(msg or "no matching periodic orbits"))
        sysinfo = d.get("system") or {}
        lunit, tunit = num(sysinfo.get("lunit")), num(sysinfo.get("tunit"))
        fields = d["fields"]
        rows = []
        for raw in d.get("data", []):
            r = {f: num(v) for f, v in zip(fields, raw)}
            if tunit and r.get("period") is not None:
                r["period_days"] = r["period"] * tunit / 86400.0
            if lunit and r.get("x") is not None:
                r["x_km"], r["z_km"] = r["x"] * lunit, (r.get("z") or 0.0) * lunit
            rows.append(r)
        # stability index <= 1 means linearly stable
        rows.sort(key=lambda r: (r.get("stability") if r.get("stability") is not None else math.inf))
        res.data = {
            "system": sysinfo.get("name") or system, "family": d.get("family"),
            "libration_point": num(d.get("libration_point")), "branch": d.get("branch"),
            "count": int(num(d.get("count"), len(rows))), "limits": d.get("limits") or {},
            "lunit_km": lunit, "tunit_s": tunit, "mass_ratio": num(sysinfo.get("mass_ratio")),
            "rows": rows[:limit],
        }
        return res


class Nasa:
    """Facade: one object for everything JPL."""

    def __init__(self, net=None):
        net = net or default_net()
        self.horizons = Horizons(net)
        self.smallbody = SmallBody(net)
        self.periodic = PeriodicOrbits(net)
