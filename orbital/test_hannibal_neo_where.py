#!/usr/bin/env python3
"""Offline tests for hannibal_neo_where (no network). Run: python test_hannibal_neo_where.py

The Horizons tables are trimmed copies of real NASA/JPL replies for 99942 Apophis fetched on 23 Oct 2026."""
from datetime import datetime, timezone

import hannibal_neo_where as w
from hannibal_net import Result

HDR_GEO = (" Date__(UT)__HR:MN, , , R.A.__(a-app), DEC___(a-app),    APmag,  S-brt,             delta,     deldot,"
           "  SMAA_3sig, SMIA_3sig,   Theta, Area_3sig,  RNG_3sigma, RNGRT_3sig,")
GEO = HDR_GEO + """
******
$$SOE
 2029-Apr-13 21:38, , , 130.166768165,  26.518051385,    3.677,  4.180,  0.00025481761644, -0.4956026,      6.878,     4.351,  59.682,     94.01,      3.2447,  0.0001001,
 2029-Apr-13 21:42, , , 127.551952725,  27.843689380,    3.765,  4.232,  0.00025424700123, -0.2153462,      6.842,     4.387,  67.022,     94.30,      3.2660,  0.0001058,
 2029-Apr-13 21:46, , , 124.866323564,  29.122239128,    3.861,  4.285,  0.00025412724901,  0.0661432,      6.845,     4.544,  75.382,     97.72,      3.2805,  0.0001113,
$$EOE
"""
HDR_TOPO = (" Date__(UT)__HR:MN, , , R.A.__(a-app), DEC___(a-app), Azimuth_(a-app), Elevation_(a-app),    APmag,  S-brt,"
            "             delta,     deldot,  SMAA_3sig, SMIA_3sig,   Theta, Area_3sig,  RNG_3sigma, RNGRT_3sig,")
TOPO = HDR_TOPO + """
******
$$SOE
 2029-Apr-13 18:30,*, , 150.0,  10.0,   100.0,      -2.0,    4.000,  4.241,  0.00050000000000, -0.0535245,      7.490,     5.113,  65.171,    120.31,      3.2786,  0.0000941,
 2029-Apr-13 19:00,*, , 150.0,  10.0,   100.0,       5.0,    3.900,  4.241,  0.00040000000000, -0.0535245,      7.490,     5.113,  65.171,    120.31,      3.2786,  0.0000941,
 2029-Apr-13 21:38, , , 125.791595473,  23.683976811,   249.905379320,      59.401064185,    3.440,  4.241,  0.00021721963654, -0.0535245,      7.490,     5.113,  65.171,    120.31,      3.2786,  0.0000941,
 2029-Apr-13 21:42, , , 122.594055938,  25.099626986,   256.277188463,      57.075626264,    3.561,  4.307,  0.00021743203640,  0.3179601,      7.431,     5.340,  72.882,    124.66,      3.2910,  0.0000983,
 2029-Apr-13 21:46, , , 119.338420200,  26.436738775,   261.890158369,      54.515561390,    3.694,  4.375,  0.00021823801934,  0.6858520,      7.418,     5.768,  84.110,    134.41,      3.2929,  0.0001022,
$$EOE
"""

# --- sidereal time and sub-point -------------------------------------------------------------------
j2000 = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)
assert abs(w.gast_deg(j2000) - 280.4568) < 0.01            # GMST 280.4606 + equation of equinoxes (-0.0039)

geo = w.parse_horizons({"result": GEO})
assert len(geo) == 3 and geo[2]["time"] == datetime(2029, 4, 13, 21, 46, tzinfo=timezone.utc)
assert abs(geo[2]["delta_km"] - 38_016.9) < 1 and abs(geo[2]["rng3_km"] - 3.2805) < 1e-6
lat, lon = w.sub_point(geo[2]["ra_deg"], geo[2]["dec_deg"], geo[2]["time"])
assert abs(lat - 29.29) < 0.05 and abs(lon - -44.00) < 0.05, (lat, lon)     # mid-Atlantic at closest approach

b = w.box_km(geo[2])
assert abs(b["along_km"] - 2.52) < 0.05 and abs(b["across_km"] - 1.67) < 0.05 and b["range_pm_km"] == 3.2805

