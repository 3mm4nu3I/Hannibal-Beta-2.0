#!/usr/bin/env python3
"""Offline tests for hannibal_kessler (no network). Run: python test_hannibal_kessler.py"""
import math

import hannibal_kessler as k

HEADER = ("OBJECT_NAME,OBJECT_ID,NORAD_CAT_ID,OBJECT_TYPE,OPS_STATUS_CODE,OWNER,LAUNCH_DATE,LAUNCH_SITE,"
          "DECAY_DATE,PERIOD,INCLINATION,APOGEE,PERIGEE,RCS,DATA_STATUS_CODE,ORBIT_CENTER,ORBIT_TYPE\n")
SAMPLE = HEADER + "\n".join([
    "STARLINK-1,2019-029A,44235,PAY,+,US,2019-05-24,AFETR,,94,53,460,455,,,EA,ORB",
    "STARLINK-2,2019-029B,44236,PAY,+,US,2019-05-24,AFETR,,94,53,462,458,,,EA,ORB",
    "FENGYUN 1C DEB,1999-025A,29000,DEB,,PRC,1999-05-10,TSC,,101,98,880,840,0.05,,EA,ORB",
    "FENGYUN 1C DEB,1999-025B,29001,DEB,,PRC,1999-05-10,TSC,,101,98,870,850,0.07,,EA,ORB",
    "OLD SAT,1970-001A,4000,PAY,D,US,1970-01-01,AFETR,1990-01-01,95,30,500,480,1.0,,EA,ORB",
    "LUNAR,2020-001A,50000,PAY,+,US,2020-01-01,AFETR,,,,,,,,MO,ORB",
])

rows = k.parse_satcat(SAMPLE)
assert len(rows) == 6

# on-orbit logic: decayed and non-Earth objects are excluded
snap = k.snapshot(rows, "2026-10-22")
assert snap["in_orbit"] == 4, snap
assert snap["by_type"] == {"PAY": 2, "DEB": 2}, snap
assert snap["active_payloads"] == 2 and snap["constellations"]["Starlink"] == 2
assert k.snapshot(rows, "1980-01-01")["in_orbit"] == 1          # only OLD SAT existed then

# growth: last year counted at the given date
g = k.growth(rows, first_year=2018, when="2026-10-22")
assert g[0]["year"] == 2018 and g[0]["DEB"] == 2 and g[0]["PAY"] == 0
assert g[-1]["year"] == 2026 and g[-1]["PAY"] == 2

# shells: objects land in the right 50 km bins
sh = {s["lo_km"]: s for s in k.shells(rows, "2026-10-22")}
assert sh[450]["objects"] == 2 and sh[450]["starlink"] == 2
assert sh[850]["objects"] == 2 and sh[850]["debris"] == 2
assert abs(sh[850]["mean_rcs_m2"] - 0.06) < 1e-9
assert sh[500]["objects"] == 0 and sh[500]["cascade_index"] == 0.0

# physics
assert abs(k.drag_lifetime_years(400) - 1) < 1e-9 and abs(k.drag_lifetime_years(1000) - 1500) < 1e-6
assert k.drag_lifetime_years(450) < k.drag_lifetime_years(850) < k.drag_lifetime_years(1450)
e = k.bullet_energy_j()                                          # 1 cm Al at 10 km/s
assert 70_000 < e < 71_500, e
vol = k.shell_volume_km3(450, 500)
assert abs(vol - 4 / 3 * math.pi * ((6378.137 + 500) ** 3 - (6378.137 + 450) ** 3)) < 1
# critical count scales inversely with lifetime and fragments
c1 = k.critical_count(1.0, vol, 10, 100, 5)
assert abs(k.critical_count(1.0, vol, 10, 100, 50) - c1 / 10) < 1e-6
assert abs(k.critical_count(1.0, vol, 10, 200, 5) - c1 / 2) < 1e-6
# cascade index = N / N_crit  ->  runaway condition k*C > N/tau holds exactly at index 1
n = c1
rate = k.collisions_per_year(n, 1.0, vol, 10)
assert abs(100 * rate - n / 5) / (n / 5) < 1e-9

assert k.classify(1.2) == "OVER THE LINE" and k.classify(0.5) == "accumulating" and k.classify(0.05) == "self-cleaning"
assert k.breakups(rows, "2026-10-22") == [("FENGYUN 1C", 2)]
assert "KESSLER CASCADE WATCH" in k.format_report(k.analyse(rows, "2026-10-22"))

print("PASS: hannibal_kessler (snapshot, growth, shells, physics, threshold, report)")
