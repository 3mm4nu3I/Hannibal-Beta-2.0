"""GNSS watch: official GPS/Galileo status plus your own RTL-SDR signal log (receive-only).

Two independent halves, decoupled from Hannibal's event loop. Hannibal only reads what they produce.

OFFICIAL STATUS (no hardware, no key, through hannibal_net)
    GPS      US Coast Guard NAVCEN operational advisory (current_opsadvisory.oa1): every active NANU
    Galileo  European GNSS Service Centre constellation page: per-satellite status and active NAGUs
    NANU types are read as published: FCST* = planned maintenance, announced days ahead (routine);
    UNUS*/UNUN* = satellite declared unusable (worth a headline); LAUNCH/DECOM/GENERAL/USABINIT = information.
    Only notices NEW since the last run become headlines, so a satellite that has been out since
    June doesn't raise an alarm every 90 seconds.

LOCAL SIGNAL LOG (needs an RTL-SDR, an ACTIVE GNSS patch antenna on bias-tee, and GNSS-SDR)
    `config` writes a starting GNSS-SDR configuration for an RTL-SDR on GPS L1 C/A (1575.42 MHz).
    GNSS-SDR writes NMEA; `log` turns its GSV sentences into a CSV of satellite, elevation and C/N0.
    `check` looks for possible local interference: at least 4 satellites above 30 deg elevation, each
    dropping more than 6 dB-Hz below its own median at that elevation, on 2 consecutive epochs.
    A C/N0 drop can also be a wall, a tree, your body, rain on the antenna or a loose cable. It is a
    CANDIDATE to look at, never proof of jamming, and it says nothing about spoofing.
    Note: GNSS needs a small patch antenna with a clear sky view, not a dish.

    python hannibal_gnss.py status                     # official GPS + Galileo status now
    python hannibal_gnss.py config > gnss_sdr_rtl.conf # then: gnss-sdr --config_file=gnss_sdr_rtl.conf
    python hannibal_gnss.py log gnss_sdr_pvt.nmea gnss_cn0.csv
    python hannibal_gnss.py check gnss_cn0.csv

For Hannibal's terminal: gnss_routine_scan(state_file, cn0_csv) returns (timestamp, {"text", "nums",
"prediction"}) items in the same shape as the infrastructure headlines.
"""
import argparse
import csv
import html
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

NANU_OA_URL = "https://www.navcen.uscg.gov/sites/default/files/gps/opsadvisory/current_opsadvisory.oa1"
GALILEO_URL = "https://www.gsc-europa.eu/system-service-status/constellation-information"
TTL = 30 * 60

PLANNED = "planned maintenance"
UNUSABLE = "UNUSABLE (official)"
INFO = "information"

MIN_ELEV_DEG = 30.0
DROP_DB = 6.0
MIN_SATS = 4
MIN_EPOCHS = 2
MIN_BASELINE = 10


# ------------------------------------------------------------------ official ----
def nanu_class(nanu_type):
    t = (nanu_type or "").upper()
    if t.startswith("FCST"):
        return PLANNED
    if t.startswith("UNUS") or t.startswith("UNUN"):
        return UNUSABLE
    return INFO


def parse_gps_opsadvisory(text):
    """NAVCEN .oa1 -> {'date', 'prns', 'notices': [{nanu, dtg, prn, type, summary, section, class}]}."""
    if "GPS OPERATIONAL ADVISORY" not in (text or ""):
        raise ValueError("not a GPS operational advisory")
    m = re.search(r"SUBJ:\s*GPS STATUS\s+(\d{1,2} \w{3} \d{4})", text)
    prns = sorted({int(p) for line in re.findall(r"PRNS\s+([\d,\s]+)", text) for p in re.findall(r"\d+", line)})
    notices, section = [], None
    for ln in text.splitlines():
        s = ln.strip()
        head = re.match(r"([A-C])\.\s+(FORECASTS|ADVISORIES|GENERAL)", s)
        if head:
            section = head.group(2)
            continue
        if s.startswith("3. REMARKS"):
            break
        row = re.match(r"(\d{7})\s+(\d{6}Z \w{3} \d{4})\s+(\d{1,2})?\s*([A-Z]+)\s+(\S+)", s)
        if row and section:
            notices.append({"system": "GPS", "nanu": row.group(1), "dtg": row.group(2),
                            "prn": int(row.group(3)) if row.group(3) else None, "type": row.group(4),
                            "summary": row.group(5), "section": section, "class": nanu_class(row.group(4))})
    return {"date": m.group(1) if m else None, "prns": prns, "notices": notices}


