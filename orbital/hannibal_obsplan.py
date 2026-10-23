"""Observing plan for an asteroid from remote telescopes: when, from where, how long (receive-only).

    source   NASA/JPL Horizons topocentric ephemerides per MPC observatory code (no key, via hannibal_net)

For each site and each night it keeps the darkest-sky hours with the object above 30 deg. It records
brightness (V), sky motion, Moon distance and the size of JPL's 3-sigma pointing box. Then it
estimates the integration needed for:

  method 1  ASTROMETRY   SNR >= 10 per tracklet position (where it is: the decisive measurement)
  method 2  PHOTOMETRY   SNR >= 50 per point, about 0.02 mag (how bright: light curve, spin, colour)

The exposure model is deliberately simple and conservative. The limiting magnitude for SNR 10 in 60 s is
20.0 for a 1 m telescope at a dark site with 2" seeing, scaling as 2.5 log10(D) + 1.25 log10(t / 60 s)
(background limited). Single exposures are capped so the trail stays under the seeing, and longer
totals mean stacking on the asteroid's motion. Treat the minutes as a planning guide, not a promise.
Check each telescope's own exposure calculator before booking.

    python hannibal_obsplan.py                        # default remote sites, both windows
    python hannibal_obsplan.py --sites K91 W85 --start 2027-01-01 --stop 2027-03-01
"""
import argparse
import json
import math
import statistics
import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
TTL = 24 * 3600

# MPC code -> (site, network, typical aperture in metres). Codes and site names verified against Horizons
# on 23 Oct 2026. Apertures are the usual telescopes there; check what the network actually offers.
SITES = OrderedDict([
    ("K91", ("Sutherland, South Africa", "LCO", 1.0)),
    ("W85", ("Cerro Tololo, Chile", "LCO", 1.0)),
    ("Q63", ("Siding Spring, Australia", "LCO", 1.0)),
    ("V37", ("McDonald, Texas", "LCO", 1.0)),
    ("Z24", ("Tenerife, Spain", "LCO", 0.4)),
    ("T04", ("Haleakala, Hawaii", "LCO", 0.4)),
    ("Q62", ("Siding Spring, Australia", "iTelescope", 0.5)),
    ("U94", ("Beryl Junction, Utah", "iTelescope", 0.5)),
    ("I89", ("Nerpio, Spain", "iTelescope", 0.43)),
])
WINDOWS = [("Window 1", "2026-12-20", "2028-08-05"), ("Window 2", "2028-10-07", "2029-04-13")]

MIN_ELEV_DEG = 30.0
MIN_MOON_DEG = 30.0
DARK_FLAGS = ("", "A")            # Horizons solar-presence flag: blank = dark, A = astronomical twilight
SEEING_ARCSEC = 2.0
M0_1M_60S = 20.0                  # SNR-10 limiting magnitude, 1 m, 60 s: conservative (real sites often do better)
SNR_ASTROMETRY, SNR_PHOTOMETRY = 10.0, 50.0
MAX_SINGLE_S = 300.0


# ------------------------------------------------------------------ exposure ----
def limiting_mag(aperture_m, exposure_s, snr=10.0):
    """Background-limited limiting magnitude for a given SNR."""
    return (M0_1M_60S + 2.5 * math.log10(aperture_m) + 1.25 * math.log10(exposure_s / 60.0)
            - 2.5 * math.log10(snr / 10.0))


def single_exposure_s(rate_arcsec_min, seeing=SEEING_ARCSEC):
    """Longest exposure whose trail stays under the seeing, capped at MAX_SINGLE_S."""
    if rate_arcsec_min <= 0:
        return MAX_SINGLE_S
    return max(1.0, min(MAX_SINGLE_S, seeing / rate_arcsec_min * 60.0))


def integration_minutes(v_mag, aperture_m, rate_arcsec_min, snr):
    """Total minutes on target to reach `snr` on V = v_mag (stacked sub-exposures, each no longer than
    single_exposure_s so the trail stays under the seeing), or None if beyond 4 h. Background-limited
    stacking adds signal-to-noise like one long exposure, so the total follows limiting_mag directly."""
    seconds = 60.0 * 10 ** ((v_mag - limiting_mag(aperture_m, 60.0, snr)) / 1.25)
    minutes = max(seconds, 1.0) / 60.0
    return round(minutes, 1) if minutes <= 240 else None


