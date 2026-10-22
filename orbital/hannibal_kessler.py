"""Kessler cascade watch: orbital debris population and cascade index by altitude (proof of concept).

    source  CelesTrak public satellite catalog (SATCAT), https://celestrak.org/pub/satcat.csv
    auth    none; receive-only (one CSV download, cached 12 h through hannibal_net)

What it computes from the catalog:
  * snapshot     objects in Earth orbit now, by type, plus active payloads and the big constellations
  * growth       objects in orbit at the end of every year since 1960, by type
  * shells       tracked objects per 50 km altitude shell (mean of apogee and perigee) with a
                 cascade index: objects in the shell divided by the count at which collision
                 fragments would arrive faster than atmospheric drag removes them
  * breakups     the parent objects that left the most tracked debris still in orbit
  * bullet       kinetic energy of a small fragment at orbital closing speed

The cascade index is a deliberately simple, linearised Kessler-style threshold:

    collisions per year in a shell    C = N^2 * sigma * v / (2 V)
    fragments added per year          k * C
    removed by drag per year          N / tau
    runaway when k * C > N / tau  ->  N_crit = 2 V / (k * sigma * v * tau)
    cascade index                     N / N_crit

sigma is the mean catalog radar cross-section in the shell, v the closing speed, k the
trackable fragments per collision and tau a rough drag lifetime for average solar activity.
It ignores manoeuvring and untracked fragments. Read it as a comparison between altitudes,
never as a forecast.

    python hannibal_kessler.py                 # fetch the catalog and print the report
    python hannibal_kessler.py --csv satcat.csv --json kessler.json
"""
import argparse
import csv
import io
import json
import math
import sys
from collections import Counter
from datetime import date

SATCAT_URL = "https://celestrak.org/pub/satcat.csv"
SATCAT_TTL = 12 * 3600
EARTH_RADIUS_KM = 6378.137
SECONDS_PER_YEAR = 3.156e7

DEFAULTS = {
    "closing_speed_kms": 10.0,       # typical relative speed of two LEO objects
    "fragments_per_collision": 100,  # trackable (>~10 cm) fragments credited to each collision
    "shell_km": 50,
    "floor_km": 200,
    "ceiling_km": 2000,
    "default_rcs_m2": 1.0,           # used when no object in a shell has a published RCS
}

# Rough orbital lifetime (years) of a typical object by altitude, average solar activity.
# Interpolated log-linearly between points. Order-of-magnitude values only.
LIFETIME_TABLE = [(200, 0.01), (300, 0.1), (400, 1), (500, 8), (600, 30), (700, 100), (800, 250),
                  (900, 600), (1000, 1500), (1200, 5000), (1500, 10000), (2000, 20000)]

ACTIVE_CODES = {"+", "P", "B", "S", "X"}
CONSTELLATIONS = {"Starlink": "STARLINK", "OneWeb": "ONEWEB", "Kuiper": "KUIPER"}


# ------------------------------------------------------------------ parsing ----
def parse_satcat(text):
    """CSV text -> list of dict rows (CelesTrak SATCAT columns)."""
    return list(csv.DictReader(io.StringIO(text)))


def _num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def on_orbit(row, when):
    """True if the object orbits Earth and was launched on/before `when` and not decayed by it."""
    if row.get("ORBIT_CENTER") != "EA" or not row.get("LAUNCH_DATE"):
        return False
    decay = row.get("DECAY_DATE") or ""
    return row["LAUNCH_DATE"] <= when and (not decay or decay > when)


def mean_altitude(row):
    apo, per = _num(row.get("APOGEE")), _num(row.get("PERIGEE"))
    if apo is None or per is None:
        return None
    return (apo + per) / 2.0


# ------------------------------------------------------------------ physics ----
def drag_lifetime_years(alt_km):
    """Rough lifetime at a given altitude, log-linear interpolation of LIFETIME_TABLE."""
    table = LIFETIME_TABLE
    if alt_km <= table[0][0]:
        return table[0][1]
    for (a, la), (b, lb) in zip(table, table[1:]):
        if a <= alt_km <= b:
            frac = (alt_km - a) / (b - a)
            return math.exp(math.log(la) + (math.log(lb) - math.log(la)) * frac)
    return table[-1][1]


