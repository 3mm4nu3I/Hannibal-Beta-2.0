"""Project Hannibal daily brief: Apophis, satellite health and the debris cascade, in one A4 PDF.

    python docs/reports/daily/build_daily.py            # writes <stamp>.pdf + <stamp>.json here
    python docs/reports/daily/build_daily.py --out DIR

Receive-only. Every call goes through orbital/hannibal_net (rate limited, cached, masked); nothing is
transmitted to any satellite. Each section that cannot reach its source says NO DATA instead of
guessing. "Changed since last report" compares with the newest earlier <stamp>.json in the folder.

Exit code: 0 all sections live, 2 at least one section NO DATA, 3 an alert (something changed that
the watch exists to catch). The summary line for phone/email is in the JSON under "headline".
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORBITAL = HERE.parents[2] / "orbital"
sys.path.insert(0, str(ORBITAL))

SAT_TARGETS = [(25544, "ISS (ZARYA)"), (39444, "FUNcube-1 (AO-73)"), (39161, "ESTCube-1"),
               (40931, "LAPAN-A2 (IO-86)"), (40069, "METEOR M-2"), (7530, "OSCAR 7 (AO-7)"),
               (24278, "JAS-2 (FO-29)")]
OBS_URL = "https://network.satnogs.org/api/observations/"
SATDB_URL = "https://db.satnogs.org/api/satellites/{}/"
STALE_H = 48
SILENT_DAYS = 30
APOPHIS_BASELINE = {"orbit_id": "220", "sentry": "removed", "verdict": "EXCLUDED", "lisbon": "IMPOSSIBLE"}


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


# ------------------------------------------------------------------ sections ----
def apophis(net):
    import hannibal_neo
    out = {"status": "ok"}
    neo, err = hannibal_neo.run("99942", net=net)
    if err or neo is None:
        return {"status": "NO DATA", "error": err or "no result"}
    o = neo["orbit"]
    p29 = next((p for p in neo["passes"] if p["date"].startswith("2029")), None)
    out.update({"verdict": neo["verdict"], "reason": neo["reason"], "orbit_id": o.get("orbit_id"),
                "condition_code": o.get("condition_code"), "n_obs": o.get("n_obs"), "last_obs": o.get("last_obs"),
                "sentry": neo["sentry"].get("state"), "sentry_removed": neo["sentry"].get("removed"),
                "passes": [{k: p[k] for k in ("date", "distance_km", "min_km", "window_km",
                                              "clearance_above_atmosphere_km", "verdict", "rough")}
                           for p in neo["passes"]]})
    if neo["verdict"] == "NO DATA":
        out["status"] = "NO DATA"
    if p29:
        out["p2029"] = {k: p29[k] for k in ("date", "distance_km", "min_km", "window_km")}
    try:
        import hannibal_neo_where as where
    except ImportError:
        out["where"] = {"status": "missing", "error": "hannibal_neo_where not in this checkout"}
        return out
    w, werr = where.run("99942", net=net, passes=neo["passes"], sentry=neo["sentry"])
    if werr or w is None:
        out["where"] = {"status": "NO DATA", "error": werr}
        return out
    ca = min(w["track"], key=lambda x: x["distance_km"])
    t = w.get("target") or {}
    out["where"] = {"status": "ok", "closest_utc": ca["time"], "closest_km": ca["distance_km"],
                    "sub_lat": ca["sub_lat"], "sub_lon": ca["sub_lon"], "box": [ca["along_km"], ca["across_km"],
                                                                                 ca["range_pm_km"]],
                    "envelope": w["envelope"],
                    "lisbon": {k: t.get(k) for k in ("verdict", "closest_km", "closest_time", "nearest_edge_km",
                                                     "clearance_above_atmosphere_km", "dark_from", "brightest_mag",
                                                     "note", "error")}}
    return out


def satellites(net, now):
    rows, errors = [], 0
    for norad, name in SAT_TARGETS:
        row = {"norad": norad, "name": name}
        good = net.get_json(OBS_URL, params={"norad_cat_id": norad, "status": "good", "ordering": "-end",
                                             "format": "json"}, ttl=3600)
        fut = net.get_json(OBS_URL, params={"norad_cat_id": norad, "status": "future", "ordering": "end",
                                            "format": "json"}, ttl=3600)
        db = net.get_json(SATDB_URL.format(norad), params={"format": "json"}, ttl=12 * 3600)
        if not good.ok:
            row.update({"state": "NO DATA", "error": good.error})
            errors += 1
            rows.append(row)
            continue
        obs = good.data if isinstance(good.data, list) else (good.data or {}).get("results", [])
        if any(int(o.get("norad_cat_id", -1)) != norad for o in obs):
            row.update({"state": "NO DATA", "error": "SatNOGS ignored the norad_cat_id filter"})
            errors += 1
            rows.append(row)
            continue
        last = _ts(obs[0]["end"]) if obs else None
        age_h = (now - last).total_seconds() / 3600 if last else None
        row.update({"last_good": last.strftime("%Y-%m-%d %H:%M") if last else None, "age_h": age_h,
                    "stations": len({o.get("ground_station") for o in obs}), "sample": len(obs),
                    "state": "LIVE" if age_h is not None and age_h <= SILENT_DAYS * 24 else "SILENT"})
        row["stale"] = age_h is None or age_h > STALE_H
        if fut.ok:
            f = fut.data if isinstance(fut.data, list) else (fut.data or {}).get("results", [])
            f = [o for o in f if int(o.get("norad_cat_id", -1)) == norad]
            if f:
                row["next_pass"] = f"{_ts(f[0]['start']):%m-%d %H:%M} {str(f[0].get('station_name', '?'))[:18]}"
        if db.ok and isinstance(db.data, dict):
            row["db_status"] = db.data.get("status")
        rows.append(row)
    return {"status": "NO DATA" if errors == len(SAT_TARGETS) else "ok", "rows": rows}


def debris(net):
    import hannibal_kessler as k
    rows, res = k.fetch_satcat(net)
    if not rows:
        return {"status": "NO DATA", "error": getattr(res, "error", "") or "catalog empty"}
    a = k.analyse(rows)
    s = a["snapshot"]
    shells = a["shells"]
    over = [f"{x['lo_km']}-{x['hi_km']}" for x in shells if x["cascade_index"] >= 1.0]
    top = sorted(shells, key=lambda x: -x["cascade_index"])[:5]
    return {"status": "ok", "in_orbit": s.get("in_orbit"), "active_payloads": s.get("active_payloads"),
            "by_type": s.get("by_type"), "over_the_line": over,
            "top": [{"shell": f"{x['lo_km']}-{x['hi_km']}", "objects": x["objects"], "index": x["cascade_index"],
                     "band": k.classify(x["cascade_index"], x["drag_lifetime_years"])} for x in top]}


# ------------------------------------------------------------------ changes -----
def previous(folder, stamp):
    files = sorted(p for p in folder.glob("*.json") if p.stem < stamp and p.stem[:4].isdigit())
    for p in reversed(files):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def changes(cur, prev):
    """List of (level, text). level 'alert' = what the watch exists to catch, 'info' = worth a line."""
    out = []
    a = cur["apophis"]
    if a.get("status") != "ok":
        out.append(("alert", f"Apophis: NASA/JPL not reachable ({a.get('error', 'no data')}), no all-clear given"))
    else:
        if str(a.get("orbit_id")) != APOPHIS_BASELINE["orbit_id"]:
            out.append(("alert", f"Apophis: NEW orbit solution {a.get('orbit_id')} (was 220)"))
        if a.get("sentry") != APOPHIS_BASELINE["sentry"]:
            out.append(("alert", f"Apophis: Sentry status is now '{a.get('sentry')}'"))
        if a.get("verdict") != APOPHIS_BASELINE["verdict"]:
            out.append(("alert", f"Apophis: verdict {a.get('verdict')}"))
        lis = (a.get("where") or {}).get("lisbon") or {}
        if (a.get("where") or {}).get("status") == "ok" and lis.get("verdict") != APOPHIS_BASELINE["lisbon"]:
            out.append(("alert", f"Apophis: impact off Lisbon is now {lis.get('verdict')}"))
    pa = (prev or {}).get("apophis") or {}
    if pa.get("passes") and a.get("passes"):
        old = {p["date"]: round(p["distance_km"]) for p in pa["passes"]}
        new = {p["date"]: round(p["distance_km"]) for p in a["passes"]}
        if old != new:
            out.append(("alert", "Apophis: pass list changed: " + ", ".join(
                f"{d} {old.get(d, '-')} -> {new.get(d, '-')} km" for d in sorted(set(old) | set(new))
                if old.get(d) != new.get(d))))
    prev_sats = {r["norad"]: r for r in ((prev or {}).get("satellites") or {}).get("rows", [])}
    for r in cur["satellites"].get("rows", []):
        p = prev_sats.get(r["norad"])
        if r["state"] == "NO DATA":
            out.append(("info", f"{r['name']}: SatNOGS no data ({r.get('error')})"))
        elif p and p.get("state") != r["state"]:
            out.append(("alert" if r["state"] == "SILENT" else "info",
                        f"{r['name']}: {p.get('state')} -> {r['state']}"))
        elif p and r.get("stale") and not p.get("stale"):
            out.append(("info", f"{r['name']}: no decode for {r['age_h']:.0f} h (stale)"))
        elif p and p.get("stale") and not r.get("stale"):
            out.append(("info", f"{r['name']}: fresh decode again ({r['age_h']:.0f} h ago)"))
    d, pd = cur["debris"], ((prev or {}).get("debris") or {})
    if d.get("status") != "ok":
        out.append(("info", f"Debris: CelesTrak not reachable ({d.get('error')})"))
    elif pd.get("over_the_line") is not None and set(d["over_the_line"]) != set(pd["over_the_line"]):
        added = sorted(set(d["over_the_line"]) - set(pd["over_the_line"]))
        gone = sorted(set(pd["over_the_line"]) - set(d["over_the_line"]))
        out.append(("info", "Debris: shells over the line" + (f" +{', '.join(added)} km" if added else "")
                    + (f" -{', '.join(gone)} km" if gone else "")))
    return out


def headline(cur):
    a = cur["apophis"]
    if a.get("status") != "ok":
        ap = "Apophis NO DATA"
    else:
        lis = ((a.get("where") or {}).get("lisbon") or {}).get("verdict")
        ap = f"Apophis {a['verdict']} (orbit {a['orbit_id']}" + (f", Lisbon {lis}" if lis else "") + ")"
    rows = cur["satellites"].get("rows", [])
    live = sum(1 for r in rows if r["state"] == "LIVE" and not r.get("stale"))
    sat = f"satellites {live}/{len(rows)} fresh"
    d = cur["debris"]
    deb = f"{len(d['over_the_line'])} debris shells over the line" if d.get("status") == "ok" else "debris NO DATA"
    alerts = [t for lvl, t in cur["changes"] if lvl == "alert"]
    if alerts:
        lead = f"ALERT: {alerts[0]}. "
    elif not cur.get("prev_stamp"):
        lead = "First report. "
    else:
        lead = "" if cur["changes"] else "No change since last report. "
    return lead + f"{ap}; {sat}; {deb}."


# ------------------------------------------------------------------ PDF ---------
def render(cur, path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    dj = Path("/usr/share/fonts/truetype/dejavu/")
    font, bold = "Helvetica", "Helvetica-Bold"
    if (dj / "DejaVuSans.ttf").exists():
        pdfmetrics.registerFont(TTFont("Sans", str(dj / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("Sans-Bold", str(dj / "DejaVuSans-Bold.ttf")))
        font, bold = "Sans", "Sans-Bold"
    ink, ink2, rule, tint = (colors.HexColor(c) for c in ("#0b0b0b", "#52514e", "#e4e3df", "#f5f4f1"))
    accent = colors.HexColor("#b3261e")
    body = ParagraphStyle("b", fontName=font, fontSize=8.8, leading=12, textColor=ink)
    small = ParagraphStyle("s", parent=body, fontSize=7.4, leading=9.6, textColor=ink2)
    h1 = ParagraphStyle("h1", parent=body, fontName=bold, fontSize=16, leading=20)
    h2 = ParagraphStyle("h2", parent=body, fontName=bold, fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=3,
                        textColor=accent)

    def table(data, widths):
        t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
        t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), font, 7.6), ("FONT", (0, 0), (-1, 0), bold, 7.6),
                               ("TEXTCOLOR", (0, 0), (-1, 0), ink2), ("LINEBELOW", (0, 0), (-1, 0), 0.6, ink),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, tint]),
                               ("LINEBELOW", (0, -1), (-1, -1), 0.4, rule), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        return t

    s = [Paragraph("PROJECT HANNIBAL // DAILY BRIEF", h1),
         Paragraph(f"{cur['stamp_human']} &nbsp;·&nbsp; receive-only &nbsp;·&nbsp; sources NASA/JPL, SatNOGS, CelesTrak",
                   small), Spacer(1, 4), Paragraph(f"<b>{cur['headline']}</b>", body)]
    if cur["changes"]:
        s.append(Paragraph("Changed since last report", h2))
        for lvl, text in cur["changes"]:
            s.append(Paragraph(("<font color='#b3261e'><b>ALERT</b></font> " if lvl == "alert" else "· ") + text, body))
    elif cur.get("prev_stamp"):
        s.append(Paragraph(f"No change since the last report ({cur['prev_stamp']}).", small))

    a = cur["apophis"]
    s.append(Paragraph("1 &nbsp; Apophis (99942): where it won't be, where it will be", h2))
    if a.get("status") != "ok":
        s.append(Paragraph(f"NO DATA: {a.get('error')}. No all-clear is given without JPL's data.", body))
    else:
        s.append(Paragraph(
            f"Verdict <b>{a['verdict']}</b>. Orbit solution {a['orbit_id']} (U={a['condition_code']}, {a['n_obs']:,} "
            f"observations, last {a['last_obs']}). Sentry: {a['sentry']} {a.get('sentry_removed') or ''}.", body))
        rows = [["pass (TDB)", "distance km", "nearest edge km", "window km", "above atmos. km", "verdict"]]
        for p in a["passes"]:
            rows.append([p["date"], f"{p['distance_km']:,.0f}", f"{p['min_km']:,.0f}", f"{p['window_km']:,.1f}",
                         f"{p['clearance_above_atmosphere_km']:,.0f}", p["verdict"] + (" ~rough" if p["rough"] else "")])
        s += [Spacer(1, 3), table(rows, [32, 26, 28, 26, 28, 30])]
        w = a.get("where") or {}
        if w.get("status") == "ok":
            lis = w["lisbon"]
            s.append(Spacer(1, 4))
            s.append(Paragraph(
                f"2029 closest at <b>{w['closest_utc']} UTC</b>: {w['closest_km']:,.0f} km from Earth's centre, over "
                f"{w['sub_lat']:.1f}N {abs(w['sub_lon']):.1f}{'W' if w['sub_lon'] < 0 else 'E'}; 3-sigma box "
                f"{w['box'][0]:.1f} × {w['box'][1]:.1f} km, ±{w['box'][2]:.1f} km in range.", body))
            if lis.get("verdict") in ("IMPOSSIBLE", "POSSIBLE"):
                col = "#1e7a3c" if lis["verdict"] == "IMPOSSIBLE" else "#b3261e"
                s.append(Paragraph(
                    f"Impossible-event test, impact off Lisbon: <font color='{col}'>"
                    f"<b>{lis['verdict']}</b></font>. Closest {lis['closest_km']:,.0f} km at {lis['closest_time']} UTC, "
                    f"nearest 3-sigma edge {lis['nearest_edge_km']:,.0f} km "
                    f"({lis['clearance_above_atmosphere_km']:,.0f} km above the atmosphere)."
                    + (f" Naked-eye from Lisbon from {lis['dark_from'][-5:]} UTC, up to mag {lis['brightest_mag']:.1f}."
                       if lis.get("dark_from") else "") + (f" {lis['note']}" if lis.get("note") else ""), body))
            else:
                s.append(Paragraph(f"Lisbon test: NO DATA ({lis.get('error')}).", body))
            env = [["envelope (TDB)", "along km", "across km", "± range km", "time ±"]]
            for e in w["envelope"]:
                if "error" in e:
                    env.append([e["date"], "-", "-", "-", e["error"][:30]])
                else:
                    env.append([e["date"], f"{e['along_km']:,.1f}", f"{e['across_km']:,.1f}", f"{e['range_pm_km']:,.1f}",
                                e.get("time_uncertainty", "") + (" ~rough" if e.get("rough") else "")])
            s += [Spacer(1, 3), table(env, [34, 34, 28, 34, 40])]
        elif w:
            s.append(Paragraph(f"Where it will be: {w.get('status')} ({w.get('error')}).", small))

    sat = cur["satellites"]
    s.append(Paragraph("2 &nbsp; Satellite health (SatNOGS, receive-only)", h2))
    rows = [["satellite", "NORAD", "state", "last good (UTC)", "age h", "stations*", "next pass (UTC)", "DB"]]
    for r in sat.get("rows", []):
        if r["state"] == "NO DATA":
            rows.append([r["name"], r["norad"], "NO DATA", (r.get("error") or "")[:28], "", "", "", ""])
            continue
        flag = r["state"] + (" stale" if r.get("stale") and r["state"] == "LIVE" else "")
        rows.append([r["name"], r["norad"], flag, r.get("last_good") or "none", f"{r['age_h']:.0f}" if r.get("age_h")
                     is not None else "-", f"{r['stations']}/{r['sample']}", r.get("next_pass", "-"),
                     r.get("db_status", "-")])
    s += [table(rows, [30, 12, 17, 32, 11, 15, 44, 17]),
          Paragraph(f"LIVE = a good decode within {SILENT_DAYS} days; stale = none in {STALE_H} h. *distinct stations "
                    "among the latest good observations (SatNOGS pages cap at 25).", small)]

    d = cur["debris"]
    s.append(Paragraph("3 &nbsp; Debris cascade watch (CelesTrak SATCAT)", h2))
    if d.get("status") != "ok":
        s.append(Paragraph(f"NO DATA: {d.get('error')}.", body))
    else:
        bt = d.get("by_type") or {}
        s.append(Paragraph(f"In orbit {d['in_orbit']:,}; working satellites {d['active_payloads']:,}; debris "
                           f"{bt.get('DEB', 0):,}; rocket stages {bt.get('R/B', 0):,}. Shells over the line: "
                           f"<b>{', '.join(d['over_the_line']) or 'none'}</b> km.", body))
        rows = [["shell km", "objects", "cascade index", "band"]]
        rows += [[t["shell"], f"{t['objects']:,}", f"{t['index']:.2f}", t["band"]] for t in d["top"]]
        s += [Spacer(1, 3), table(rows, [30, 24, 28, 50]),
              Paragraph("Cascade index = objects / linearised Kessler threshold; a comparison between altitudes, "
                        "never a forecast.", small)]
    s += [Spacer(1, 8), Paragraph("Generated by the Hannibal daily routine. Receive-only monitoring: nothing was "
                                  "transmitted. Sections that could not reach their source say NO DATA.", small)]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                      bottomMargin=14 * mm, title=f"Hannibal daily brief {cur['stamp_human']}",
                      author="Project Hannibal").build(s)


# ------------------------------------------------------------------ main --------
def build(out_dir=HERE, net=None, now=None):
    if net is None:
        from hannibal_net import default_net
        net = default_net()
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d_%H%M")
    cur = {"stamp": stamp, "stamp_human": now.strftime("%a %d %b %Y, %H:%M UTC"), "generated": now.isoformat()}
    for key, fn in (("apophis", lambda: apophis(net)), ("satellites", lambda: satellites(net, now)),
                    ("debris", lambda: debris(net))):
        try:
            cur[key] = fn()
        except Exception as exc:  # noqa: BLE001 - one broken source must not sink the brief
            cur[key] = {"status": "NO DATA", "error": f"{type(exc).__name__}: {exc}"}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prev = previous(out_dir, stamp)
    cur["prev_stamp"] = (prev or {}).get("stamp")
    cur["changes"] = changes(cur, prev)
    cur["headline"] = headline(cur)
    (out_dir / f"{stamp}.json").write_text(json.dumps(cur, indent=2, default=str), encoding="utf-8")
    render(cur, out_dir / f"{stamp}.pdf")
    return cur, out_dir / f"{stamp}.pdf"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Project Hannibal daily brief (PDF + JSON)")
    ap.add_argument("--out", default=str(HERE), help="folder for the PDF and JSON (default: this folder)")
    args = ap.parse_args(argv)
    cur, pdf = build(args.out)
    print(cur["headline"])
    for lvl, text in cur["changes"]:
        print(f"  [{lvl}] {text}")
    print(pdf)
    if any(lvl == "alert" for lvl, _ in cur["changes"]):
        return 3
    return 2 if any(cur[k].get("status") == "NO DATA" for k in ("apophis", "satellites", "debris")) else 0


if __name__ == "__main__":
    sys.exit(main())
