#!/usr/bin/env python3
"""Offline tests for hannibal_crosscheck (no network). Run: python test_hannibal_crosscheck.py

The JPL and ESA replies are trimmed copies of real ones for 99942 Apophis fetched on 23 Oct 2026."""
import hashlib
import json
import tempfile
from datetime import datetime, timezone

import hannibal_crosscheck as x
from hannibal_net import Result

FIELDS = ["des", "orbit_id", "jd", "cd", "dist", "dist_min", "dist_max", "v_rel", "v_inf", "t_sigma_f", "h"]
CAD = {"count": "3", "fields": FIELDS, "data": [
    ["99942", "220", "2462240.407091969", "2029-Apr-13 21:46", "0.000254090910419299", "0.000254068999976389",
     "0.000254112821017663", "7.42253895678452", "5.84135589753103", "< 00:01", "19.09"],
    ["99942", "220", "2470281.587043906", "2051-Apr-20 02:05", "0.0414902230254537", "0.0399038645943395",
     "0.0430769570279036", "4.69385481977169", "4.68015322050512", "08:07", "19.09"],
    ["99942", "220", "2493800.0", "2116-Apr-12 21:44", "0.017560896582075", "0.00103509", "0.104846",
     "8.0", "7.9", "7_11:21", "19.09"]]}
CLOLIN = """TIME SCALE = 'UTC'
BODY         CALENDAR-TIME     MJD-TIME        TIME-UNCERT.     NOM.-DISTANCE          MIN.-POSS.-DIST.       DIST.-UNCERT.         STRETCH   WIDTH     PROBABILITY
       EARTH 2021/03/06.05096  59279.050963511 2.578189792E-06  1.126513859353443E-01  1.126513840417332E-01  6.464040659148392E-10 4.357E-09 6.222E-10 1.00E+00
       EARTH 2029/04/13.90629  62239.906290151 5.921531403E-07  2.541065889903392E-04  2.540801519235249E-04  8.812361819802394E-09 8.927E-09 6.080E-09 1.00E+00
       EARTH 2051/04/19.81047  70280.810465650 1.288267983E-01  4.017314825596193E-02  3.818505915376491E-02  6.627020156462058E-04 6.628E-04 1.238E-07 1.00E+00
       EARTH 2109/06/11.26149  91517.261493888 1.120207922E+01  1.210465062328127E-01  1.113502369017203E-01  3.268062345103237E-03 3.654E-03 1.352E-06 1.00E+00
       EARTH 2116/04/08.31411  94010.314109610 1.525693175E+00  8.129632233619222E-02  1.401633870868264E-03  2.666139750521602E-02 2.666E-02 1.115E-07 1.00E+00
"""
SENTRY = '{"error":"specified object removed","signature":{"version":"2.0","source":"NASA/JPL Sentry Data API"},' \
         '"removed":"2021-02-21 08:22:28"}'
MODEL_PARS = [{"name": "A1", "value": "5.E-13", "sigma": "4.892E-13", "kind": "EST"},
              {"name": "A2", "value": "-2.901766637153165E-14", "sigma": "1.859E-16", "kind": "EST"},
              {"name": "ALN", "value": "1.", "sigma": None, "kind": "SET"}]


def sbdb(pars=MODEL_PARS):
    return json.dumps({"object": {"fullname": "99942 Apophis (2004 MN4)"},
                       "orbit": {"orbit_id": "220", "n_obs_used": 7370, "last_obs": "2022-04-09",
                                 "condition_code": "0", "model_pars": pars}})


SBDB = sbdb()
KE1 = """99942
 NGR   0.00000000000000E+00 -2.90012877256919E-04
! RMS    1.43322E-10   1.39504E-09   1.55280E-07   7.58889E-06   8.15420E-06   9.01435E-07   2.32321E-06
"""
RISK = """Last Update: 2026-10-23 18:51 UTC
Num/des.           Name       |   m  |   *=Y   |      Date/Time   |  IP max  | PS max |TS  | Vel km/s | Years     | IP cum   | PS cum |
2023VD3                       |   14 |    *    | 2034-11-08 17:08 |  2.35E-3 |  -2.67 |  0 |   21.01  | 2034-2039 |  2.35E-3 |  -2.67 |
"""
RWO = """version =   3
END_OF_HEADER
! Object      Obser ============= Date =============
 99942        O C   2004 03 15.10789       1.000E-05 04 06 08.080
 99942        O C K 2011 03 04.81625       1.000E-05 02 06 3
 99942        S S   2020 12 18.97667       1.000E-05 11 30 1
 99942        S s   2020 12 18.97667 1      -5634.1734000000
 99942        R c   2021 03 05 07:00:00  16852345.34209   0.14990
 99942        V c   2005 01 27 23:31:00    548781.78980   1.
 99942        O C   2022 04 09.12345       1.000E-05 10 00 00
"""
TODAY = datetime(2026, 10, 23, 21, 0, tzinfo=timezone.utc)