# ------------------------------------------------------------------ Horizons ----
def params(des, code, start, stop, step="30m"):
    s = str(des).strip()
    return {"format": "json", "COMMAND": f"'{s};'" if s.isdigit() else f"'DES={s};'", "OBJ_DATA": "NO",
            "MAKE_EPHEM": "YES", "EPHEM_TYPE": "OBSERVER", "CENTER": f"'{code}@399'",
            "START_TIME": f"'{start}'", "STOP_TIME": f"'{stop}'", "STEP_SIZE": f"'{step}'",
            "QUANTITIES": "'3,4,9,23,25,36'", "SKIP_DAYLT": "YES", "ELEV_CUT": f"'{MIN_ELEV_DEG:.0f}'",
            "CSV_FORMAT": "YES", "ANG_FORMAT": "DEG", "TIME_DIGITS": "MINUTES", "EXTRA_PREC": "YES"}


def parse(payload):
    text = (payload or {}).get("result") or ""
    if "$$SOE" not in text:
        raise ValueError((payload or {}).get("error") or "Horizons returned no ephemeris table")
    head, body = text.split("$$SOE", 1)
    lon = 0.0
    for ln in head.splitlines():
        if ln.startswith("Center geodetic"):
            lon = float(ln.split(":", 1)[1].split(",")[0])
            lon = lon - 360.0 if lon > 180.0 else lon
    cols = [c.strip() for c in [ln for ln in head.splitlines() if "Date__(UT)" in ln][-1].split(",")]
    idx = {c: i for i, c in enumerate(cols) if c}
    need = ("dRA*cosD", "d(DEC)/dt", "Elevation_(a-app)", "APmag", "T-O-M", "RA_3sigma", "DEC_3sigma")
    if any(n not in idx for n in need):
        raise ValueError("Horizons table is missing expected columns")
    rows = []
    rows_lon = lon
    for ln in body.split("$$EOE", 1)[0].splitlines():
        if not ln.startswith(" 1") and not ln.startswith(" 2"):
            continue                                  # skips the cut-off markers between nights
        c = ln.split(",")
        try:
            rows.append({
                "time": datetime.strptime(c[0].strip(), "%Y-%b-%d %H:%M").replace(tzinfo=timezone.utc),
                "sun": c[1].strip(), "moon_up": c[2].strip() != "",
                "rate": math.hypot(float(c[idx["dRA*cosD"]]), float(c[idx["d(DEC)/dt"]])) / 60.0,   # "/min
                "elev": float(c[idx["Elevation_(a-app)"]]), "v": float(c[idx["APmag"]]),
                "moon_sep": float(c[idx["T-O-M"]]),
                "box3": max(float(c[idx["RA_3sigma"]]), float(c[idx["DEC_3sigma"]])),
            })
        except (ValueError, IndexError):
            continue
    for r in rows:
        r["site_lon"] = rows_lon
    return rows


def fetch(des, code, start, stop, net=None, step="30m"):
    if net is None:
        from hannibal_net import default_net
        net = default_net()
    res = net.get_json(HORIZONS_URL, params=params(des, code, start, stop, step), ttl=TTL)
    if not res.ok:
        return None, res.error
    try:
        return parse(res.data), ""
    except ValueError as exc:
        return None, str(exc)


# ------------------------------------------------------------------ planning ----
def usable(r):
    return r["sun"] in DARK_FLAGS and r["elev"] >= MIN_ELEV_DEG and (not r["moon_up"] or r["moon_sep"] >= MIN_MOON_DEG)


def nights(rows):
    """Group usable rows into nights, each labelled by its local evening date (from the site longitude)."""
    out = OrderedDict()
    for r in rows:
        if not usable(r):
            continue
        local = r["time"] + timedelta(hours=r.get("site_lon", 0.0) / 15.0) - timedelta(hours=12)
        key = local.date().isoformat()
        n = out.setdefault(key, {"night": key, "hours": 0.0, "best": None})
        n["hours"] += 0.5
        if n["best"] is None or r["elev"] > n["best"]["elev"]:
            n["best"] = r
    return list(out.values())


def plan_site(code, rows, aperture):
    months = OrderedDict()
    for n in nights(rows):
        b = n["best"]
        m = months.setdefault(n["night"][:7], [])
        m.append({"night": n["night"], "hours": n["hours"], "elev": b["elev"], "v": b["v"], "rate": b["rate"],
                  "box3": b["box3"]})
    summary = []
    for month, ns in months.items():
        v = statistics.median(x["v"] for x in ns)
        rate = statistics.median(x["rate"] for x in ns)
        summary.append({"month": month, "nights": len(ns), "hours": round(sum(x["hours"] for x in ns), 1),
                        "max_single_exposure_s": round(single_exposure_s(rate)),
                        "v": round(v, 1), "rate_arcsec_min": round(rate, 2),
                        "box3_arcsec": round(max(x["box3"] for x in ns), 3),
                        "astrometry_min": integration_minutes(v, aperture, rate, SNR_ASTROMETRY),
                        "photometry_min": integration_minutes(v, aperture, rate, SNR_PHOTOMETRY),
                        "best_night": max(ns, key=lambda x: (x["hours"], -x["v"]))["night"]})
    return summary