def shell_volume_km3(lo_km, hi_km):
    r1, r2 = EARTH_RADIUS_KM + lo_km, EARTH_RADIUS_KM + hi_km
    return 4.0 / 3.0 * math.pi * (r2 ** 3 - r1 ** 3)


def collisions_per_year(n, sigma_m2, volume_km3, v_kms):
    """Kinetic-gas collision rate for n objects in a volume, no manoeuvring."""
    sigma_km2 = sigma_m2 * 1e-6
    return 0.5 * n * n * sigma_km2 * v_kms * SECONDS_PER_YEAR / volume_km3


def critical_count(sigma_m2, volume_km3, v_kms, fragments, tau_years):
    """Population at which fragments from collisions arrive as fast as drag removes objects."""
    sigma_km2 = sigma_m2 * 1e-6
    denom = fragments * sigma_km2 * v_kms * SECONDS_PER_YEAR * tau_years
    return 2.0 * volume_km3 / denom if denom > 0 else float("inf")


def bullet_energy_j(diameter_cm=1.0, density_g_cm3=2.7, speed_kms=10.0):
    """Kinetic energy (J) of a solid sphere, default a 1 cm aluminium ball at 10 km/s."""
    radius_cm = diameter_cm / 2.0
    mass_kg = 4.0 / 3.0 * math.pi * radius_cm ** 3 * density_g_cm3 / 1000.0
    return 0.5 * mass_kg * (speed_kms * 1000.0) ** 2


# ------------------------------------------------------------------ analysis ---
def snapshot(rows, when):
    cur = [r for r in rows if on_orbit(r, when)]
    types = Counter(r.get("OBJECT_TYPE", "UNK") for r in cur)
    active = sum(1 for r in cur if r.get("OBJECT_TYPE") == "PAY" and r.get("OPS_STATUS_CODE") in ACTIVE_CODES)
    fleets = {name: sum(1 for r in cur if prefix in (r.get("OBJECT_NAME") or ""))
              for name, prefix in CONSTELLATIONS.items()}
    return {"date": when, "in_orbit": len(cur), "by_type": dict(types), "active_payloads": active,
            "constellations": fleets}


def growth(rows, first_year=1960, when=None):
    """Objects in orbit at the end of each year (the final year is counted at `when`)."""
    when = when or date.today().isoformat()
    last_year = int(when[:4])
    out = []
    for year in range(first_year, last_year + 1):
        cutoff = when if year == last_year else f"{year}-12-31"
        c = Counter(r.get("OBJECT_TYPE", "UNK") for r in rows if on_orbit(r, cutoff))
        out.append({"year": year, "PAY": c.get("PAY", 0), "R/B": c.get("R/B", 0),
                    "DEB": c.get("DEB", 0), "UNK": c.get("UNK", 0)})
    return out


def shells(rows, when, params=None):
    p = dict(DEFAULTS, **(params or {}))
    cur = [r for r in rows if on_orbit(r, when)]
    low = []
    for r in cur:
        per, alt = _num(r.get("PERIGEE")), mean_altitude(r)
        if per is not None and alt is not None and per < p["ceiling_km"]:
            low.append((alt, r))
    out = []
    for lo in range(p["floor_km"], p["ceiling_km"], p["shell_km"]):
        hi = lo + p["shell_km"]
        members = [r for alt, r in low if lo <= alt < hi]
        n = len(members)
        volume = shell_volume_km3(lo, hi)
        rcs = [_num(r.get("RCS")) for r in members if _num(r.get("RCS")) is not None]
        sigma = sum(rcs) / len(rcs) if rcs else p["default_rcs_m2"]
        tau = drag_lifetime_years(lo + p["shell_km"] / 2.0)
        ncrit = critical_count(sigma, volume, p["closing_speed_kms"], p["fragments_per_collision"], tau)
        types = Counter(r.get("OBJECT_TYPE", "UNK") for r in members)
        out.append({
            "lo_km": lo, "hi_km": hi, "objects": n,
            "payloads": types.get("PAY", 0), "debris": types.get("DEB", 0), "rocket_bodies": types.get("R/B", 0),
            "starlink": sum(1 for r in members if (r.get("OBJECT_NAME") or "").startswith("STARLINK")),
            "density_per_1e9_km3": n / volume * 1e9,
            "mean_rcs_m2": sigma,
            "collisions_per_year_unmanaged": collisions_per_year(n, sigma, volume, p["closing_speed_kms"]) if n else 0.0,
            "drag_lifetime_years": tau,
            "critical_count": ncrit,
            "cascade_index": n / ncrit if n and ncrit not in (0, float("inf")) else 0.0,
        })
    for sh in out:
        sh["multiplier_to_cross"] = multiplier_to_cross(sh["cascade_index"])
        sh["robustness"] = robustness(sh["cascade_index"])
    return out


