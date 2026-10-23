"""Pre-registered criterion C9: is the asteroid brighter than predicted, as it would be if closer? Receive-only.

    source   NASA/JPL Horizons: predicted apparent magnitude (APmag), distance and phase angle at the exact
             time of each measurement, for the observatory code that took it   (no key, via hannibal_net)

Input: a CSV with columns  utc, mag, mag_err, station, band
       e.g. 2027-01-18T03:12:45Z, 20.71, 0.04, V37, r

Why it is self-calibrated: an absolute comparison is not good enough. JPL's absolute magnitude H
(19.09) and ESA's (18.89) differ by 0.2 mag, the phase law is uncertain, filters differ (V, r, G) and
Apophis tumbles with a brightness swing of up to about 1 mag. So C9 compares each night with the
same station's own first nights in the same band. Constant offsets (H, filter, zero point) then cancel,
and what is left is a change of brightness the prediction does not explain.

Distance signature: brightness goes as distance^-2, so if the true distance is k times the predicted
one, the residual is dV = 5 log10(k). An object 10% closer than predicted is 0.23 mag brighter;
Bram's 28,500 km against 38,011 km at closest approach would be -0.62 mag in the last hours. Far from
Earth, any realistic change of path changes the distance by a tiny fraction, so C9 is sensitive mainly
in the final days; position measurements (hannibal_astrometry_check.py) catch a change far earlier.

C9 fires (pre-registration section 4e) only when ALL of these hold:
  1. at least BASELINE_NIGHTS nights on the same station and band form the baseline (median residual)
  2. a later night's mean residual, minus that baseline, is brighter by more than DRIFT_MAG (0.3 mag,
     beyond the tumbling allowance) AND by more than 3 sigma of that night's mean
  3. it happens on at least 2 nights in a row on that station
  4. a second, independent station shows the same within its own uncertainty
  5. the drift does not just follow the phase angle (checked by hand: a phase-law problem, not distance)
The script checks 1 to 4 and reports 5's data. Like every criterion, a fire means manual verification.

    python hannibal_photometry_check.py my_photometry.csv
"""
import argparse
import csv
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
AU_KM = 149_597_870.7
BASELINE_NIGHTS = 3
DRIFT_MAG = 0.3
SIGMAS = 3.0


def read_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = datetime.fromisoformat(r["utc"].strip().replace("Z", "+00:00"))
            rows.append({"utc": t if t.tzinfo else t.replace(tzinfo=timezone.utc), "mag": float(r["mag"]),
                         "err": float(r.get("mag_err") or 0.1), "station": r["station"].strip().upper(),
                         "band": (r.get("band") or "V").strip()})
    return rows


def params(des, station, times):
    s = str(des).strip()
    return {"format": "json", "COMMAND": f"'{s};'" if s.isdigit() else f"'DES={s};'", "OBJ_DATA": "NO",
            "MAKE_EPHEM": "YES", "EPHEM_TYPE": "OBSERVER", "CENTER": f"'{station}@399'",
            "TLIST": " ".join(f"'{t.timestamp() / 86400.0 + 2440587.5:.9f}'" for t in times), "TLIST_TYPE": "JD",
            "TIME_TYPE": "UT", "QUANTITIES": "'9,20,24'", "CSV_FORMAT": "YES", "EXTRA_PREC": "YES",
            "TIME_DIGITS": "FRACSEC"}


def parse(payload):
    text = (payload or {}).get("result") or ""
    if "$$SOE" not in text:
        raise ValueError((payload or {}).get("error") or "Horizons returned no ephemeris table")
    head, body = text.split("$$SOE", 1)
    cols = [c.strip() for c in [ln for ln in head.splitlines() if "Date__(UT)" in ln][-1].split(",")]
    idx = {c: i for i, c in enumerate(cols) if c}
    for need in ("APmag", "delta", "S-T-O"):
        if need not in idx:
            raise ValueError(f"Horizons table has no {need} column")
    out = []
    for ln in body.split("$$EOE", 1)[0].strip().splitlines():
        c = ln.split(",")
        out.append({"vpred": float(c[idx["APmag"]]), "delta_km": float(c[idx["delta"]]) * AU_KM,
                    "phase": float(c[idx["S-T-O"]])})
    return out


def residual_rows(obs, pred):
    return [dict(o, vpred=p["vpred"], resid=o["mag"] - p["vpred"], delta_km=p["delta_km"], phase=p["phase"])
            for o, p in zip(obs, pred)]