def records(**override):
    texts = {"jpl_cad": json.dumps(CAD), "jpl_sentry": SENTRY, "jpl_sbdb": SBDB, "esa_clolin": CLOLIN,
             "esa_risk_list": RISK, "esa_observations": RWO, "esa_orbit": KE1}
    texts.update(override)
    out = {}
    for k, t in texts.items():
        if t is None:
            out[k] = {"name": k, "ok": False, "error": "ConnectionError"}
        else:
            out[k] = {"name": k, "ok": True, "text": t, "sha256": hashlib.sha256(t.encode()).hexdigest(),
                      "bytes": len(t.encode()), "url": "u", "params": {}, "retrieved_utc": "2026-10-23T21:00:00Z"}
    return out


# --- parsing ---------------------------------------------------------------------------------------
esa = x.parse_clolin(CLOLIN)
assert len(esa) == 5
e29 = esa[1]
assert e29["time_utc"].strftime("%H:%M:%S") == "21:45:03" and abs(e29["distance_km"] - 38_013.8) < 1
jpl = x.jpl_passes(CAD)
assert jpl[0]["time_utc"].strftime("%H:%M:%S") == "21:44:50"        # 21:46 TDB minus 69.184 s
assert abs(jpl[0]["sigma_km"] - 6.555 / 6) < 0.01

obs = x.observations_summary(RWO)
assert obs == {"count": 6, "optical": 3, "from_space": 1, "radar": 2, "first": "2004-03-15", "last": "2022-04-09"}
assert x.risk_list_lines(RISK, "99942") == [] and len(x.risk_list_lines(RISK, "2023 VD3")) == 1

# --- the real comparison: everything agrees, nothing reaches Earth ---------------------------------
a = x.analyse("99942", records(), today=TODAY)
assert a["verdict"] == x.CONSISTENT, a
p = {r["date"]: r for r in a["passes"]}
r29 = p["2029-Apr-13 21:46"]
assert r29["status"] == x.AGREE and abs(r29["diff_km"] - 2.3) < 0.3 and r29["n_sigma"] < 3
assert abs(r29["time_diff_s"]) < 60                                   # same minute in UTC once TDB is converted
assert p["2116-Apr-12 21:44"]["status"] == x.AGREE                    # wildly different km, but huge sigma
assert any(r["status"] == x.ONLY_ESA for r in a["passes"])            # 2109: ESA lists it, JPL does not
assert a["jpl_sentry"].startswith("removed") and a["esa_risk_list"] == "not listed"
assert a["esa_observations"]["last"] == "2022-04-09" and not a["notes"]

# --- each concern trigger fires on its own -----------------------------------------------------------
moved = CLOLIN.replace("2.541065889903392E-04", "2.545000000000000E-04")      # ESA 2029 nominal +59 km
a = x.analyse("99942", records(esa_clolin=moved), today=TODAY)
assert a["verdict"] == x.CONCERN and "sigma apart" in a["reason"]

hit = CLOLIN.replace("2.540801519235249E-04", "4.000000000000000E-05")        # min possible 5,984 km
assert "reaches the atmosphere" in x.analyse("99942", records(esa_clolin=hit), today=TODAY)["reason"]

listed = RISK + "99942         Apophis         |  340 |    *    | 2068-04-12 13:00 |  1.0E-5  |  -3.00 |  0 |  12.00  | 2068-2068 |  1.0E-5  |  -3.00 |\n"
assert "ESA risk list includes" in x.analyse("99942", records(esa_risk_list=listed), today=TODAY)["reason"]

sentry_listed = json.dumps({"summary": {"ip": "1e-5", "n_imp": 1}, "data": [{"date": "2068-04-12"}]})
assert "Sentry lists" in x.analyse("99942", records(jpl_sentry=sentry_listed), today=TODAY)["reason"]

