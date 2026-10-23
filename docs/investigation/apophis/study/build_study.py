"""Apophis study pipeline: aggregate every evidence snapshot into a verified dataset and an academic report.

    python docs/investigation/apophis/study/build_study.py                 # all snapshots so far
    python docs/investigation/apophis/study/build_study.py --until 2026-10-26T11:00Z

Inputs   docs/investigation/apophis/evidence/<stamp>/   (hourly collect.py runs and daily-brief runs)
Outputs  study/out/apophis_snapshots.csv     one row per snapshot, fixed columns
         study/out/summary.json             statistics, criteria tallies, integrity results
         study/out/fig_*.png                three figures
         study/out/Apophis_Study_Report.pdf the report
         study/out/STUDY_MANIFEST.json      SHA-256 of every input folder and every output file

Rules the pipeline follows, so it can't be steered toward a conclusion:
  * a snapshot whose files fail their SHA-256 check is kept in the table, marked, and excluded from statistics
  * values are taken exactly as the agencies published them; nothing is smoothed, filled in or dropped
  * the conclusions paragraph is generated from the pre-registered criteria alone, with fixed wording for
    each outcome, written before the data (see CONCLUSION_TEXT below)
  * hourly snapshots of the same orbit solution are NOT independent measurements, and the report says so
"""
import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
INV = HERE.parent
EVIDENCE = INV / "evidence"
OUT = HERE / "out"
REPO = INV.parents[2]

P2029_KM, P2029_3SIGMA_KM = 38_011.46, 3.3
BET = {"Bram": (28_000, 29_000), "Claude": (38_008, 38_015)}
COLUMNS = ["stamp", "taken_utc", "integrity", "source", "crosscheck_verdict", "jpl_orbit_id", "jpl_n_obs",
           "jpl_last_obs", "esa_n_obs", "esa_last_obs", "jpl_sentry", "esa_risk_list", "jpl_2029_km", "esa_2029_km",
           "diff_2029_km", "nsigma_2029", "jpl_2029_min_km", "esa_2029_min_km", "time_diff_2029_s", "jpl_A2",
           "jpl_A2_sigma", "esa_A2", "esa_A2_sigma", "jpl_A1", "jpl_A1_sigma", "jpl_A3", "lisbon_verdict",
           "lisbon_nearest_edge_km", "C1", "C2", "C3", "C4", "C5", "C6", "sources_failed"]

# Fixed in advance. The pipeline picks one; it never writes its own conclusion.
CONCLUSION_TEXT = {
    "fired": ("At least one pre-registered criterion fired during the study period ({fired}). Per the "
              "pre-registration (section 7), this is a trigger for manual verification of the raw evidence, not a "
              "finding in itself. The affected snapshots are listed in the results."),
    "none": ("No pre-registered criterion fired in any verified snapshot. Over the study period, the public data "
             "from NASA/JPL and ESA NEOCC give no evidence for a risk of impact by 99942 Apophis, including at the "
             "point off Lisbon, and no evidence for a push the Yarkovsky model doesn't explain. This is a null result "
             "for the period covered. It does not test predictions that depend on observations not yet made "
             "(Apophis is next observable from about 20 December 2026)."),
    "insufficient": ("The verified snapshots do not cover all pre-registered criteria ({unchecked} could not be "
                     "checked in any snapshot), so no conclusion is drawn for those criteria."),
}


# ------------------------------------------------------------------ loading -----
def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify(folder):
    sums = folder / "SHA256SUMS"
    if not sums.exists():
        return "no SHA256SUMS"
    bad = []
    for ln in sums.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        digest, name = ln.split(None, 1)
        f = folder / name.strip()
        if not f.exists() or sha256(f) != digest:
            bad.append(name.strip())
    return "OK" if not bad else "FAILED: " + ", ".join(bad)