def multiplier_to_cross(index):
    """How many times larger k (fragments per collision) times tau (drag lifetime) must be for the shell
    to reach index 1. The index is proportional to k * tau, so this is simply 1 / index (<= 1: already over)."""
    return 1.0 / index if index > 0 else float("inf")


def robustness(index):
    """Plain-language sensitivity of a shell's status to the two roughest assumptions (k and tau)."""
    m = multiplier_to_cross(index)
    if m <= 1:
        return "over even at these assumptions" if m <= 0.5 else "over, but within 2x of the line"
    if m <= 2:
        return "crosses if k or tau is 2x higher"
    if m <= 10:
        return "crosses only if k*tau is 2-10x higher"
    return "far from the line (>10x)"


SELF_CLEANING_YEARS = 50   # a shell drag empties within about half a century


def classify(index, tau_years=None):
    """Band label. Low-index shells are 'self-cleaning' only when drag actually clears them;
    a low-index shell with a long lifetime is 'quiet (slow to clear)', not self-cleaning."""
    if index >= 1.0:
        return "OVER THE LINE"
    if index >= 0.25:
        return "accumulating"
    if tau_years is not None and tau_years > SELF_CLEANING_YEARS:
        return "quiet (slow to clear)" if index < 0.1 else "calm"
    return "self-cleaning" if index < 0.1 else "calm"


def breakups(rows, when, top=10):
    deb = [r for r in rows if on_orbit(r, when) and r.get("OBJECT_TYPE") == "DEB"]
    parents = Counter((r.get("OBJECT_NAME") or "").replace(" DEB", "").split(" (")[0].strip() for r in deb)
    return parents.most_common(top)


def analyse(rows, when=None, params=None):
    when = when or date.today().isoformat()
    return {"date": when, "params": dict(DEFAULTS, **(params or {})),
            "snapshot": snapshot(rows, when), "growth": growth(rows, when=when),
            "shells": shells(rows, when, params), "breakups": breakups(rows, when),
            "bullet_1cm_al_10kms_j": bullet_energy_j()}


# ------------------------------------------------------------------ fetching ---
def fetch_satcat(net=None):
    """Download the catalog through hannibal_net (masked, rate limited, cached 12 h). Returns (rows, Result)."""
    if net is None:
        from hannibal_net import default_net
        net = default_net()
    res = net.request("GET", SATCAT_URL, expect="text", ttl=SATCAT_TTL, timeout=60,
                      validate=lambda t: "" if isinstance(t, str) and t.startswith("OBJECT_NAME") else
                      "CelesTrak did not return the SATCAT CSV")
    return (parse_satcat(res.data) if res.ok else []), res


