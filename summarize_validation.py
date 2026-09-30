#!/usr/bin/env python3
"""
summarize_validation.py -- turn large record-level validation tables into the small
aggregate tables specified in Appendix F of the Project Hannibal monograph.

Runs locally. It reads your CSV(s) and prints/writes ONLY aggregates (no record-level rows),
so the output is small enough to paste into a chat.

Minimum input: one CSV with one row per scored claim and two columns
    score  : the confidence score Q in [0, 1]
    label  : 1 if the claim was later confirmed (adjudicated correct), else 0

Optional columns (each unlocks more tables):
    gate      : 1 if the claim was released by the gate, 0 if held/blocked
    reviewed  : 1 if routed to human review, else 0
    override  : 1 if the reviewer overrode the machine recommendation, else 0
    review_s  : seconds spent in review
    corrected : 1 if the claim was corrected after release, else 0
    latency_s : end-to-end latency in seconds
    group     : any category (source class, domain, language...) for subgroup tables
    time      : timestamp or sortable number; enables a temporal train/test split check

Usage:
    python summarize_validation.py data.csv
    python summarize_validation.py data.csv --score Q --label y --group source_class --out summary.md
    python summarize_validation.py a.csv b.csv          # files are concatenated
    python summarize_validation.py data.csv --thresholds 0.5 0.6 0.7 0.8 0.9

Requires: Python 3.9+, numpy, pandas.
"""
import argparse
import sys
import numpy as np
import pandas as pd


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def auroc(p, y):
    """Rank-based AUROC (Mann-Whitney U); returns nan if only one class is present."""
    y = np.asarray(y); p = np.asarray(p)
    n1 = int((y == 1).sum()); n0 = int((y == 0).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    ranks = pd.Series(p).rank(method="average").to_numpy()
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def calibration_table(p, y, bins=10):
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        n = int(m.sum())
        rows.append({"bin": "%.1f-%.1f" % (edges[b], edges[b + 1]), "n": n,
                     "mean_score": float(p[m].mean()) if n else np.nan,
                     "observed_rate": float(y[m].mean()) if n else np.nan})
    return pd.DataFrame(rows)


def ece_from_table(cal, n_total):
    c = cal.dropna()
    return float(((c["n"] / n_total) * (c["observed_rate"] - c["mean_score"]).abs()).sum())


def bootstrap_ci(fn, p, y, n_boot=1000, seed=0):
    rng = np.random.default_rng(seed)
    n = len(p); vals = []
    for _ in range(n_boot):
        i = rng.integers(0, n, n)
        v = fn(p[i], y[i])
        if not np.isnan(v):
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def fmt(x, d=3):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else ("%.*f" % (d, x))


def md(df, floatfmt=3):
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            cells.append(fmt(float(v), floatfmt) if isinstance(v, (float, np.floating)) else str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--score", default="score"); ap.add_argument("--label", default="label")
    ap.add_argument("--gate"); ap.add_argument("--reviewed"); ap.add_argument("--override")
    ap.add_argument("--review-s", dest="review_s"); ap.add_argument("--corrected")
    ap.add_argument("--latency-s", dest="latency_s"); ap.add_argument("--group"); ap.add_argument("--time")
    ap.add_argument("--thresholds", nargs="*", type=float, default=[0.5, 0.6, 0.7, 0.75, 0.8, 0.9])
    ap.add_argument("--bins", type=int, default=10)
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--out", help="also write the summary to this markdown file")
    a = ap.parse_args()

    df = pd.concat([pd.read_csv(f) for f in a.csv], ignore_index=True)
    for c in (a.score, a.label):
        if c not in df.columns:
            sys.exit("Column '%s' not found. Columns present: %s" % (c, ", ".join(df.columns)))
    df = df.dropna(subset=[a.score, a.label]).copy()
    p = df[a.score].astype(float).to_numpy(); y = df[a.label].astype(int).to_numpy()
    if p.min() < 0 or p.max() > 1:
        sys.exit("Scores must lie in [0, 1]; found min=%.3f max=%.3f. Rescale first." % (p.min(), p.max()))
    if not set(np.unique(y)) <= {0, 1}:
        sys.exit("Labels must be 0/1.")
    n = len(p)
    out = []

    # ---- R2 headline metrics
    cal = calibration_table(p, y, a.bins)
    ece = ece_from_table(cal, n)
    b_lo, b_hi = bootstrap_ci(brier, p, y, a.boot)
    e_lo, e_hi = bootstrap_ci(lambda pp, yy: ece_from_table(calibration_table(pp, yy, a.bins), len(pp)), p, y, a.boot)
    a_lo, a_hi = bootstrap_ci(auroc, p, y, a.boot)
    base = brier(np.full(n, y.mean()), y)  # constant-prediction baseline
    r2 = pd.DataFrame([
        {"metric": "claims (n)", "value": n, "ci95_low": np.nan, "ci95_high": np.nan},
        {"metric": "prevalence of correct claims", "value": float(y.mean()), "ci95_low": np.nan, "ci95_high": np.nan},
        {"metric": "Brier", "value": brier(p, y), "ci95_low": b_lo, "ci95_high": b_hi},
        {"metric": "Brier, constant baseline", "value": base, "ci95_low": np.nan, "ci95_high": np.nan},
        {"metric": "ECE (%d equal-width bins)" % a.bins, "value": ece, "ci95_low": e_lo, "ci95_high": e_hi},
        {"metric": "AUROC", "value": auroc(p, y), "ci95_low": a_lo, "ci95_high": a_hi}], dtype=object)
    out += ["## R2  Headline metrics", md(r2), ""]

    # ---- R1 calibration
    out += ["## R1  Calibration by bin of the score", md(cal), ""]

    # ---- R3 risk-coverage
    rows = []
    for t in a.thresholds:
        rel = p >= t
        cov = float(rel.mean())
        risk = float(1 - y[rel].mean()) if rel.any() else float("nan")
        row = {"threshold": t, "coverage": cov, "risk_among_released": risk}
        if a.reviewed and a.reviewed in df.columns:
            row["review_share"] = float(df[a.reviewed].astype(float).mean())
        rows.append(row)
    out += ["## R3  Risk-coverage by score threshold (score >= threshold treated as released)",
            "Ungated risk (release everything): %s" % fmt(float(1 - y.mean())), md(pd.DataFrame(rows)), ""]
    if a.gate and a.gate in df.columns:
        g = df[a.gate].astype(int).to_numpy() == 1
        out += ["Actual gate in the data: coverage %s, risk among released %s" %
                (fmt(float(g.mean())), fmt(float(1 - y[g].mean())) if g.any() else "n/a"), ""]

    # ---- R4 review
    if a.reviewed and a.reviewed in df.columns:
        rv = df[a.reviewed].astype(int) == 1
        r4 = {"review rate": float(rv.mean())}
        if a.override and a.override in df.columns and rv.any():
            r4["override rate (among reviewed)"] = float(df.loc[rv, a.override].astype(float).mean())
        if a.review_s and a.review_s in df.columns and rv.any():
            r4["median review time (s)"] = float(df.loc[rv, a.review_s].astype(float).median())
        if a.corrected and a.corrected in df.columns:
            r4["corrections after release (share)"] = float(df[a.corrected].astype(float).mean())
        out += ["## R4  Review", md(pd.DataFrame([{"metric": k, "value": v} for k, v in r4.items()])), ""]

    # ---- R5 latency
    if a.latency_s and a.latency_s in df.columns:
        l = df[a.latency_s].astype(float).dropna()
        out += ["## R5  Latency (s)", md(pd.DataFrame([{"median": float(l.median()), "p90": float(l.quantile(.9)), "p99": float(l.quantile(.99))}])), ""]

    # ---- R6 subgroups
    if a.group and a.group in df.columns:
        rows = []
        for gname, sub in df.groupby(a.group):
            pp = sub[a.score].astype(float).to_numpy(); yy = sub[a.label].astype(int).to_numpy()
            if len(pp) == 0:
                continue
            c = calibration_table(pp, yy, a.bins)
            rows.append({"group": gname, "n": len(pp), "prevalence": float(yy.mean()),
                         "Brier": brier(pp, yy), "ECE": ece_from_table(c, len(pp))})
        out += ["## R6  Subgroups by '%s'" % a.group, md(pd.DataFrame(rows)),
                "Small groups give unstable ECE; read n first.", ""]

    # ---- temporal split sanity check
    if a.time and a.time in df.columns:
        d2 = df.sort_values(a.time)
        half = len(d2) // 2
        parts = []
        for name, sub in (("earlier half", d2.iloc[:half]), ("later half", d2.iloc[half:])):
            pp = sub[a.score].astype(float).to_numpy(); yy = sub[a.label].astype(int).to_numpy()
            parts.append({"period": name, "n": len(pp), "prevalence": float(yy.mean()), "Brier": brier(pp, yy),
                          "ECE": ece_from_table(calibration_table(pp, yy, a.bins), len(pp))})
        out += ["## Temporal check (earlier vs later half)", md(pd.DataFrame(parts)),
                "Large differences suggest drift; choose thresholds on the earlier half and evaluate on the later half.", ""]

    text = "\n".join(out)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("\n(written to %s)" % a.out, file=sys.stderr)


if __name__ == "__main__":
    main()