newer = RWO + " 99942        O C   2027 01 05.12345       1.000E-05 10 00 00\n"
assert "new orbit" in " ".join(x.analyse("99942", records(esa_observations=newer), today=TODAY)["notes"])

# --- C6: a push the Yarkovsky model of solution 220 does not explain ----------------------------------
assert x.esa_nongrav(KE1)["A2"][0] == -2.90012877256919e-14
ng = x.analyse("99942", records(), today=TODAY)["nongrav"]
assert ng["jpl"]["A2"][0] == x.A2_BASELINE and abs(ng["esa"]["A2"][1] - 2.32321e-16) < 1e-21
jump = [dict(p, value="-2.99E-14") if p["name"] == "A2" else p for p in MODEL_PARS]
assert "C6: JPL Yarkovsky term moved" in x.analyse("99942", records(jpl_sbdb=sbdb(jump)), today=TODAY)["reason"]
side = MODEL_PARS + [{"name": "A3", "value": "4.0E-15", "sigma": "5.0E-16", "kind": "EST"}]
assert "out-of-plane push" in x.analyse("99942", records(jpl_sbdb=sbdb(side)), today=TODAY)["reason"]
radial = [dict(p, value="5.0E-12") if p["name"] == "A1" else p for p in MODEL_PARS]
assert "radial push" in x.analyse("99942", records(jpl_sbdb=sbdb(radial)), today=TODAY)["reason"]
esa_off = KE1.replace("-2.90012877256919E-04", "-3.00000000000000E-04")
assert "JPL and ESA disagree on the Yarkovsky" in x.analyse("99942", records(esa_orbit=esa_off), today=TODAY)["reason"]
assert "C6 (unexplained push) not checked" in " ".join(
    x.analyse("99942", records(jpl_sbdb=None), today=TODAY)["notes"])
assert "not checkable" in " ".join(x.analyse("99942", records(jpl_sbdb=sbdb([])), today=TODAY)["notes"])

# --- no data never becomes an all-clear --------------------------------------------------------------
assert x.analyse("99942", records(esa_clolin=None), today=TODAY)["verdict"] == x.NO_DATA
assert x.analyse("99942", records(jpl_cad=None), today=TODAY)["verdict"] == x.NO_DATA
a = x.analyse("99942", records(esa_risk_list=None), today=TODAY)
assert a["verdict"] == x.CONSISTENT and "could not be reached" in a["notes"][0]

# --- evidence folder: hashes match the saved bytes ---------------------------------------------------
recs = records(esa_observations=RWO * 40000)                         # > SMALL_BYTES: hash + summary only
a = x.analyse("99942", recs, today=TODAY)
with tempfile.TemporaryDirectory() as tmp:
    folder = x.write_evidence(recs, a, tmp)
    man = json.loads((folder / "manifest.json").read_text())
    for entry in man["sources"]:
        if entry.get("saved_as"):
            assert hashlib.sha256((folder / entry["saved_as"]).read_bytes()).hexdigest() == entry["sha256"]
        else:
            assert entry["name"] == "esa_observations" and entry["summary"]["count"] > 0
    assert len((folder / "SHA256SUMS").read_text().splitlines()) == 6


# --- capture() asks live: no cache, no stale fallback ------------------------------------------------
class FakeNet:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kw):
        self.calls.append((url, kw))
        name = kw["params"].get("file") or url
        text = {"99942.clolin": CLOLIN, "esa_risk_list": RISK, "99942.rwo": RWO, "99942.ke1": KE1}.get(name)
        if text is None:
            text = json.dumps(CAD) if "cad" in url else SENTRY if "sentry" in url else SBDB
        return Result(text)


net = FakeNet()
recs = x.capture("99942", net=net)
assert all(kw["ttl"] == 0 and kw["stale_ok"] is False and kw["expect"] == "text" for _, kw in net.calls)
assert all(r["ok"] and len(r["sha256"]) == 64 for r in recs.values())
assert x.analyse("99942", recs, today=TODAY)["verdict"] == x.CONSISTENT
assert "INDEPENDENT CROSS-CHECK" in x.format_report(x.analyse("99942", recs, today=TODAY))

print("PASS: hannibal_crosscheck (parsing, JPL/ESA agreement, every concern trigger, no-data, evidence hashes)")