# ------------------------------------------------------------------ report -----
def format_report(result):
    s = result["snapshot"]
    t = s["by_type"]
    lines = [
        f"  KESSLER CASCADE WATCH  catalog date {result['date']}",
        f"  In orbit {s['in_orbit']:,}  |  working satellites {s['active_payloads']:,}  |  "
        f"payloads {t.get('PAY', 0):,}  debris {t.get('DEB', 0):,}  rocket stages {t.get('R/B', 0):,}",
        "  Constellations: " + ", ".join(f"{k} {v:,}" for k, v in s["constellations"].items()),
        "",
        f"  {'shell km':>11} {'objects':>8} {'sats':>6} {'debris':>7} {'coll/yr*':>9} {'drag yrs':>9} {'index':>6} {'x cross':>8}  band",
    ]
    for sh in result["shells"]:
        if not sh["objects"]:
            continue
        lines.append(f"  {sh['lo_km']:>5}-{sh['hi_km']:<5} {sh['objects']:>8,} {sh['payloads']:>6,} {sh['debris']:>7,} "
                     f"{sh['collisions_per_year_unmanaged']:>9.4f} {sh['drag_lifetime_years']:>9,.0f} "
                     f"{sh['cascade_index']:>6.2f} {_fmt_mult(sh['multiplier_to_cross']):>8}  {classify(sh['cascade_index'], sh['drag_lifetime_years'])}")
    busiest = max(result["shells"], key=lambda x: x["objects"])
    over = [f"{x['lo_km']}-{x['hi_km']}" for x in result["shells"] if x["cascade_index"] >= 1]
    near = [f"{x['lo_km']}-{x['hi_km']}" for x in result["shells"] if 0.5 <= x["cascade_index"] < 1]
    lines += [
        "  * collisions per year if nobody manoeuvred.  x cross = how many times larger k (fragments per collision)",
        "    times tau (drag lifetime) would have to be for the shell to reach index 1.",
        "",
        f"  Busiest shell {busiest['lo_km']}-{busiest['hi_km']} km: {busiest['objects']:,} objects, "
        f"index {busiest['cascade_index']:.2f} (drag clears it in ~{busiest['drag_lifetime_years']:.0f} y).",
        "  Shells over the line: " + (", ".join(over) + " km" if over else "none"),
        "  Within 2x of the line: " + (", ".join(near) + " km" if near else "none")
        + "  (the 2009 Iridium-Cosmos collision alone produced over 2,000 catalogued fragments)",
        "",
        "  Breakups with the most tracked debris still in orbit:",
    ]
    lines += [f"    {n:>6,}  {name}" for name, n in result["breakups"][:8]]
    p = result["params"]
    lines += [
        "",
        f"  A 1 cm aluminium fragment at {p['closing_speed_kms']:.0f} km/s carries "
        f"~{result['bullet_1cm_al_10kms_j']:,.0f} J (a .308 rifle round: ~3,500 J).",
        f"  Model: k={p['fragments_per_collision']} fragments/collision, v={p['closing_speed_kms']} km/s, "
        "rough drag lifetimes, tracked objects only, no manoeuvring. Compare altitudes; not a forecast.",
    ]
    return "\n".join(lines)


def _fmt_mult(m):
    if m == float("inf"):
        return "-"
    return "over" if m <= 1 else (f"{m:.1f}x" if m < 100 else f"{m:,.0f}x")


def screen_kessler(ask, print_fn, color=False):
    """[D] screen for the Orbital Ops menu."""
    print_fn("  Fetching the CelesTrak satellite catalog (cached 12 h)...")
    rows, res = fetch_satcat()
    if not rows:
        print_fn(f"  [!] Catalog unavailable: {res.error or 'empty response'}")
        return
    if res.stale:
        print_fn(f"  [!] {res.note}")
    print_fn(format_report(analyse(rows)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kessler cascade watch (receive-only, CelesTrak SATCAT)")
    ap.add_argument("--csv", help="use a local satcat.csv instead of downloading")
    ap.add_argument("--json", help="also write the full analysis to this JSON file")
    ap.add_argument("--date", help="analyse the catalog as of YYYY-MM-DD (default today)")
    ap.add_argument("--fragments", type=int, default=DEFAULTS["fragments_per_collision"])
    ap.add_argument("--speed", type=float, default=DEFAULTS["closing_speed_kms"])
    args = ap.parse_args(argv)
    if args.csv:
        with open(args.csv, encoding="utf-8") as fh:
            rows = parse_satcat(fh.read())
    else:
        rows, res = fetch_satcat()
        if not rows:
            print(f"Catalog unavailable: {res.error}", file=sys.stderr)
            return 1
    result = analyse(rows, args.date, {"fragments_per_collision": args.fragments, "closing_speed_kms": args.speed})
    print(format_report(result))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        print(f"\n  wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