t = w.track(geo)
assert min(t, key=lambda x: x["distance_km"])["time"] == "2029-Apr-13 21:46"
assert abs(t[2]["altitude_km"] - (38_016.9 - w.EARTH_EQ_RADIUS_KM)) < 1

# --- parse errors are refused, never guessed ---------------------------------------------------------
for bad in ({"result": "No matches found."}, {"error": "Cannot interpret date"}, {}, None):
    try:
        w.parse_horizons(bad)
        raise AssertionError(f"accepted {bad!r}")
    except ValueError:
        pass
assert w._horizons_error({"error": "bad"}).startswith("Horizons:")
assert w._horizons_error({"result": GEO}) == ""

# --- impossible-event test off Lisbon ----------------------------------------------------------------
topo = w.parse_horizons({"result": TOPO})
assert topo[0]["sun"] == "*" and topo[2]["sun"] == ""
tc = w.target_check(topo, w.LISBON_OFFSHORE)
assert tc["verdict"] == w.IMPOSSIBLE
assert tc["closest_time"] == "2029-Apr-13 21:38" and abs(tc["closest_km"] - 32_496) < 2
assert abs(tc["nearest_edge_km"] - (tc["closest_km"] - 3.2786)) < 0.01
assert tc["visible_from"] == "2029-Apr-13 19:00"             # first row is below the horizon
assert tc["dark_from"] == "2029-Apr-13 21:38"                 # 19:00 is up but in daylight
assert abs(tc["brightest_mag"] - 3.44) < 1e-6

# a point the uncertainty reaches down to -> POSSIBLE (the test can fail, it is not hard-wired)
graze = [dict(topo[2], delta_km=60.0, rng3_km=10.0)]
assert w.target_check(graze, (0.0, 0.0, "test"))["verdict"] == w.POSSIBLE

# --- request parameters ------------------------------------------------------------------------------
p = w.horizons_params("99942", j2000, j2000, site=(38.70, -9.60))
assert p["COMMAND"] == "'99942;'" and p["CENTER"] == "'coord@399'" and p["SITE_COORD"] == "'350.40000,38.70000,0'"
assert w.horizons_params("2024 YR4", j2000, j2000)["COMMAND"] == "'DES=2024 YR4;'"


# --- run() through a fake network --------------------------------------------------------------------
class FakeNet:
    def __init__(self, ok=True):
        self.ok, self.calls = ok, []

    def get_json(self, url, params=None, **kw):
        self.calls.append(params)
        if not self.ok:
            return Result(None, error="ConnectionError")
        return Result({"result": TOPO if params.get("CENTER") == "'coord@399'" else GEO})


PASSES = [{"date": "2029-Apr-13 21:46", "distance_km": 38_011.5, "time_uncertainty": "< 00:01", "rough": False},
          {"date": "2051-Apr-20 02:05", "distance_km": 6_206_849.0, "time_uncertainty": "08:07", "rough": False}]
net = FakeNet()
r, err = w.run("99942", net=net, passes=PASSES, sentry={"state": "removed"})
assert not err and r["target"]["verdict"] == w.IMPOSSIBLE and "note" not in r["target"]
assert len(r["envelope"]) == 2 and len(net.calls) == 3          # track, one extra pass, target
text = w.format_report(r)
assert "IMPOSSIBLE" in text and "Atlantic off Lisbon" in text and "<- closest" in text

r, _ = w.run("99942", net=FakeNet(), passes=PASSES, sentry={"state": "listed"})
assert "keyhole" in r["target"]["note"]
r, _ = w.run("99942", net=FakeNet(), passes=PASSES, sentry={"state": "unknown"})
assert "only this flyby" in r["target"]["note"]

r, err = w.run("99942", net=FakeNet(ok=False), passes=PASSES, sentry={"state": "removed"})
assert r is None and err.startswith("JPL Horizons unavailable")    # no verdict without data
r, err = w.run("99942", net=FakeNet(), passes=[], sentry={"state": "removed"})
assert r is None and "no Earth close approach" in err

print("PASS: hannibal_neo_where (sidereal time, sub-point, 3-sigma box, parse errors, Lisbon test, fake net)")