def parse_galileo_constellation(page):
    """GSC constellation page -> per-satellite rows {name, svid, clock, status, nagu, nagu_type, subject}."""
    rows = []
    for tr in re.findall(r"<tr.*?</tr>", page or "", re.S):
        cells = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c))).strip()
                 for c in re.findall(r"<t[dh].*?</t[dh]>", tr, re.S)]
        if len(cells) >= 4 and re.fullmatch(r"GSAT\d{4}", cells[0]) and re.fullmatch(r"E\d{2}", cells[1]):
            rows.append({"system": "Galileo", "name": cells[0], "svid": cells[1], "clock": cells[2],
                         "status": cells[3], "nagu": cells[4] if len(cells) > 4 else "",
                         "nagu_type": cells[5] if len(cells) > 5 else "", "subject": cells[6] if len(cells) > 6 else ""})
    if not rows:
        raise ValueError("no Galileo satellite rows found (page layout changed?)")
    return rows


def fetch_official(net=None):
    if net is None:
        from hannibal_net import default_net
        net = default_net()
    out = {"gps": None, "galileo": None, "errors": []}
    r = net.request("GET", NANU_OA_URL, expect="text", ttl=TTL, timeout=30)
    if r.ok:
        try:
            out["gps"] = parse_gps_opsadvisory(r.data)
        except ValueError as exc:
            out["errors"].append(f"GPS: {exc}")
    else:
        out["errors"].append(f"GPS: {r.error}")
    r = net.request("GET", GALILEO_URL, expect="text", ttl=TTL, timeout=30)
    if r.ok:
        try:
            out["galileo"] = parse_galileo_constellation(r.data)
        except ValueError as exc:
            out["errors"].append(f"Galileo: {exc}")
    else:
        out["errors"].append(f"Galileo: {r.error}")
    return out


def official_keys(status):
    """Stable identifiers of everything worth remembering between runs."""
    keys = set()
    for n in (status.get("gps") or {}).get("notices", []):
        keys.add(f"GPS:{n['nanu']}")
    for s in status.get("galileo") or []:
        if s["status"].upper() != "USABLE":
            keys.add(f"GAL:{s['svid']}:{s['status']}:{s['nagu']}")
    return keys


def official_headlines(status, seen, now=None):
    """Headlines for notices not in `seen`. Planned maintenance is reported as routine, not as a fault."""
    now = now or time.time()
    out = []
    for n in (status.get("gps") or {}).get("notices", []):
        if f"GPS:{n['nanu']}" in seen or n["class"] == INFO:
            continue
        prn = f"PRN{n['prn']:02d}" if n["prn"] is not None else "GPS"
        what = "declared unusable" if n["class"] == UNUSABLE else "planned maintenance window"
        out.append((now, {"text": f"[GPS] {prn} {what}: NANU {n['nanu']} {n['type']} {n['summary']}",
                          "nums": n["type"], "prediction": "OUTAGE (NAVCEN)" if n["class"] == UNUSABLE else "ROUTINE"}))
    for s in status.get("galileo") or []:
        key = f"GAL:{s['svid']}:{s['status']}:{s['nagu']}"
        if s["status"].upper() == "USABLE" or key in seen:
            continue
        out.append((now, {"text": f"[GALILEO] {s['svid']} ({s['name']}) {s['status']}: NAGU {s['nagu'] or '-'} {s['subject']}",
                          "nums": s["status"], "prediction": "OUTAGE (GSC)"}))
    return out


# ------------------------------------------------------------------ local SDR ---
GSV = re.compile(r"^\$(G[PALBN]|BD)GSV,")
SYSTEM = {"GP": "GPS", "GA": "Galileo", "GL": "GLONASS", "GB": "BeiDou", "BD": "BeiDou", "GN": "GNSS"}


def nmea_ok(line):
    """Checks the NMEA checksum (*hh). Lines without one are rejected."""
    if "*" not in line or not line.startswith("$"):
        return False
    body, _, cs = line[1:].partition("*")
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(cs[:2], 16)
    except ValueError:
        return False


def parse_gsv(line):
    """One GSV sentence -> [(system, prn, elev, az, cn0)] for satellites that report a C/N0."""
    line = line.strip()
    if not GSV.match(line) or not nmea_ok(line):
        return []
    talker = line[1:3]
    f = line[1:].split("*")[0].split(",")
    out = []
    for i in range(4, len(f) - 3, 4):
        prn, el, az, snr = f[i:i + 4]
        if prn and el and snr:
            try:
                out.append((SYSTEM.get(talker, talker), int(prn), float(el), float(az or 0), float(snr)))
            except ValueError:
                continue
    return out