def from_analysis(folder):
    """Older daily-brief folders hold analysis.json only (no Lisbon test): map it to the same columns."""
    a = json.loads((folder / "analysis.json").read_text(encoding="utf-8"))
    m = json.loads((folder / "manifest.json").read_text(encoding="utf-8")) if (folder / "manifest.json").exists() else {}
    row = {"stamp": folder.name, "taken_utc": a.get("checked_utc", "").replace(" ", "T") + ":00Z",
           "crosscheck_verdict": a.get("verdict"), "jpl_sentry": a.get("jpl_sentry"),
           "esa_risk_list": a.get("esa_risk_list"), "source": "daily brief"}
    jo = a.get("jpl_orbit") or {}
    row.update({"jpl_orbit_id": jo.get("orbit_id"), "jpl_n_obs": jo.get("n_obs_used"), "jpl_last_obs": jo.get("last_obs")})
    eo = a.get("esa_observations") or {}
    row.update({"esa_n_obs": eo.get("count"), "esa_last_obs": eo.get("last")})
    p = next((r for r in a.get("passes", []) if str(r.get("date", "")).startswith("2029")), {})
    row.update({"jpl_2029_km": p.get("jpl_km"), "esa_2029_km": p.get("esa_km"), "diff_2029_km": p.get("diff_km"),
                "nsigma_2029": p.get("n_sigma"), "jpl_2029_min_km": p.get("jpl_min_km"),
                "esa_2029_min_km": p.get("esa_min_km"), "time_diff_2029_s": p.get("time_diff_s")})
    ng = a.get("nongrav") or {}
    for ag in ("jpl", "esa"):
        for t in ("A1", "A2", "A3"):
            v = (ng.get(ag) or {}).get(t)
            row[f"{ag}_{t}"], row[f"{ag}_{t}_sigma"] = (v[0], v[1]) if v else (None, None)
    concerns = a.get("concerns", [])
    for i in (1, 2, 3, 6):
        row[f"C{i}"] = any(c.startswith(f"C{i}:") for c in concerns) if a.get("verdict") != "NO DATA" else None
    if "nongrav" not in a:
        row["C6"] = None
    row["C4"] = None
    row["C5"] = (abs(row["jpl_2029_km"] - P2029_KM) > P2029_3SIGMA_KM) if row.get("jpl_2029_km") else None
    failed = [s["name"] for s in m.get("sources", []) if not s.get("ok")]
    row["sources_failed"] = ";".join(failed)
    return row


def load(until=None):
    rows = []
    for folder in sorted(p for p in EVIDENCE.iterdir() if p.is_dir()):
        integrity = verify(folder)
        if (folder / "snapshot.json").exists():
            s = json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
            row = {k: s.get(k) for k in COLUMNS}
            row.update({f"C{i}": s["criteria"].get(f"C{i}") for i in range(1, 7)})
            row["source"] = "hourly collector"
            row["sources_failed"] = ";".join(k for k, ok in s.get("sources_ok", {}).items() if not ok)
        elif (folder / "analysis.json").exists():
            row = from_analysis(folder)
        else:
            continue
        row["integrity"] = integrity
        row["folder_sha256"] = hashlib.sha256("".join(sha256(f) for f in sorted(folder.iterdir())).encode()).hexdigest()
        if until and row["taken_utc"] and row["taken_utc"] > until:
            continue
        rows.append(row)
    return rows


# ------------------------------------------------------------------ statistics --
def describe(values):
    v = [float(x) for x in values if x is not None and x != ""]
    if not v:
        return {"n": 0}
    return {"n": len(v), "min": min(v), "max": max(v), "mean": statistics.fmean(v),
            "stdev": statistics.stdev(v) if len(v) > 1 else 0.0, "distinct": len(set(round(x, 9) for x in v))}