def nights(rows):
    """Night means per station and band. A night = the UTC date shifted by 12 h (keeps one night together)."""
    groups = defaultdict(list)
    for r in rows:
        key = (r["station"], r["band"], datetime.fromtimestamp(r["utc"].timestamp() - 43200, timezone.utc).date().isoformat())
        groups[key].append(r)
    out = []
    for (st, band, night), rs in sorted(groups.items()):
        w = [1 / max(r["err"], 0.005) ** 2 for r in rs]
        mean = sum(wi * r["resid"] for wi, r in zip(w, rs)) / sum(w)
        scatter = statistics.stdev([r["resid"] for r in rs]) if len(rs) > 1 else max(r["err"] for r in rs)
        sem = max(scatter / math.sqrt(len(rs)), 1 / math.sqrt(sum(w)))
        out.append({"station": st, "band": band, "night": night, "points": len(rs), "mean_resid": mean, "sem": sem,
                    "phase": statistics.fmean(r["phase"] for r in rs),
                    "delta_km": statistics.fmean(r["delta_km"] for r in rs)})
    return out


def evaluate(night_rows):
    """Self-calibrated drift per station/band, and the C9 decision (conditions 1 to 4)."""
    by = defaultdict(list)
    for n in night_rows:
        by[(n["station"], n["band"])].append(n)
    series, flagged = [], {}
    for (st, band), ns in by.items():
        ns.sort(key=lambda n: n["night"])
        if len(ns) < BASELINE_NIGHTS:
            series.append({"station": st, "band": band, "status": f"baseline needs {BASELINE_NIGHTS} nights, has {len(ns)}",
                           "nights": ns})
            continue
        base = statistics.median(n["mean_resid"] for n in ns[:BASELINE_NIGHTS])
        run, best = 0, 0
        for n in ns:
            n["drift"] = n["mean_resid"] - base
            n["implied_distance_factor"] = 10 ** (n["drift"] / 5)
            n["bright"] = (n["drift"] < -DRIFT_MAG) and (-n["drift"] > SIGMAS * n["sem"])
            run = run + 1 if n["bright"] else 0
            best = max(best, run)
        series.append({"station": st, "band": band, "status": "ok", "baseline": base, "nights": ns,
                       "two_in_a_row": best >= 2})
        if best >= 2:
            flagged[st] = [n for n in ns if n["bright"]]
    confirmed = len(flagged) >= 2
    if confirmed:
        verdict = "C9 FIRED (conditions 1-4): check the phase-angle dependence and the raw images by hand"
    elif flagged:
        verdict = "candidate on one station only: needs a second, independent station before C9 can fire"
    else:
        verdict = "not fired: brightness follows JPL's prediction within the allowances"
    return {"series": series, "stations_flagged": sorted(flagged), "c9_fired": confirmed, "verdict": verdict}


def run(path, des="99942", net=None):
    if net is None:
        from hannibal_net import default_net
        net = default_net()
    obs = read_csv(path)
    by = defaultdict(list)
    for o in obs:
        by[o["station"]].append(o)
    rows = []
    for st, os_ in by.items():
        res = net.get_json(HORIZONS_URL, params=params(des, st, [o["utc"] for o in os_]), ttl=0)
        if not res.ok:
            return None, f"Horizons unavailable for {st}: {res.error}"
        try:
            pred = parse(res.data)
        except ValueError as exc:
            return None, f"Horizons reply for {st} not understood: {exc}"
        if len(pred) != len(os_):
            return None, f"Horizons returned {len(pred)} predictions for {len(os_)} measurements at {st}"
        rows += residual_rows(os_, pred)
    return evaluate(nights(rows)), ""


def format_report(r):
    lines = [f"  C9 PHOTOMETRIC CHECK  (brighter than predicted = closer?)  drift threshold {DRIFT_MAG} mag + {SIGMAS:.0f} sigma"]
    for s in r["series"]:
        lines.append(f"\n  {s['station']} band {s['band']}: " + (f"baseline residual {s['baseline']:+.3f} mag"
                                                                 if s["status"] == "ok" else s["status"]))
        lines.append(f"  {'night':<11} {'pts':>4} {'mean O-C':>9} {'+/-':>6} {'drift':>7} {'k':>6} {'phase':>6}")
        for n in s["nights"]:
            drift = f"{n['drift']:+.3f}" if "drift" in n else "-"
            k = f"{n['implied_distance_factor']:.3f}" if "drift" in n else "-"
            lines.append(f"  {n['night']:<11} {n['points']:>4} {n['mean_resid']:>+9.3f} {n['sem']:>6.3f} {drift:>7} "
                         f"{k:>6} {n['phase']:>6.1f}" + ("  BRIGHT" if n.get("bright") else ""))
    lines += ["", "  k = implied true/predicted distance (from 5 log10 k = drift); meaningful only near Earth.",
              f"  RESULT: {r['verdict']}."]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pre-registered C9: brightness against JPL's prediction")
    ap.add_argument("csv")
    ap.add_argument("--des", default="99942")
    args = ap.parse_args(argv)
    r, err = run(args.csv, args.des)
    if err:
        print(err, file=sys.stderr)
        return 1
    print(format_report(r))
    return 3 if r["c9_fired"] else 0


if __name__ == "__main__":
    sys.exit(main())
