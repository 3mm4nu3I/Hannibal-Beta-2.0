#!/usr/bin/env python3
"""Offline tests for hannibal_obsplan and hannibal_astrometry_check (no network).
Run: python test_hannibal_obsplan_astrometry.py

The Horizons rows are trimmed copies of real replies for 99942 Apophis fetched on 23 Oct 2026."""
import math
from datetime import datetime, timezone

import hannibal_astrometry_check as ac
import hannibal_obsplan as op

# --- exposure model ---------------------------------------------------------------------------------
assert abs(op.limiting_mag(1.0, 60) - op.M0_1M_60S) < 1e-9
assert abs(op.limiting_mag(0.4, 60) - (op.M0_1M_60S + 2.5 * math.log10(0.4))) < 1e-9
assert abs(op.limiting_mag(1.0, 60, snr=50) - (op.M0_1M_60S - 2.5 * math.log10(5))) < 1e-9
assert abs(op.single_exposure_s(2.0) - 60.0) < 1e-9 and op.single_exposure_s(0.0) == op.MAX_SINGLE_S
assert op.integration_minutes(op.M0_1M_60S, 1.0, 1.0, 10) == 1.0          # at the limit: 60 s
assert op.integration_minutes(op.M0_1M_60S + 1.25, 1.0, 1.0, 10) == 10.0  # 1.25 mag fainter: 10x longer
assert op.integration_minutes(25.0, 0.4, 1.0, 50) is None                  # hopeless -> None, not a number

# --- Horizons parsing and nights (real header, a cut-off marker, a daylight row) ----------------------
HDR = (" Date__(UT)__HR:MN, , , dRA*cosD, d(DEC)/dt, Azimuth_(a-app), Elevation_(a-app),    APmag,  S-brt,"
       "     S-O-T,/r,  T-O-M, MN_Illu%,  RA_3sigma, DEC_3sigma,")
TXT = ("Center geodetic : 149.0706, -31.2729871, 1.17503  {E-lon(deg),Lat(deg),Alt(km)}\n" + HDR + """
$$SOE
 2027-Jan-15 10:00, , , 179.9408,  66.62247,   284.18,      45.6,   20.797,  3.604,   52.8157,/T,   86.4,  48.9,      0.002,      0.002,
 2027-Jan-15 10:30,A, , 179.9408,  66.62247,   284.18,      50.1,   20.797,  3.604,   52.8157,/T,   86.4,  48.9,      0.002,      0.002,

>..... Elevation Cut-off Requested .....<

 2027-Jan-15 19:00,C,m, 179.9,  66.6,   284.18,      40.0,   20.8,  3.6,   52.8,/T,   86.4,  48.9,      0.002,      0.002,
 2027-Jan-16 11:00, ,m, 179.9,  66.6,   284.18,      55.0,   20.8,  3.6,   52.8,/T,   12.0,  48.9,      0.002,      0.002,
$$EOE
""")
rows = op.parse({"result": TXT})
assert len(rows) == 4 and rows[0]["site_lon"] == 149.0706
assert abs(rows[0]["rate"] - math.hypot(179.9408, 66.62247) / 60) < 1e-9
assert [op.usable(r) for r in rows] == [True, True, False, False]     # civil twilight, then Moon 12 deg away
ns = op.nights(rows)
assert len(ns) == 1 and ns[0]["hours"] == 1.0 and ns[0]["best"]["elev"] == 50.1   # Australia: one local night

# --- O-C residuals ----------------------------------------------------------------------------------
t = datetime(2027, 1, 18, 6, 0, tzinfo=timezone.utc)
pred = [{"ra": 352.346293568, "dec": -5.049447963, "rate_ra": 180.4264, "rate_dec": 67.04575,
         "sig_ra": 0.002 / 3, "sig_dec": 0.002 / 3}]
same = ac.residuals([{"utc": t, "ra": 352.346293568, "dec": -5.049447963, "station": "V37", "sigma": 0.3}], pred)
assert abs(same[0]["dra"]) < 1e-6 and not same[0]["flag"]
# 1.5" along the motion = 1.5 / (192.5"/h / 3600) = 28.05 s clock error
off = 1.5 / 3600 / math.cos(math.radians(-5.049447963))
r = ac.residuals([{"utc": t, "ra": 352.346293568 + off * 180.4264 / math.hypot(180.4264, 67.04575),
                   "dec": -5.049447963 + 1.5 / 3600 * 67.04575 / math.hypot(180.4264, 67.04575),
                   "station": "V37", "sigma": 0.3}], pred)[0]
assert r["flag"] and abs(r["along_track"] - 1.5) < 0.01 and abs(r["clock_error_s"] - 28.05) < 0.1
# RA wrap at 0/360 deg
w = ac.residuals([{"utc": t, "ra": 0.0001, "dec": 0.0, "station": "X", "sigma": 0.3}],
                 [{"ra": 359.9999, "dec": 0.0, "rate_ra": 1, "rate_dec": 0, "sig_ra": 0.001, "sig_dec": 0.001}])
assert abs(w[0]["dra"] - 0.72) < 1e-6

# tracklets: one bad point never flags; three consistent offset points do
pts = [dict(same[0], dra=0.1 * i, ddec=0.0) for i in range(3)]
assert not ac.tracklets(pts)[0]["flag"]
shifted = [dict(same[0], dra=2.0, ddec=0.0) for _ in range(3)]
assert ac.tracklets(shifted)[0]["flag"]
assert not ac.tracklets([dict(same[0], dra=50.0)])[0]["flag"]            # single point: not a tracklet flag

print("PASS: hannibal_obsplan + hannibal_astrometry_check (exposure model, parsing, nights, O-C, clock, wrap, tracklets)")