def summarise(rows):
    ok = [r for r in rows if r["integrity"] == "OK"]
    out = {"snapshots_total": len(rows), "snapshots_verified": len(ok),
           "integrity_failures": [{"stamp": r["stamp"], "integrity": r["integrity"]} for r in rows if r["integrity"] != "OK"],
           "first_utc": ok[0]["taken_utc"] if ok else None, "last_utc": ok[-1]["taken_utc"] if ok else None,
           "orbit_solutions_seen": sorted({str(r["jpl_orbit_id"]) for r in ok if r.get("jpl_orbit_id")}),
           "jpl_last_obs_seen": sorted({str(r["jpl_last_obs"]) for r in ok if r.get("jpl_last_obs")}),
           "esa_last_obs_seen": sorted({str(r["esa_last_obs"]) for r in ok if r.get("esa_last_obs")}),
           "sentry_states": sorted({str(r["jpl_sentry"]) for r in ok if r.get("jpl_sentry")}),
           "esa_risk_states": sorted({str(r["esa_risk_list"]) for r in ok if r.get("esa_risk_list")}),
           "metrics": {k: describe(r.get(k) for r in ok) for k in
                       ("jpl_2029_km", "esa_2029_km", "diff_2029_km", "nsigma_2029", "jpl_2029_min_km",
                        "esa_2029_min_km", "time_diff_2029_s", "jpl_A2", "esa_A2", "lisbon_nearest_edge_km")},
           "criteria": {}, "source_failures": {}}
    for i in range(1, 7):
        k = f"C{i}"
        vals = [r.get(k) for r in ok]
        out["criteria"][k] = {"fired": sum(1 for v in vals if v is True), "checked": sum(1 for v in vals if v is not None),
                              "fired_in": [r["stamp"] for r in ok if r.get(k) is True]}
    for r in ok:
        for s in filter(None, (r.get("sources_failed") or "").split(";")):
            out["source_failures"][s] = out["source_failures"].get(s, 0) + 1
    fired = [k for k, v in out["criteria"].items() if v["fired"]]
    unchecked = [k for k, v in out["criteria"].items() if v["checked"] == 0]
    if fired:
        out["outcome"], text = "fired", CONCLUSION_TEXT["fired"].format(fired=", ".join(fired))
    else:
        out["outcome"], text = "none", CONCLUSION_TEXT["none"]
    if unchecked:
        text += " " + CONCLUSION_TEXT["insufficient"].format(unchecked=", ".join(unchecked))
    out["conclusion"] = text
    d = out["metrics"]["jpl_2029_km"]
    if d.get("n"):
        last = [r for r in ok if r.get("jpl_2029_km")][-1]["jpl_2029_km"]
        out["bet_status"] = {who: lo <= last <= hi for who, (lo, hi) in BET.items()}
        out["bet_latest_km"] = last
    return out


# ------------------------------------------------------------------ outputs -----
def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS + ["folder_sha256"], extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLUMNS + ["folder_sha256"]})


