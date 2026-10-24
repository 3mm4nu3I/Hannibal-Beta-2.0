"""Check your own asteroid astrometry against JPL's prediction (O-C residuals). Receive-only.

    source   NASA/JPL Horizons: astrometric RA/Dec (ICRF) at the exact time of each measurement, for the
             observatory code that took it, with JPL's own 3-sigma uncertainty   (no key, via hannibal_net)

Input: a CSV with columns  utc, ra_deg, dec_deg, station[, sigma_arcsec]
       e.g. 2027-01-18T03:12:45.3Z, 131.123456, 20.987654, V37, 0.3
       (ADES-like, decimal degrees; station = MPC observatory code; sigma = your 1-sigma per coordinate)

For each position: O-C in RA*cos(Dec) and Dec (arcsec), and how many combined sigmas that is
(your sigma and JPL's sigma added in quadrature). For a whole tracklet (one station, one night): the mean
O-C, which averages down your scatter.

Reading the result honestly:
  * single points off by a few sigma happen: bad timing, star-catalogue errors, a cosmic ray
  * a TRACKLET whose mean O-C is more than 3 combined sigma off, confirmed on a second night or by a
    second station, is what an unexplained push or manoeuvre would look like (pre-registered C6/C3)
  * the first things to rule out: clock error (O-C along the direction of motion = rate x time error),
    the reference catalogue (use Gaia DR3), and mid-exposure time
Submit good astrometry to the Minor Planet Center (ADES format): that's how it enters JPL's and ESA's
orbit fits, and the daily cross-check would then see any effect.

    python hannibal_astrometry_check.py my_measurements.csv
"""
import argparse
import csv
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
DEFAULT_SIGMA = 0.5        # arcsec, a cautious amateur/remote-telescope figure
FLAG_SIGMAS = 3.0


def read_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = datetime.fromisoformat(r["utc"].strip().replace("Z", "+00:00"))
            t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
            rows.append({"utc": t, "ra": float(r["ra_deg"]), "dec": float(r["dec_deg"]),
                         "station": r["station"].strip().upper(),
                         "sigma": float(r.get("sigma_arcsec") or DEFAULT_SIGMA)})
    return rows


def jd_utc(t):
    return t.timestamp() / 86400.0 + 2440587.5


def params(des, station, times):
    s = str(des).strip()
    return {"format": "json", "COMMAND": f"'{s};'" if s.isdigit() else f"'DES={s};'", "OBJ_DATA": "NO",
            "MAKE_EPHEM": "YES", "EPHEM_TYPE": "OBSERVER", "CENTER": f"'{station}@399'",
            "TLIST": " ".join(f"'{jd_utc(t):.9f}'" for t in times), "TLIST_TYPE": "JD", "TIME_TYPE": "UT",
            "QUANTITIES": "'1,3,36'", "CSV_FORMAT": "YES", "ANG_FORMAT": "DEG", "EXTRA_PREC": "YES",
            "TIME_DIGITS": "FRACSEC"}


def parse(payload):
    text = (payload or {}).get("result") or ""
    if "$$SOE" not in text:
        raise ValueError((payload or {}).get("error") or "Horizons returned no ephemeris table")
    head, body = text.split("$$SOE", 1)
    cols = [c.strip() for c in [ln for ln in head.splitlines() if "Date__(UT)" in ln or "Date_________JDUT" in ln][-1].split(",")]
    idx = {c: i for i, c in enumerate(cols) if c}
    ra_k = next(k for k in idx if k.startswith("R.A.") and "ICRF" in k)
    de_k = next(k for k in idx if k.startswith("DEC") and "ICRF" in k)
    out = []
    for ln in body.split("$$EOE", 1)[0].strip().splitlines():
        c = ln.split(",")
        out.append({"ra": float(c[idx[ra_k]]), "dec": float(c[idx[de_k]]),
                    "rate_ra": float(c[idx["dRA*cosD"]]), "rate_dec": float(c[idx["d(DEC)/dt"]]),
                    "sig_ra": float(c[idx["RA_3sigma"]]) / 3.0, "sig_dec": float(c[idx["DEC_3sigma"]]) / 3.0})
    return out


def residuals(obs, pred):
    """O-C for matched lists. Returns rows with arcsec residuals and sigmas."""
    out = []
    for o, p in zip(obs, pred):
        dra = ((o["ra"] - p["ra"] + 180.0) % 360.0 - 180.0) * math.cos(math.radians(p["dec"])) * 3600.0
        ddec = (o["dec"] - p["dec"]) * 3600.0
        s_ra, s_dec = math.hypot(o["sigma"], p["sig_ra"]), math.hypot(o["sigma"], p["sig_dec"])
        n = math.hypot(dra / s_ra, ddec / s_dec) / math.sqrt(2.0)
        rate = math.hypot(p["rate_ra"], p["rate_dec"]) / 3600.0          # arcsec per second
        along = ((dra * p["rate_ra"] + ddec * p["rate_dec"]) / math.hypot(p["rate_ra"], p["rate_dec"])
                 if rate > 0 else 0.0)
        out.append({"utc": o["utc"].strftime("%Y-%m-%d %H:%M:%S"), "station": o["station"], "dra": dra, "ddec": ddec,
                    "n_sigma": n, "flag": n > FLAG_SIGMAS, "along_track": along,
                    "clock_error_s": along / rate if rate > 0 else None,
                    "jpl_sigma_arcsec": max(p["sig_ra"], p["sig_dec"]), "obs_sigma": o["sigma"]})
    return out