def run(des="99942", sites=None, windows=None, net=None):
    sites = sites or list(SITES)
    windows = windows or WINDOWS
    result = {"designation": des, "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
              "assumptions": {"min_elev_deg": MIN_ELEV_DEG, "min_moon_deg": MIN_MOON_DEG, "seeing_arcsec": SEEING_ARCSEC,
                              "m0_1m_60s": M0_1M_60S, "snr_astrometry": SNR_ASTROMETRY,
                              "snr_photometry": SNR_PHOTOMETRY},
              "sites": []}
    for code in sites:
        name, network, ap = SITES.get(code, (code, "?", 0.5))
        entry = {"code": code, "site": name, "network": network, "aperture_m": ap, "windows": []}
        for label, start, stop in windows:
            rows, err = fetch(des, code, start, stop, net)
            entry["windows"].append({"window": label, "start": start, "stop": stop, "error": err,
                                     "months": plan_site(code, rows, ap) if rows else []})
        result["sites"].append(entry)
    return result


def best_by_month(result):
    """For each month: the site with the shortest astrometry integration (ties -> more dark hours)."""
    best = OrderedDict()
    for s in result["sites"]:
        for w in s["windows"]:
            for m in w["months"]:
                if m["astrometry_min"] is None:
                    continue
                cur = best.get(m["month"])
                key = (m["astrometry_min"], -m["hours"])
                if cur is None or key < cur["_key"]:
                    best[m["month"]] = dict(m, code=s["code"], site=s["site"], network=s["network"],
                                            aperture_m=s["aperture_m"], _key=key)
    return [{k: v for k, v in b.items() if k != "_key"} for b in sorted(best.values(), key=lambda x: x["month"])]


def _m(minutes):
    return "<1" if minutes < 1 else f"{minutes:.0f}"


def format_report(result):
    lines = [f"  OBSERVING PLAN  {result['designation']}  (remote telescopes, receive-only)",
             f"  usable = Sun below astronomical twilight, elevation >= {MIN_ELEV_DEG:.0f} deg, Moon >= "
             f"{MIN_MOON_DEG:.0f} deg away; integration for SNR {SNR_ASTROMETRY:.0f} (astrometry) and "
             f"{SNR_PHOTOMETRY:.0f} (photometry)", ""]
    rate_hdr = '"/min'
    lines.append(f"  {'month':<8} {'best site':<34} {'ap m':>4} {'nights':>6} {'V':>5} {rate_hdr:>6} "
                 f"{'sub s':>5} {'astro min':>9} {'photo min':>9}  best night")
    for b in best_by_month(result):
        ph = _m(b["photometry_min"]) if b["photometry_min"] is not None else ">240"
        lines.append(f"  {b['month']:<8} {b['code'] + ' ' + b['site'] + ' (' + b['network'] + ')':<34} "
                     f"{b['aperture_m']:>4.2f} {b['nights']:>6} {b['v']:>5.1f} {b['rate_arcsec_min']:>6.2f} "
                     f"{b['max_single_exposure_s']:>5} {_m(b['astrometry_min']):>9} {ph:>9}  {b['best_night']}")
    errs = [f"{s['code']} {w['window']}: {w['error']}" for s in result["sites"] for w in s["windows"] if w["error"]]
    if errs:
        lines += ["", "  Horizons errors (no plan for these): " + "; ".join(errs)]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Remote-telescope observing plan (JPL Horizons)")
    ap.add_argument("des", nargs="?", default="99942")
    ap.add_argument("--sites", nargs="+", help=f"MPC codes (default: {' '.join(SITES)})")
    ap.add_argument("--start", help="custom window start YYYY-MM-DD (with --stop)")
    ap.add_argument("--stop")
    ap.add_argument("--json", help="also write the full plan to this file")
    args = ap.parse_args(argv)
    windows = [("Custom", args.start, args.stop)] if args.start and args.stop else None
    result = run(args.des, args.sites, windows)
    print(format_report(result))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
