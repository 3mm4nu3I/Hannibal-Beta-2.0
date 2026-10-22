#!/usr/bin/env python3
"""Offline tests for hannibal_neo (no network). Run: python test_hannibal_neo.py

The payloads are trimmed copies of real NASA/JPL responses fetched on 22 Oct 2026."""
import hannibal_neo as neo
from hannibal_net import Result

FIELDS = ["des", "orbit_id", "jd", "cd", "dist", "dist_min", "dist_max", "v_rel", "v_inf", "t_sigma_f", "h"]
CAD_APOPHIS = {"count": "2", "fields": FIELDS, "data": [
    ["99942", "220", "2462240.407091969", "2029-Apr-13 21:46", "0.000254090910419299", "0.000254068999976389",
     "0.000254112821017663", "7.42253895678452", "5.84135589753103", "< 00:01", "19.09"],
    ["99942", "220", "2463500.0", "2116-Apr-12 21:44", "0.0175609", "0.00103509", "0.104846",
     "8.0", "7.9", "2_03:00", "19.09"]]}
CAD_BENNU = {"count": "1", "fields": FIELDS, "data": [
    ["101955", "118", "2501000.0", "2135-Sep-25 07:49", "0.00136393", "0.00130312", "0.00142609",
     "6.0", "5.99", "00:12", "20.63"]]}
SENTRY_REMOVED = {"signature": {"source": "NASA/JPL Sentry Data API", "version": "2.0"},
                  "removed": "2021-02-21 08:22:28", "error": "specified object removed"}
SENTRY_BENNU = {"summary": {"ip": "0.000571699999999996", "ps_cum": "-1.40", "n_imp": 157, "method": "MC",
                            "fullname": "101955 Bennu (1999 RQ36)", "ts_max": None},
                "data": [{"date": "2290-09-25.12", "ip": "1.000e-07"}, {"date": "2178-09-24.40", "ip": "2.0e-07"},
                         {"date": "2182-09-24.59", "ip": "3.7e-04"}]}
SENTRY_NOT_FOUND = {"error": "specified object not found"}
SBDB_APOPHIS = {"object": {"fullname": "99942 Apophis (2004 MN4)"},
                "orbit": {"orbit_id": "220", "condition_code": "0", "data_arc": "6599", "n_obs_used": 7370,
                          "last_obs": "2022-04-09"},
                "phys_par": [{"name": "diameter", "value": "0.34"}, {"name": "H", "value": "19.09"}]}

# --- single pass geometry ------------------------------------------------------------------------
p = neo.approaches_from_cad(CAD_APOPHIS, "99942")
assert len(p) == 2
a29 = p[0]
assert abs(a29["distance_km"] - 38_011.5) < 1 and abs(a29["min_km"] - 38_008.2) < 1
assert abs(a29["window_km"] - 6.6) < 0.1
assert abs(a29["clearance_above_atmosphere_km"] - (38_008.2 - 6_378.137 - 100)) < 1
assert a29["inside_geo"] and not a29["rough"] and a29["verdict"] == neo.EXCLUDED
assert a29["margin_ratio"] > 4_000
assert p[1]["rough"] and p[1]["verdict"] == neo.EXCLUDED          # 2116: window wider than the distance

# a pass whose nearest edge dips into the atmosphere is not excluded
graze = neo.assess_pass("2099-Jan-01 00:00", 0.0001, 6_400 / neo.AU_KM, 0.0002, 10.0)
assert graze["verdict"] == neo.NOT_EXCLUDED and graze["clearance_above_atmosphere_km"] < 0

# rows for another object are refused (the filter must be honoured)
try:
    neo.approaches_from_cad(CAD_BENNU, "99942")
    raise AssertionError("foreign object accepted")
except ValueError:
    pass