def tracklets(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["station"], r["utc"][:10])].append(r)
    out = []
    for (st, night), rs in sorted(groups.items()):
        n = len(rs)
        mra, mdec = statistics.fmean(r["dra"] for r in rs), statistics.fmean(r["ddec"] for r in rs)
        s = math.hypot(statistics.fmean(r["obs_sigma"] for r in rs) / math.sqrt(n),
                       max(r["jpl_sigma_arcsec"] for r in rs))
        n_sig = math.hypot(mra, mdec) / s / math.sqrt(2.0)
        out.append({"station": st, "night": night, "points": n, "mean_dra": mra, "mean_ddec": mdec,
                    "sigma_of_mean": s, "n_sigma": n_sig, "flag": n_sig > FLAG_SIGMAS and n >= 3})
    return out


def run(path, des="99942", net=None):
    if net is None:
        from hannibal_net import default_net
        net = default_net()
    obs = read_csv(path)
    by_station = defaultdict(list)
    for o in obs:
        by_station[o["station"]].append(o)
    rows = []
    for st, os_ in by_station.items():
        res = net.get_json(HORIZONS_URL, params=params(des, st, [o["utc"] for o in os_]), ttl=0)
        if not res.ok:
            return None, f"Horizons unavailable for {st}: {res.error}"
        try:
            pred = parse(res.data)
        except (ValueError, StopIteration) as exc:
            return None, f"Horizons reply for {st} not understood: {exc}"
        if len(pred) != len(os_):
            return None, f"Horizons returned {len(pred)} positions for {len(os_)} measurements at {st}"
        rows += residuals(os_, pred)
    return {"designation": des, "points": rows, "tracklets": tracklets(rows)}, ""


def format_report(r):
    lines = [f"  O-C CHECK  {r['designation']} vs JPL Horizons  (arcsec; flag = more than {FLAG_SIGMAS:.0f} combined sigma)",
             "", f"  {'utc':<20} {'stn':<4} {'dRA*cosD':>9} {'dDec':>8} {'sigma':>6}  note"]
    for p in r["points"]:
        note = "FLAG" if p["flag"] else ""
        if p["flag"] and p["clock_error_s"] is not None and abs(p["along_track"]) > 0.8 * math.hypot(p["dra"], p["ddec"]):
            note += f" mostly along the motion: a clock error of {p['clock_error_s']:+.1f} s would explain it"
        lines.append(f"  {p['utc']:<20} {p['station']:<4} {p['dra']:>+9.2f} {p['ddec']:>+8.2f} {p['n_sigma']:>6.1f}  {note}")
    lines += ["", f"  {'tracklet':<16} {'pts':>3} {'mean dRA':>9} {'mean dDec':>9} {'+/-':>6} {'sigma':>6}"]
    for t in r["tracklets"]:
        lines.append(f"  {t['station'] + ' ' + t['night']:<16} {t['points']:>3} {t['mean_dra']:>+9.2f} "
                     f"{t['mean_ddec']:>+9.2f} {t['sigma_of_mean']:>6.2f} {t['n_sigma']:>6.1f}"
                     + ("  FLAG: confirm on another night / station before anything else" if t["flag"] else ""))
    flagged = [t for t in r["tracklets"] if t["flag"]]
    single = [p for p in r["points"] if p["flag"]]
    ok_text = ("consistent with JPL's orbit." if not single else
               f"no tracklet is off, but {len(single)} single point(s) are: most likely measurement errors. "
               "Re-measure them; a single point is never evidence on its own.")
    lines += ["", "  RESULT: " + (ok_text if not flagged else
                                  f"{len(flagged)} tracklet(s) off by more than {FLAG_SIGMAS:.0f} sigma. Check clock, "
                                  "catalogue (Gaia DR3) and mid-exposure times, then re-observe. Not a concern until "
                                  "confirmed independently (PREREGISTRATION section 7).")]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="O-C residuals of your astrometry against JPL Horizons")
    ap.add_argument("csv")
    ap.add_argument("--des", default="99942")
    args = ap.parse_args(argv)
    r, err = run(args.csv, args.des)
    if err:
        print(err, file=sys.stderr)
        return 1
    print(format_report(r))
    return 3 if any(t["flag"] for t in r["tracklets"]) else 0


if __name__ == "__main__":
    sys.exit(main())
