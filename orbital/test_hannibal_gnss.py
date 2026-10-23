#!/usr/bin/env python3
"""Offline tests for hannibal_gnss (no network, no radio). Run: python test_hannibal_gnss.py

The advisory and Galileo rows are trimmed copies of the real NAVCEN and GSC pages of 23 Oct 2026."""
import csv
import json
import tempfile
from pathlib import Path

import hannibal_gnss as g
from hannibal_net import Result

OA = """UNCLASSIFIED
GPS OPERATIONAL ADVISORY        295.OA1
SUBJ: GPS STATUS      22 OCT 2026

1. SATELLITES, PLANES, AND CLOCKS (CS=CESIUM RB=RUBIDIUM):
B. BLOCK II : PRNS  2,  3,  5
   PLANE    : SLOT D1, E1, E3
C. BLOCK III: PRNS  1,  4, 11
   PLANE    : SLOT D2, F4, D5

2. CURRENT ADVISORIES AND FORECASTS :
A. FORECASTS:           FOR SEVEN DAYS AFTER EVENT CONCLUDES.
NANU          MSG DATE/TIME       PRN  TYPE         SUMMARY (JDAY/ZULU TIME START - STOP)
2026093       152011Z OCT 2026    08   FCSTDV       296/0150-296/1350
2026095       202052Z OCT 2026    12   FCSTRESCD    302/1600-303/0000

B. ADVISORIES:
NANU          MSG DATE/TIME       PRN  TYPE         SUMMARY (JDAY/ZULU TIME START - STOP)
2026048       261618Z JUN 2026    11   UNUSUFN      177/1612-/

C. GENERAL:
NANU          MSG DATE/TIME       PRN  TYPE         SUMMARY (JDAY/ZULU TIME START - STOP)
2026016       022303Z FEB 2026    20   LAUNCH       /-/
2026079       291526Z SEP 2026         GENERAL      /-/


3. REMARKS:
A. THE POINT OF CONTACT 2026999   111111Z OCT 2026  01  UNUSABLE  1/1-1/2
"""
GAL = """<table><tr><th>Satellite Name1</th><th>SV ID2</th><th>Clock3</th><th>Status4</th><th>Active NAGU5</th>
<th>NAGU Type6</th><th>NAGU Subject7</th></tr>
<tr><td>GSAT0101</td><td>E11</td><td>RAFS</td><td>USABLE</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
<tr><td>GSAT0201</td><td>E18</td><td>PHM</td><td>NOT USABLE</td><td>2021008</td><td>GENERAL</td>
<td>GSAT0201 AND GSAT0202 UNAVAILABLE</td></tr>
<tr><td>GENERAL NOTICE</td><td>2016063</td><td>2016-12-15</td><td>x</td></tr></table>"""

# --- official parsing -------------------------------------------------------------------------------
gps = g.parse_gps_opsadvisory(OA)
assert gps["date"] == "22 OCT 2026" and gps["prns"] == [1, 2, 3, 4, 5, 11]
assert [n["nanu"] for n in gps["notices"]] == ["2026093", "2026095", "2026048", "2026016", "2026079"]   # stops at REMARKS
by = {n["nanu"]: n for n in gps["notices"]}
assert by["2026093"]["class"] == g.PLANNED and by["2026093"]["prn"] == 8 and by["2026093"]["section"] == "FORECASTS"
assert by["2026048"]["class"] == g.UNUSABLE and by["2026079"]["prn"] is None and by["2026016"]["class"] == g.INFO
for bad in ("", "<html>404</html>"):
    try:
        g.parse_gps_opsadvisory(bad)
        raise AssertionError("accepted a non-advisory")
    except ValueError:
        pass

gal = g.parse_galileo_constellation(GAL)
assert [s["svid"] for s in gal] == ["E11", "E18"] and gal[0]["nagu"] == "" and gal[1]["status"] == "NOT USABLE"
try:
    g.parse_galileo_constellation("<p>changed layout</p>")
    raise AssertionError("accepted a page without rows")
except ValueError:
    pass

# --- headlines: planned = routine, unusable = outage, info skipped, only new ones ----------------------
st = {"gps": gps, "galileo": gal, "errors": []}
heads = g.official_headlines(st, seen=set(), now=1.0)
texts = [h[1]["text"] for h in heads]
assert len(heads) == 4                                                # 2 planned + 1 unusable + 1 Galileo
assert any("PRN11 declared unusable" in t for t in texts)
assert all(h[1]["prediction"] in ("ROUTINE", "OUTAGE (NAVCEN)", "OUTAGE (GSC)") for h in heads)
assert [h for h in heads if "PRN08" in h[1]["text"]][0][1]["prediction"] == "ROUTINE"
assert not any("TIMING FAULT" in t.upper() for t in texts)
assert g.official_headlines(st, seen=g.official_keys(st)) == []        # nothing new -> nothing