def figures(rows, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "axes.spines.top": False,
                         "axes.spines.right": False})
    ok = [r for r in rows if r["integrity"] == "OK" and r.get("jpl_2029_km")]
    t = [datetime.fromisoformat(r["taken_utc"].replace("Z", "+00:00")) for r in ok]
    paths = {}
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 2.8), gridspec_kw={"width_ratios": [2.2, 1]})
    a1.fill_between(t, [P2029_KM - P2029_3SIGMA_KM] * len(t), [P2029_KM + P2029_3SIGMA_KM] * len(t), color="#2a78d6",
                    alpha=0.12, label="JPL sol. 220, 3-sigma", step="mid")
    a1.plot(t, [r["jpl_2029_km"] for r in ok], "o-", ms=2.5, lw=1, color="#2a78d6", label="NASA/JPL")
    a1.plot(t, [r["esa_2029_km"] for r in ok], "s-", ms=2.5, lw=1, color="#b3261e", label="ESA NEOCC")
    a1.set_ylabel("2029 closest approach, km")
    a1.set_title("Predicted 2029 distance, per snapshot", loc="left", fontsize=9)
    a1.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
    a1.legend(frameon=False, fontsize=6.5, loc="lower left", ncol=3)
    a1.ticklabel_format(axis="y", useOffset=False, style="plain")
    for y, who, col in ((0, "Bram", "#8a8984"), (1, "Claude", "#52514e")):
        lo, hi = BET[who]
        mid, half = (lo + hi) / 2, max((hi - lo) / 2, 150)          # draw at least 300 km wide so it is visible
        a2.hlines(y, mid - half, mid + half, lw=9, color=col)
        a2.text(mid, y + 0.28, f"{lo:,}–{hi:,} km", ha="center", fontsize=6.5, color=col)
    a2.set_yticks([0, 1], ["Bram", "Claude"])
    a2.set_ylim(-0.6, 1.9)
    a2.axvline(ok[-1]["jpl_2029_km"], color="#2a78d6", lw=1.2)
    a2.text(ok[-1]["jpl_2029_km"], 1.65, "latest JPL ", color="#2a78d6", fontsize=6.5, ha="right")
    a2.set_xlim(26_000, 40_000)
    a2.set_title("The bet (full scale)", loc="left", fontsize=9)
    a2.set_xlabel("km")
    fig.tight_layout()
    paths["distance"] = out / "fig_distance.png"
    fig.savefig(paths["distance"], dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 2.2))
    ax.axhspan(-3, 3, color="#1e7a3c", alpha=0.08)
    ax.plot(t, [math.copysign(r["nsigma_2029"], r["diff_2029_km"] or 1) if r.get("nsigma_2029") is not None else None
                for r in ok], "o-", ms=2.5, lw=1, color="#0b0b0b")
    ax.axhline(3, color="#b3261e", lw=0.8, ls="--")
    ax.axhline(-3, color="#b3261e", lw=0.8, ls="--")
    ax.set_ylabel("ESA − JPL, sigma")
    ax.set_title("Agreement between agencies on the 2029 distance (C3 fires outside ±3)", loc="left", fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
    fig.tight_layout()
    paths["agreement"] = out / "fig_agreement.png"
    fig.savefig(paths["agreement"], dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 2.2))
    a2v = [r for r in ok if r.get("jpl_A2") is not None]
    ta = [datetime.fromisoformat(r["taken_utc"].replace("Z", "+00:00")) for r in a2v]
    ax.errorbar(ta, [r["jpl_A2"] * 1e14 for r in a2v], yerr=[3 * (r["jpl_A2_sigma"] or 0) * 1e14 for r in a2v],
                fmt="o", ms=2.5, color="#2a78d6", label="JPL A2 ± 3 sigma", lw=0.8)
    ax.errorbar(ta, [r["esa_A2"] * 1e14 if r.get("esa_A2") else None for r in a2v],
                yerr=[3 * (r["esa_A2_sigma"] or 0) * 1e14 for r in a2v], fmt="s", ms=2.5, color="#b3261e",
                label="ESA A2 ± 3 sigma", lw=0.8)
    if len(ta) == 1:
        from datetime import timedelta
        ax.set_xlim(ta[0] - timedelta(hours=1), ta[0] + timedelta(hours=1))
    ax.set_ylabel("A2, 1e-14 au/d²")
    ax.set_title("Yarkovsky push A2 (C6)", loc="left", fontsize=9)
    ax.legend(frameon=False, fontsize=7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
    fig.tight_layout()
    paths["a2"] = out / "fig_a2.png"
    fig.savefig(paths["a2"], dpi=200)
    plt.close(fig)
    return paths


ZOMBIE_FILE = REPO / "docs" / "reports" / "2026-10-23_mission-report" / "zombie_23oct.json"


def zombie_appendix():
    """Supplementary SatNOGS result (Appendix B), read as recorded; None if the file isn't there."""
    if not ZOMBIE_FILE.exists():
        return None
    d = json.loads(ZOMBIE_FILE.read_text(encoding="utf-8"))
    return {"counts": d.get("counts", {}), "sha256": sha256(ZOMBIE_FILE),
            "heard": [r for r in d.get("rows", []) if r.get("tier") == "HEARD"]}


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def fmt(x, nd=1):
    if x is None or x == "":
        return "–"
    if isinstance(x, float):
        if abs(x) < 1e-6 and x != 0:
            return f"{x:.4e}"
        return f"{x:,.{nd}f}"
    return str(x)


def report(rows, summary, figs, path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    dj = Path("/usr/share/fonts/truetype/dejavu/")
    for name, f in (("Sans", "DejaVuSans.ttf"), ("Sans-Bold", "DejaVuSans-Bold.ttf"), ("Sans-It", "DejaVuSans-Oblique.ttf"),
                    ("Mono", "DejaVuSansMono.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(dj / f)))
    pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-Bold", italic="Sans-It", boldItalic="Sans-Bold")
    ink, ink2, rule, tint = (colors.HexColor(c) for c in ("#0b0b0b", "#52514e", "#e4e3df", "#f5f4f1"))
    body = ParagraphStyle("b", fontName="Sans", fontSize=9, leading=12.8, textColor=ink, spaceAfter=4)
    small = ParagraphStyle("s", parent=body, fontSize=7.4, leading=9.8, textColor=ink2)
    h1 = ParagraphStyle("h1", parent=body, fontName="Sans-Bold", fontSize=16, leading=20)
    h2 = ParagraphStyle("h2", parent=body, fontName="Sans-Bold", fontSize=11, leading=14, spaceBefore=10)
    cell = ParagraphStyle("c", parent=body, fontSize=7.8, leading=10, spaceAfter=0)
    cellb = ParagraphStyle("cb", parent=cell, fontName="Sans-Bold")

    def P(t, st=body):
        return Paragraph(t, st)

    def T(data, widths):
        t = Table([[P(str(c), cellb if i == 0 else cell) for c in r] for i, r in enumerate(data)],
                  colWidths=[w * mm for w in widths], repeatRows=1)
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.7, ink), ("LINEBELOW", (0, -1), (-1, -1), 0.4, rule),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, tint]),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        return t

    m = summary["metrics"]
    head = git("rev-parse", "--short", "HEAD")
    s = [P("An amateur, pre-registered monitoring study of asteroid 99942 Apophis: impact exclusion, agency "
           "agreement and model predictions for the 13 April 2029 close approach", h1),
         P(f"Project Hannibal · data {summary['first_utc']} to {summary['last_utc']} · "
           f"{summary['snapshots_verified']} verified snapshots · report built "
           f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC from commit {head}", small), Spacer(1, 6)]

    d29, e29 = m["jpl_2029_km"], m["esa_2029_km"]
    s += [P("Abstract", h2), P(
        f"We monitored the public orbit products of NASA/JPL and ESA NEOCC for asteroid 99942 Apophis, hourly, from "
        f"{summary['first_utc']} to {summary['last_utc']} ({summary['snapshots_verified']} verified snapshots, every raw "
        f"reply hashed with SHA-256). Before collecting data we fixed nine criteria (C1 to C9) for what would count as "
        f"real reason for concern: risk listings, a pass reaching the atmosphere, disagreement between the agencies, "
        f"an impact solution at a point off Lisbon, a shift of the 2029 distance, and a push the Yarkovsky model "
        f"doesn't explain. C1 to C6 are evaluated automatically. Over the period, JPL's predicted 2029 distance "
        f"ranged {fmt(d29.get('min'))} to {fmt(d29.get('max'))} km and ESA's {fmt(e29.get('min'))} to "
        f"{fmt(e29.get('max'))} km. Orbit solutions seen: {', '.join(summary['orbit_solutions_seen']) or '–'}. "
        f"{summary['conclusion']}")]

    s += [P("1  Question and pre-registration", h2), P(
        "Question: is there evidence, in public data from independent professional sources, that Apophis poses a real "
        "risk of impact, including at 38.70N 9.60W off Lisbon during the 2029 flyby? The criteria, two hypotheses and a "
        "recorded bet were committed to git before the data that tests them existed "
        "(<font name='Mono'>docs/investigation/apophis/PREREGISTRATION.md</font>; registration commit 36f3703, "
        "23 Oct 2026, 21:03 UTC)."),
          T([["Criterion", "Definition (abridged)", "Checked"],
             ["C1", "JPL Sentry or ESA's risk list carries Apophis", "automatic"],
             ["C2", "Any pass's minimum possible distance ≤ Earth radius + 100 km (JPL or ESA)", "automatic"],
             ["C3", "JPL and ESA disagree by > 3 combined sigma on a pass whose window is smaller than its distance", "automatic"],
             ["C4", "Impact at the point off Lisbon is POSSIBLE on JPL's 3-sigma bounds", "automatic (hourly collector)"],
             ["C5", f"A new JPL solution moves the 2029 distance by > {P2029_3SIGMA_KM} km (3 sigma of solution 220)", "automatic"],
             ["C6", "Yarkovsky A2 moves > 3 sigma, a radial or normal push becomes significant, or JPL and ESA disagree on A2", "automatic"],
             ["C7", "Narrowband radio signal tracking Apophis, confirmed by a second station (2029 flyby)", "manual, not yet possible"],
             ["C8", "Light curve, spin or colour inconsistent with a natural body, or close-up imaging", "manual, not yet possible"],
             ["C9", "Measured brightness drifts > 0.3 mag and 3 sigma brighter than JPL's prediction, 2 nights, 2 stations (self-calibrated)", "own photometry, from Dec 2026"]],
            [18, 116, 40]),
          Spacer(1, 4),
          P("Hypotheses: H0, the agencies' orbit models are correct; H-A (stated by the investigators), Apophis is "
            "artificial or controlled. A recorded bet (section 4d) puts the 2029 distance at 28,000 to 29,000 km "
            "(investigator) or 38,008 to 38,015 km (AI assistant, from JPL's 3-sigma window).", small)]

    s += [P("2  Data and methods", h2), P(
        "Sources (all public, no authentication): NASA/JPL CNEOS close-approach API, Sentry API and Small-Body Database "
        "(orbit and non-gravitational parameters, full precision); NASA/JPL Horizons (topocentric ephemeris for the "
        "Lisbon point, 1-minute steps over ±12 h around closest approach); ESA NEOCC close approaches (.clolin), risk "
        "list, observation file (.rwo) and orbit (.ke1). Each snapshot fetches every source live (no cache, no stale "
        "copy) and stores the replies, their SHA-256 hashes, a manifest and the extracted values. Replies over 200 kB "
        "(ESA risk list and observation file, the Horizons table) are kept as hash plus extracted lines."),
          P("Comparison: passes are matched across agencies (within 5 days, or 3 times ESA's time uncertainty), and JPL's "
            "TDB times are converted to UTC (−69.184 s). The combined sigma is √(σ_JPL² + σ_ESA²), with σ_JPL = window/6 "
            "from JPL's 3-sigma bounds and σ_ESA ESA's stated 1-sigma. The Lisbon test takes the minimum over the "
            "window of the topocentric distance minus Horizons' 3-sigma range uncertainty and compares it with 100 km. "
            "Software: <font name='Mono'>orbital/hannibal_crosscheck.py</font>, <font name='Mono'>hannibal_neo_where.py</font>, "
            "<font name='Mono'>docs/investigation/apophis/collect.py</font>, all with offline tests.")]

    s += [P("3  Results", h2),
          T([["Quantity", "n", "min", "max", "mean", "stdev"]] +
            [[label, m[k].get("n", 0), fmt(m[k].get("min"), nd), fmt(m[k].get("max"), nd), fmt(m[k].get("mean"), nd),
              fmt(m[k].get("stdev"), 3)]
             for label, k, nd in (("JPL 2029 distance, km", "jpl_2029_km", 2), ("ESA 2029 distance, km", "esa_2029_km", 2),
                                  ("ESA − JPL, km", "diff_2029_km", 2), ("|ESA − JPL|, sigma", "nsigma_2029", 2),
                                  ("JPL nearest 3-sigma edge, km", "jpl_2029_min_km", 2),
                                  ("ESA minimum possible, km", "esa_2029_min_km", 2),
                                  ("Time ESA − JPL (UTC), s", "time_diff_2029_s", 1),
                                  ("Lisbon nearest edge, km", "lisbon_nearest_edge_km", 1))],
            [56, 12, 26, 26, 26, 28]),
          Spacer(1, 4),
          T([["Criterion", "fired", "checked", "fired in snapshots"]] +
            [[k, v["fired"], v["checked"], ", ".join(v["fired_in"][:6]) + (" …" if len(v["fired_in"]) > 6 else "") or "–"]
             for k, v in summary["criteria"].items()], [20, 18, 20, 116]),
          Spacer(1, 4),
          P(f"Orbit solutions seen: {', '.join(summary['orbit_solutions_seen']) or '–'}. Latest observation used by JPL: "
            f"{', '.join(summary['jpl_last_obs_seen']) or '–'}; in ESA's file: {', '.join(summary['esa_last_obs_seen']) or '–'}. "
            f"Sentry: {'; '.join(summary['sentry_states']) or '–'}. ESA risk list: {'; '.join(summary['esa_risk_states']) or '–'}. "
            f"Source failures (snapshots): {json.dumps(summary['source_failures']) if summary['source_failures'] else 'none'}. "
            f"Integrity failures: {len(summary['integrity_failures'])}."),
          Image(str(figs["distance"]), width=174 * mm, height=174 * mm * 2.8 / 7.2),
          Image(str(figs["agreement"]), width=174 * mm, height=174 * mm * 2.2 / 7.2),
          Image(str(figs["a2"]), width=174 * mm, height=174 * mm * 2.2 / 7.2)]
    if summary.get("bet_latest_km"):
        inside = [w for w, v in summary["bet_status"].items() if v]
        s.append(P(f"The bet: the latest JPL value, {summary['bet_latest_km']:,.2f} km, lies inside "
                   f"{inside[0] + chr(39) + 's' if inside else 'neither'} range. The bet is settled only by the "
                   "post-flyby reconstruction (April 2029).", small))

    s += [P("4  Threats to validity and bias controls", h2),
          T([["Issue", "Effect", "Control or statement"],
             ["Shared observations", "JPL and ESA fit largely the same Minor Planet Center observations; their agreement "
              "tests the fitting, not the observations themselves.", "Stated. The study's own astrometry "
              "(hannibal_astrometry_check.py, from Dec 2026) adds independent observations."],
             ["Snapshots are not independent", "Hourly snapshots of an unchanged orbit solution repeat one measurement. "
              "n is the number of looks, not the number of independent samples.", "No statistical test treats them as "
              "independent. What the series can detect is the publication of a new solution."],
             ["Linearised uncertainty", "3-sigma windows assume a linear covariance; this fails for distant passes (2116).",
              "C3 ignores passes whose window is larger than the distance; those are logged as notes."],
             ["Observation gap", "No observations since 2022-04-09; Apophis is unobservable until about 20 Dec 2026.",
              "The null result covers the period only; the study continues through the 2027–2029 windows."],
             ["Investigator expectation", "The investigators hold H-A and bet against the models.",
              "Criteria, thresholds and conclusion wording were fixed before the data; the pipeline picks the wording."],
             ["AI assistance", "The software and this report were written with Claude (Anthropic).",
              "All code, data and hashes are public in the repository; anyone can rerun the pipeline."],
             ["Data integrity", "Files could be altered after collection.", "SHA-256 per file, checked on every build; "
              "failures are excluded from statistics and listed."]], [32, 72, 70])]

    s += [P("5  Conclusion", h2), P(summary["conclusion"]),
          P("Predictions for the 2029 model test (section 4c of the pre-registration) remain open until the post-flyby "
            "reconstruction: closest approach 21:44:50 UTC (JPL) or 21:45:03 UTC (ESA), at 38,011 km (JPL 3-sigma window "
            "38,008 to 38,015 km) or 38,014 km (ESA).", small)]

    s += [P("6  Reproducibility", h2),
          P("<font name='Mono'>git clone --branch reports/daily https://github.com/3mm4nu3I/Hannibal-Beta-2.0<br/>"
            "python docs/investigation/apophis/study/build_study.py --until &lt;same cutoff&gt;</font><br/>"
            "rebuilds the dataset, figures and this report from the stored evidence. "
            "<font name='Mono'>study/out/STUDY_MANIFEST.json</font> lists the SHA-256 of every input folder and every "
            "output. Each evidence folder can be checked on its own with <font name='Mono'>sha256sum -c SHA256SUMS</font>."),
          P("7  Data and code availability", h2),
          P("All evidence snapshots, the pre-registration, the software and this report's builder are public in the "
            "repository above (branch reports/daily, pull request #15). Raw agency replies under 200 kB are stored "
            "verbatim; larger ones are stored as SHA-256 hash plus extracted lines and can be re-downloaded from the "
            "agencies for comparison. Excluded material: station telemetry summaries dated 20 to 22 October 2026 are "
            "not used, because they cannot be reproduced from recorded data."),
          P("8  Contributions and AI-use disclosure", h2),
          P("Study design, hypotheses H-A and the investigator's prediction: Bram (Project Hannibal). Software, analysis "
            "pipeline and drafting of this report: Claude, an AI model by Anthropic, at the investigator's request; the AI "
            "assistant's own prediction is recorded separately (pre-registration 4d) and plays no part in the criteria. "
            "No data was generated by the AI: every number in the results comes from the agencies' replies stored in the "
            "evidence folders."),
          P("9  References (data services)", h2),
          P("[1] NASA/JPL Center for Near-Earth Object Studies, SBDB Close-Approach Data API, ssd-api.jpl.nasa.gov/cad.api. "
            "[2] NASA/JPL Sentry: Earth Impact Monitoring, ssd-api.jpl.nasa.gov/sentry.api. "
            "[3] NASA/JPL Small-Body Database API, ssd-api.jpl.nasa.gov/sbdb.api. "
            "[4] NASA/JPL Horizons System API, ssd.jpl.nasa.gov/api/horizons.api. "
            "[5] ESA NEO Coordination Centre, close approaches, risk list, observations and orbits, neo.ssa.esa.int. "
            "[6] SatNOGS Network and DB (Libre Space Foundation), network.satnogs.org and db.satnogs.org (Appendix B).", small),
          PageBreak(), P("Appendix A: snapshots", h2),
          T([["stamp", "integrity", "orbit", "JPL 2029 km", "ESA 2029 km", "sigma", "Lisbon", "fired"]] +
            [[r["stamp"], r["integrity"][:10], r.get("jpl_orbit_id") or "–", fmt(r.get("jpl_2029_km"), 2),
              fmt(r.get("esa_2029_km"), 2), fmt(r.get("nsigma_2029"), 2), r.get("lisbon_verdict") or "–",
              ",".join(f"C{i}" for i in range(1, 7) if r.get(f"C{i}") is True) or "none"] for r in rows],
            [31, 17, 12, 25, 25, 14, 26, 24])]
    z = zombie_appendix()
    if z:
        s += [P("Appendix B: supplementary result, dormant military satellites still transmitting", h2),
              P("A separate question from the Apophis study, included because it shows the same method (public records, "
                "fixed rules, reproducible). On 23 October 2026 the 148 military objects of the investigators' 17 October "
                "export were checked against SatNOGS for a vetted good observation (any volunteer station) in the 30 "
                "days before. HEARD means at least one such observation; it is not reception by the investigators' "
                "own station."),
              T([["Outcome", "Objects"]] + [[k, v] for k, v in z["counts"].items()], [80, 30]),
              Spacer(1, 4),
              T([["Object", "NORAD", "Launched", "Heard on", "Vetted good / bad (30 d)", "Last good (UTC)"]] +
                [[r["name"], r["norad"], r["launched"], r["heard_on"], f"{r['good']} / {r['bad']}", r["last_good"]]
                 for r in z["heard"]], [26, 15, 18, 49, 34, 32]),
              Spacer(1, 4),
              P(f"Source file docs/reports/2026-10-23_mission-report/zombie_23oct.json, SHA-256 {z['sha256']}. Rerun "
                "(with a new 30-day window): <font name='Mono'>python orbital/hannibal_zombie.py --json out.json</font>. "
                "Limits: 142 of the 148 objects have no SatNOGS record, so for them the check is silent, not negative; "
                "ERS 15's 2 good against 5 bad observations is a small sample, consistent with an intermittent, "
                "sunlight-dependent transmitter. This result plays no part in the Apophis criteria.", small)]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm,
                      bottomMargin=15 * mm, title="Apophis monitoring study", author="Project Hannibal").build(s)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Aggregate Apophis evidence snapshots into dataset + report")
    ap.add_argument("--until", help="ignore snapshots after this UTC time, e.g. 2026-10-26T11:00Z")
    args = ap.parse_args(argv)
    until = None
    if args.until:
        u = datetime.fromisoformat(args.until.replace("Z", "+00:00"))
        until = (u if u.tzinfo else u.replace(tzinfo=timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = load(until)
    if not rows:
        raise SystemExit("no evidence snapshots found")
    OUT.mkdir(exist_ok=True)
    summary = summarise(rows)
    write_csv(rows, OUT / "apophis_snapshots.csv")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    figs = figures(rows, OUT)
    report(rows, summary, figs, OUT / "Apophis_Study_Report.pdf")
    manifest = {"built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "commit": git("rev-parse", "HEAD"),
                "until": args.until, "inputs": {r["stamp"]: r["folder_sha256"] for r in rows},
                "outputs": {p.name: sha256(p) for p in sorted(OUT.iterdir()) if p.name != "STUDY_MANIFEST.json"}}
    (OUT / "STUDY_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"{summary['snapshots_verified']}/{summary['snapshots_total']} snapshots verified; outcome: {summary['outcome']}")
    print(OUT / "Apophis_Study_Report.pdf")


if __name__ == "__main__":
    main()