# --- Sentry states ---------------------------------------------------------------------------------
assert neo.sentry_status(SENTRY_REMOVED) == {"state": "removed", "removed": "2021-02-21 08:22:28"}
assert neo.sentry_status(SENTRY_NOT_FOUND) == {"state": "not_listed"}
b = neo.sentry_status(SENTRY_BENNU)
assert b["state"] == "listed" and b["n_imp"] == 157 and b["first_date"] == "2178" and b["last_date"] == "2290"
assert neo.sentry_status({"error": "HTTP 503"})["state"] == "unknown"

# --- overall verdict -------------------------------------------------------------------------------
r = neo.analyse("99942", CAD_APOPHIS, SENTRY_REMOVED, SBDB_APOPHIS, start="2026-10-22")
assert r["verdict"] == neo.EXCLUDED and "removed from" in r["reason"]
assert r["orbit"]["name"] == "99942 Apophis (2004 MN4)" and r["orbit"]["condition_code"] == "0"

# Bennu: every pass clears Earth, yet Sentry still lists impacts -> NOT EXCLUDED (the keyhole case)
r = neo.analyse("101955", CAD_BENNU, SENTRY_BENNU, None)
assert all(x["verdict"] == neo.EXCLUDED for x in r["passes"])
assert r["verdict"] == neo.NOT_EXCLUDED and "1 in 1,749" in r["reason"]
assert "keyhole" in neo.format_report(r)

# never listed, no approaches in the window (Eros-like) -> excluded
assert neo.analyse("433", {"count": "0"}, SENTRY_NOT_FOUND, None)["verdict"] == neo.EXCLUDED
# every pass clears but Sentry could not be reached -> no verdict claimed
assert neo.analyse("99942", CAD_APOPHIS, {"error": "HTTP 503"}, None)["verdict"] == neo.NO_DATA
# a pass reaching the atmosphere -> not excluded even when Sentry has removed the object
bad = {"fields": FIELDS, "data": [["9", "1", "0", "2099-Jan-01 00:00", "0.0001", str(6_400 / neo.AU_KM),
                                   "0.0002", "10", "10", "", "20"]]}
assert neo.analyse("9", bad, SENTRY_REMOVED, None)["verdict"] == neo.NOT_EXCLUDED


# --- run() through a fake network -------------------------------------------------------------------
class FakeNet:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def get_json(self, url, params=None, **kw):
        self.calls.append((url, params))
        for key, res in self.answers.items():
            if key in url:
                return res
        return Result(None, error="unexpected url")


net = FakeNet({"cad.api": Result(CAD_APOPHIS), "sentry.api": Result(SENTRY_REMOVED), "sbdb.api": Result(SBDB_APOPHIS)})
result, err = neo.run("99942", net=net)
assert not err and result["verdict"] == neo.EXCLUDED
cad_params = net.calls[0][1]
assert cad_params["des"] == "99942" and cad_params["date-max"] == neo.DEFAULT_END   # filter sent as des=

result, err = neo.run("zzzz9", net=FakeNet({"cad.api": Result(None, error="HTTP 400 from ssd-api.jpl.nasa.gov"),
                                            "sentry.api": Result(SENTRY_NOT_FOUND), "sbdb.api": Result({})}))
assert result is None and "does not recognise" in err

result, err = neo.run("99942", net=FakeNet({"cad.api": Result(None, error="ConnectionError"),
                                            "sentry.api": Result(None, error="ConnectionError"),
                                            "sbdb.api": Result(None, error="ConnectionError")}))
assert result is None and err.startswith("JPL unavailable")

result, err = neo.run("99942", net=FakeNet({"cad.api": Result(None, error="Timeout"),
                                            "sentry.api": Result(SENTRY_REMOVED), "sbdb.api": Result({})}))
assert result["verdict"] == neo.NO_DATA      # never claims exclusion without the close-approach data

print("PASS: hannibal_neo (pass geometry, foreign rows, Sentry states, keyhole case, verdicts, fake net)")