# --- NMEA --------------------------------------------------------------------------------------------
def nmea(body):
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"${body}*{cs:02X}"


gsv = nmea("GPGSV,2,1,07,08,62,123,45,10,35,200,41,12,12,300,30,15,70,050,47")
assert g.nmea_ok(gsv) and not g.nmea_ok(gsv[:-2] + "00") and not g.nmea_ok("$GPGSV,1,1")
sats = g.parse_gsv(gsv)
assert [s[1] for s in sats] == [8, 10, 12, 15] and sats[0] == ("GPS", 8, 62.0, 123.0, 45.0)
assert g.parse_gsv(nmea("GPGSV,1,1,01,22,40,100,")) == []               # no C/N0 = not tracked, skipped
assert g.parse_gsv(nmea("GAGSV,1,1,01,05,55,010,44"))[0][0] == "Galileo"
assert g.nmea_time(nmea("GPGGA,123519.00,5112.0,N,00424.0,E,1,08,0.9,10.0,M,46.9,M,,")) == "123519.00"

with tempfile.TemporaryDirectory() as tmp:
    src, out = Path(tmp) / "pvt.nmea", Path(tmp) / "cn0.csv"
    src.write_text("\n".join([nmea("GPRMC,120000.00,A,5112.0,N,00424.0,E,0.0,0.0,231026,,,A"), gsv,
                              "$GPGSV,garbage*00", nmea("GPGGA,120001.00,5112.0,N,00424.0,E,1,08,0.9,10,M,47,M,,"),
                              nmea("GPGSV,1,1,01,08,62,123,44")]) + "\n")
    assert g.log_nmea(src, out, clock=lambda: 1793000000.0) == 5
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["epoch"] == "120000.00" and rows[-1]["epoch"] == "120001.00" and rows[-1]["cn0"] == "44.0"


# --- interference candidate --------------------------------------------------------------------------
def session(drop_sats=(), drop_epochs=(), drop_db=10.0, low_drop=False, n=30):
    rows = []
    sats = {"GPS08": 60, "GPS10": 45, "GPS15": 70, "GPS21": 38, "GPS24": 52, "GPS12": 12}
    for e in range(n):
        for sat, el in sats.items():
            cn0 = 44.0 if el >= 30 else 32.0
            if e in drop_epochs and (sat in drop_sats or (low_drop and el < 30)):
                cn0 -= drop_db
            rows.append({"epoch": f"{e:06d}", "utc": f"t{e}", "sat": sat, "elev": float(el), "cn0": cn0})
    return rows


four = ("GPS08", "GPS10", "GPS15", "GPS21")
assert not g.interference_check(session())["candidate"]                                    # quiet sky
assert g.interference_check(session(four, (20, 21)))["candidate"]                          # 4 sats x 2 epochs
assert not g.interference_check(session(four, (20,)))["candidate"]                         # 1 epoch only
assert not g.interference_check(session(four[:3], (20, 21)))["candidate"]                  # only 3 sats
assert not g.interference_check(session(four, (20, 21), drop_db=4.0))["candidate"]         # under 6 dB
assert not g.interference_check(session(("GPS12",), (20, 21), low_drop=True))["candidate"]  # low elevation ignored
assert not g.interference_check(session(four, (3, 4), n=8))["candidate"]                   # no baseline yet
r = g.interference_check(session(four, (20, 21)))
assert r["events"][0]["epoch"] == "000021" and abs(r["events"][0]["worst_db"] - 10.0) < 1e-9


# --- the Hannibal hook: new notices once, state survives a failed fetch --------------------------------
class FakeNet:
    def __init__(self, ok=True):
        self.ok = ok

    def request(self, method, url, **kw):
        if not self.ok:
            return Result(None, error="ConnectionError")
        return Result(OA if "navcen" in url else GAL)


with tempfile.TemporaryDirectory() as tmp:
    state = Path(tmp) / "seen.json"
    first = g.gnss_routine_scan(state, None, net=FakeNet())
    assert len(first) == 4 and state.exists()
    assert g.gnss_routine_scan(state, None, net=FakeNet()) == []            # second run: nothing new
    before = state.read_text()
    assert g.gnss_routine_scan(state, None, net=FakeNet(ok=False)) == []    # outage: nothing, no alarm
    assert state.read_text() == before                                      # and the memory is kept
    assert json.loads(before) and "GPS:2026048" in json.loads(before)

assert "Osmosdr_Signal_Source" in g.GNSS_SDR_CONF and "1575420000" in g.GNSS_SDR_CONF
print("PASS: hannibal_gnss (NAVCEN/GSC parsing, routine vs outage, new-only, NMEA checksum, C/N0 log, "
      "interference rules, failed fetch)")
