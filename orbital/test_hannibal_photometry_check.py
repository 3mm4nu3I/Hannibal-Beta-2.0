#!/usr/bin/env python3
"""Offline tests for hannibal_photometry_check (criterion C9). Run: python test_hannibal_photometry_check.py"""
from datetime import datetime, timedelta, timezone

import hannibal_photometry_check as p

HDR = (" Date__(UT)__HR:MN:SC.fff, , ,   APmag,  S-brt,             delta,     deldot,     S-T-O,")
TXT = HDR + """
$$SOE
 2027-Jan-18 06:00:00.000, ,m,  20.807,  3.623,  0.95950620417015, -1.6422538,   64.6861,
$$EOE
"""
pr = p.parse({"result": TXT})
assert pr[0]["vpred"] == 20.807 and abs(pr[0]["delta_km"] - 143_540_085) < 1 and pr[0]["phase"] == 64.6861
for bad in ({"result": "nothing"}, {}, None):
    try:
        p.parse(bad)
        raise AssertionError("accepted a reply without a table")
    except ValueError:
        pass

# the distance signature: 10% closer -> 0.23 mag brighter; Bram's 28,500 vs 38,011 km -> -0.62 mag
import math
assert abs(5 * math.log10(0.9) + 0.229) < 0.001 and abs(5 * math.log10(28_500 / 38_011) + 0.625) < 0.001


def obs(station, night0, offsets, band="r", err=0.03, per_night=6, constant=0.0):
    """Synthetic residual rows: `offsets` is the extra brightness per night (negative = brighter)."""
    rows = []
    for i, off in enumerate(offsets):
        t0 = night0 + timedelta(days=i)
        for k in range(per_night):
            jitter = (-1) ** k * 0.02
            rows.append({"utc": t0 + timedelta(minutes=20 * k), "mag": 0, "err": err, "station": station, "band": band,
                         "resid": constant + off + jitter, "vpred": 20.8, "delta_km": 1.4e8, "phase": 60.0})
    return rows


n0 = datetime(2027, 1, 18, 22, 0, tzinfo=timezone.utc)

# a constant offset (H, filter, zero point) cancels out completely
r = p.evaluate(p.nights(obs("V37", n0, [0, 0, 0, 0, 0], constant=0.45)))
assert not r["c9_fired"] and abs(r["series"][0]["baseline"] - 0.45) < 1e-9 and "not fired" in r["verdict"]

# nights crossing UTC midnight stay one night
assert len(p.nights(obs("V37", datetime(2027, 1, 18, 23, 30, tzinfo=timezone.utc), [0]))) == 1

# a drift within the tumbling allowance (0.25 mag) never fires
assert not p.evaluate(p.nights(obs("V37", n0, [0, 0, 0, -0.25, -0.25])))["stations_flagged"]
# one bright night is not enough
assert not p.evaluate(p.nights(obs("V37", n0, [0, 0, 0, -0.5, 0])))["stations_flagged"]
# a big drift with huge errors (inside 3 sigma) does not count
noisy = p.nights(obs("V37", n0, [0, 0, 0, -0.4, -0.4], err=0.6, per_night=1))
assert not p.evaluate(noisy)["stations_flagged"]
# two bright nights in a row on ONE station: a candidate, not a fire
one = p.evaluate(p.nights(obs("V37", n0, [0, 0, 0, -0.5, -0.5])))
assert one["stations_flagged"] == ["V37"] and not one["c9_fired"] and "second" in one["verdict"]
# the same on a second, independent station: C9 fires
two = p.evaluate(p.nights(obs("V37", n0, [0, 0, 0, -0.5, -0.5]) + obs("K91", n0, [0, 0, 0, -0.45, -0.5], band="V")))
assert two["c9_fired"] and two["stations_flagged"] == ["K91", "V37"]
v = [s for s in two["series"] if s["station"] == "V37"][0]["nights"][-1]
assert abs(v["implied_distance_factor"] - 10 ** (-0.1)) < 1e-6           # 0.5 mag brighter = 0.79 x the distance
# too few nights for a baseline: says so, never fires
short = p.evaluate(p.nights(obs("V37", n0, [0, -0.9])))
assert "baseline needs" in short["series"][0]["status"] and not short["c9_fired"]
assert "C9 PHOTOMETRIC CHECK" in p.format_report(two)

print("PASS: hannibal_photometry_check (parsing, signature, self-calibration, allowance, 3 sigma, 2 nights, 2 stations)")