def nmea_time(line):
    """UTC time from a GGA or RMC sentence ('hhmmss.ss'), else None."""
    m = re.match(r"^\$G[PNALB](GGA|RMC),(\d{6}(?:\.\d+)?),", line.strip())
    return m.group(2) if m and nmea_ok(line.strip()) else None


def log_nmea(nmea_path, csv_path, follow=False, clock=time.time, sleep=time.sleep):
    """Turns NMEA GSV sentences into CSV rows: utc, epoch, system, prn, elev, az, cn0.
    The epoch comes from the latest GGA/RMC time; the date is the computer's UTC date (receivers
    only send dates in RMC). With follow=True it keeps reading as GNSS-SDR appends."""
    new = not Path(csv_path).exists()
    written = 0
    with open(nmea_path, "r", encoding="ascii", errors="ignore") as src, \
            open(csv_path, "a", newline="", encoding="utf-8") as dst:
        w = csv.writer(dst)
        if new:
            w.writerow(["utc", "epoch", "system", "prn", "elev", "az", "cn0"])
        epoch = None
        while True:
            line = src.readline()
            if not line:
                if not follow:
                    break
                dst.flush()
                sleep(1.0)
                continue
            t = nmea_time(line)
            if t:
                epoch = t
                continue
            for system, prn, el, az, cn0 in parse_gsv(line):
                utc = datetime.fromtimestamp(clock(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                w.writerow([utc, epoch or "", system, prn, el, az, cn0])
                written += 1
    return written


def read_cn0(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return [{"epoch": r["epoch"] or r["utc"], "utc": r["utc"], "sat": f"{r['system']}{int(r['prn']):02d}",
                 "elev": float(r["elev"]), "cn0": float(r["cn0"])} for r in csv.DictReader(fh)]


def interference_check(rows):
    """Possible local interference: >= MIN_SATS high satellites each > DROP_DB below their own median
    at that elevation (10-deg bins, >= MIN_BASELINE samples), on >= MIN_EPOCHS consecutive epochs."""
    baseline = defaultdict(list)
    for r in rows:
        baseline[(r["sat"], int(r["elev"] // 10))].append(r["cn0"])
    medians = {k: statistics.median(v) for k, v in baseline.items() if len(v) >= MIN_BASELINE}
    epochs = defaultdict(list)
    order = []
    for r in rows:
        if r["epoch"] not in epochs:
            order.append(r["epoch"])
        epochs[r["epoch"]].append(r)
    flagged, run, best, events = [], 0, 0, []
    for e in order:
        high = [r for r in epochs[e] if r["elev"] >= MIN_ELEV_DEG and (r["sat"], int(r["elev"] // 10)) in medians]
        dropped = [r for r in high if medians[(r["sat"], int(r["elev"] // 10))] - r["cn0"] > DROP_DB]
        hit = len(dropped) >= MIN_SATS
        run = run + 1 if hit else 0
        best = max(best, run)
        if hit:
            flagged.append({"epoch": e, "utc": dropped[0]["utc"], "dropped": len(dropped), "high": len(high),
                            "worst_db": max(medians[(r["sat"], int(r["elev"] // 10))] - r["cn0"] for r in dropped)})
        if run == MIN_EPOCHS:
            events.append(flagged[-1])
    return {"epochs": len(order), "satellites": len({r["sat"] for r in rows}), "baselines": len(medians),
            "candidate": best >= MIN_EPOCHS, "events": events, "flagged_epochs": flagged}


def local_headlines(csv_path, now=None):
    if not csv_path or not Path(csv_path).exists():
        return []
    res = interference_check(read_cn0(csv_path))
    if not res["candidate"]:
        return []
    e = res["events"][-1]
    return [(now or time.time(), {"text": f"[LOCAL GNSS] {e['dropped']} of {e['high']} high satellites "
                                          f"{DROP_DB:.0f}+ dB-Hz below normal at {e['utc']}: check antenna, "
                                          "obstruction, interference",
                                  "nums": f"-{e['worst_db']:.0f}dB", "prediction": "CANDIDATE"})]


# ------------------------------------------------------------------ Hannibal ----
def gnss_routine_scan(state_file="gnss_seen.json", cn0_csv=None, net=None):
    """For Hannibal's batch sync. Returns new official notices + a local-interference candidate.
    A failed fetch returns nothing and leaves the remembered state unchanged."""
    state = Path(state_file)
    seen = set(json.loads(state.read_text())) if state.exists() else set()
    status = fetch_official(net)
    items = official_headlines(status, seen)
    if status["gps"] is not None or status["galileo"] is not None:
        state.write_text(json.dumps(sorted(seen | official_keys(status))))
    return items + local_headlines(cn0_csv)


GNSS_SDR_CONF = """; GNSS-SDR starting configuration: RTL-SDR, GPS L1 C/A, real time. Written by hannibal_gnss.py.
; Needs an ACTIVE GNSS patch antenna. bias=1 powers it through the RTL-SDR's bias-tee (RTL-SDR Blog V3/V4).
; Check every value against the GNSS-SDR documentation for your version before relying on it.
[GNSS-SDR]
GNSS-SDR.internal_fs_sps=2000000
SignalSource.implementation=Osmosdr_Signal_Source
SignalSource.item_type=gr_complex
SignalSource.sampling_frequency=2000000
SignalSource.freq=1575420000
SignalSource.gain=40
SignalSource.rf_gain=40
SignalSource.if_gain=30
SignalSource.AGC_enabled=false
SignalSource.samples=0
SignalSource.repeat=false
SignalSource.osmosdr_args=rtl,bias=1
SignalConditioner.implementation=Pass_Through
Channels_1C.count=8
Channels.in_acquisition=1
Channel.signal=1C
Acquisition_1C.implementation=GPS_L1_CA_PCPS_Acquisition
Acquisition_1C.item_type=gr_complex
Acquisition_1C.coherent_integration_time_ms=1
Acquisition_1C.pfa=0.01
Acquisition_1C.doppler_max=10000
Acquisition_1C.doppler_step=250
Acquisition_1C.max_dwells=15
Tracking_1C.implementation=GPS_L1_CA_DLL_PLL_Tracking
Tracking_1C.item_type=gr_complex
Tracking_1C.pll_bw_hz=40.0
Tracking_1C.dll_bw_hz=2.0
TelemetryDecoder_1C.implementation=GPS_L1_CA_Telemetry_Decoder
Observables.implementation=Hybrid_Observables
PVT.implementation=RTKLIB_PVT
PVT.positioning_mode=Single
PVT.output_rate_ms=1000
PVT.display_rate_ms=1000
PVT.nmea_dump_filename=./gnss_sdr_pvt.nmea
PVT.flag_nmea_tty_port=false
PVT.output_path=./
"""


# ------------------------------------------------------------------ CLI ---------
def format_status(st):
    lines = ["  GNSS OFFICIAL STATUS  (NAVCEN NANUs + GSC NAGUs, receive-only)"]
    g = st.get("gps")
    if g:
        lines.append(f"\n  GPS advisory of {g['date']}: {len(g['prns'])} satellites in the constellation")
        for n in g["notices"]:
            if n["class"] == INFO:
                continue
            prn = f"PRN{n['prn']:02d}" if n["prn"] is not None else "-"
            lines.append(f"    {n['nanu']}  {prn:<6} {n['type']:<10} {n['summary']:<22} {n['class']}")
    gal = st.get("galileo")
    if gal:
        bad = [s for s in gal if s["status"].upper() != "USABLE"]
        lines.append(f"\n  Galileo: {len(gal) - len(bad)} of {len(gal)} satellites USABLE")
        for s in bad:
            lines.append(f"    {s['svid']} {s['name']}  {s['status']:<11} NAGU {s['nagu'] or '-'}  {s['subject']}")
    for e in st["errors"]:
        lines.append(f"\n  NO DATA: {e}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="GNSS watch: official status + RTL-SDR C/N0 log")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("config")
    lg = sub.add_parser("log")
    lg.add_argument("nmea")
    lg.add_argument("csv")
    lg.add_argument("--follow", action="store_true", help="keep reading while GNSS-SDR writes")
    ck = sub.add_parser("check")
    ck.add_argument("csv")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        st = fetch_official()
        print(format_status(st))
        return 2 if st["errors"] else 0
    if a.cmd == "config":
        sys.stdout.write(GNSS_SDR_CONF)
        return 0
    if a.cmd == "log":
        print(f"{log_nmea(a.nmea, a.csv, follow=a.follow)} satellite readings written to {a.csv}")
        return 0
    res = interference_check(read_cn0(a.csv))
    print(f"  {res['epochs']} epochs, {res['satellites']} satellites, {res['baselines']} elevation baselines")
    if res["candidate"]:
        for e in res["events"]:
            print(f"  CANDIDATE at {e['utc']}: {e['dropped']} of {e['high']} high satellites down to "
                  f"{e['worst_db']:.1f} dB-Hz below their normal. Check antenna, obstruction, cable first.")
        return 3
    print("  no interference candidate (C/N0 within normal for the high satellites)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
