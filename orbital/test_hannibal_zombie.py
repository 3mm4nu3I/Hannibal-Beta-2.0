#!/usr/bin/env python3
"""Offline tests for hannibal_zombie (no network). Run: python test_hannibal_zombie.py

The records are trimmed copies of real SatNOGS DB and Network responses fetched on 22 Oct 2026."""
from datetime import datetime, timezone

import hannibal_zombie as z
from hannibal_net import Result

NOW = datetime(2026, 10, 22, 18, 40, tzinfo=timezone.utc)
SINCE = z.window_start(30, NOW)

SATS = [
    {"name": "ERS-15", "norad_cat_id": 2412, "status": "in orbit", "launched": "1966-08-19T00:00:00Z"},
    {"name": "COSMOS 2488", "norad_cat_id": 39483, "status": "in orbit", "launched": "2013-12-25T00:00:00Z"},
    {"name": "SDS-3 F-5", "norad_cat_id": 32378, "status": "in orbit", "launched": None},
    {"name": "USA 184", "norad_cat_id": 29249, "status": "in orbit", "launched": "2006-06-28T00:00:00Z"},
    {"name": "ISS", "norad_cat_id": 25544, "status": "in orbit", "launched": "1998-11-20T00:00:00Z"},
    {"name": "no id", "norad_cat_id": None},
]
TXS = [
    {"description": "carrier wave", "alive": True, "type": "Transmitter", "downlink_low": 136439000, "mode": "CW",
     "norad_cat_id": 2412, "status": "active"},
    {"description": "UHF Unknown", "alive": True, "type": "Transmitter", "downlink_low": 387174810, "mode": "FM",
     "norad_cat_id": 39483, "status": "active"},
    {"description": "UHF Unknown", "alive": True, "type": "Transmitter", "downlink_low": 388687277, "mode": "FM",
     "norad_cat_id": 39483, "status": "active"},
    {"description": "CW Carrier", "alive": False, "type": "Transmitter", "downlink_low": 2242504000, "mode": "CW",
     "norad_cat_id": 32378, "status": "inactive"},
    {"description": "Mode S1", "alive": True, "type": "Transmitter", "downlink_low": 2232520000, "mode": "FM",
     "norad_cat_id": 29249, "status": "active"},
    {"description": "Mode V APRS", "alive": True, "type": "Transceiver", "uplink_low": 145825000,
     "downlink_low": 145825000, "mode": "AFSK", "norad_cat_id": 25544, "status": "active"},
]


def obs(norad, status, end, station="SGP", desc="carrier wave", mode="CW", hz=136439000):
    return {"norad_cat_id": norad, "status": status, "start": end, "end": end, "station_name": station,
            "transmitter_description": desc, "transmitter_mode": mode, "transmitter_downlink_low": hz}


ERS_GOOD = [obs(2412, "good", "2026-09-26T12:40:16Z"), obs(2412, "good", "2026-09-24T09:10:00Z")]
ERS_BAD = [obs(2412, "bad", f"2026-10-1{d}T22:34:39Z", "station-02") for d in range(5)]
COSMOS_GOOD = [obs(39483, "good", f"2026-10-{21 - i:02d}T12:45:54Z", "UT4UYF/P", "UHF Unknown", "FM", 388687277)
               for i in range(9)]

# --- targets ------------------------------------------------------------------------------------------
assert z.parse_ids("2412, 39483 25544;2412 x 0 -5") == [2412, 39483, 25544]
assert z.targets_from_json([{"norad": 2412, "name": "ERS 15"}, {"id": 2412}, 39483]) == [
    {"norad": 2412, "name": "ERS 15"}, {"norad": 39483, "name": ""}]
assert z.targets_from_json({"targets": [{"id": 25544, "name": "ISS (ZARYA)"}]}) == [{"norad": 25544, "name": "ISS (ZARYA)"}]
seed = z.load_targets()
assert len(seed) == 148 and seed[0] == {"norad": 42719, "name": "COSMOS 2518"} and seed[-1]["norad"] == 41121

# --- one object at a time -----------------------------------------------------------------------------
sats, txs = z.index_db(SATS, TXS)
assert set(sats) == {2412, 39483, 32378, 29249, 25544} and len(txs[39483]) == 2

r = z.assess({"norad": 2412, "name": "ERS 15"}, sats[2412], txs[2412], {"good": ERS_GOOD, "bad": ERS_BAD}, SINCE)
assert r["tier"] == z.HEARD and r["good"] == 2 and r["bad"] == 5 and r["launched"] == "1966"
assert r["last_good"] == "2026-09-26 12:40" and "136.439 MHz" in r["heard_on"] and not r["uplink_on_record"]

r = z.assess({"norad": 29249, "name": "USA 184"}, sats[29249], txs[29249], {"good": [], "bad": []}, SINCE)
assert r["tier"] == z.LISTED and r["good"] == 0

r = z.assess({"norad": 32378, "name": "USA 198"}, sats[32378], txs[32378], {"good": [], "bad": []}, SINCE)
assert r["tier"] == z.NO_ACTIVE and r["db_name"] == "SDS-3 F-5" and r["launched"] == ""

r = z.assess({"norad": 836, "name": "OPS 3662 (VELA 3)"}, None, None, None, SINCE)
assert r["tier"] == z.NOT_IN_DB and not r["in_satnogs"]

# a good result older than the window, or for another object, or with another status, never counts
stray = [obs(2412, "good", "2026-08-01T00:00:00Z"), obs(39483, "good", "2026-10-20T00:00:00Z"),
         obs(2412, "bad", "2026-10-20T00:00:00Z")]
r = z.assess({"norad": 2412, "name": ""}, sats[2412], txs[2412], {"good": stray, "bad": []}, SINCE)
assert r["tier"] == z.LISTED and r["good"] == 0 and r["name"] == "ERS-15"

# a full page means "at least 25"
r = z.assess({"norad": 25544, "name": "ISS"}, sats[25544], txs[25544],
             {"good": [obs(25544, "good", "2026-10-22T17:00:00Z")] * z.PAGE, "bad": []}, SINCE)
assert r["good_capped"] and r["uplink_on_record"]

# a network failure is NOT CHECKED, never "not heard"
r = z.assess({"norad": 2412, "name": ""}, sats[2412], txs[2412], {"good": None, "bad": None, "error": "Timeout"}, SINCE)
assert r["tier"] == z.UNCHECKED and r["error"] == "Timeout"

# --- run() through a fake network -------------------------------------------------------------------
class FakeNet:
    def __init__(self, db_ok=True, fail_obs=()):
        self.calls, self.db_ok, self.fail_obs = [], db_ok, set(fail_obs)

    def get_json(self, url, params=None, **kw):
        self.calls.append((url, dict(params or {})))
        if url == z.DB_SATELLITES_URL:
            return Result(SATS) if self.db_ok else Result(None, error="HTTP 503 from db.satnogs.org")
        if url == z.DB_TRANSMITTERS_URL:
            return Result(TXS) if self.db_ok else Result(None, error="HTTP 503 from db.satnogs.org")
        if url == z.NETWORK_OBS_URL:
            n, st = params["norad_cat_id"], params["status"]
            if n in self.fail_obs:
                return Result(None, error="ConnectionError")
            data = {(2412, "good"): ERS_GOOD, (2412, "bad"): ERS_BAD, (39483, "good"): COSMOS_GOOD}
            return Result(data.get((n, st), []))
        return Result(None, error="unexpected url")


TARGETS = [{"norad": 42719, "name": "COSMOS 2518"}, {"norad": 29249, "name": "USA 184"},
           {"norad": 32378, "name": "USA 198"}, {"norad": 39483, "name": "COSMOS 2488"},
           {"norad": 2412, "name": "ERS 15"}, {"norad": 836, "name": "OPS 3662 (VELA 3)"}]

net = FakeNet()
res, err = z.run(TARGETS, net=net, now=NOW)
assert not err
assert res["counts"] == {z.HEARD: 2, z.LISTED: 1, z.NO_ACTIVE: 1, z.UNCHECKED: 0, z.NOT_IN_DB: 2}
assert res["verdict"] == "HEARD in the last 30 days: 2 of 6" and res["heard_with_uplink"] == 0
assert [r["norad"] for r in res["rows"][:2]] == [39483, 2412]          # most recently heard first
obs_calls = [p for u, p in net.calls if u == z.NETWORK_OBS_URL]
assert {p["norad_cat_id"] for p in obs_calls} == {29249, 32378, 39483, 2412}   # never asks about objects with no transmitter
assert all(p["start"] == "2026-09-22T18:00:00Z" for p in obs_calls)          # hour-rounded window, cache-friendly
text = z.format_report(res)
assert "ERS 15" in text and "VELA 3" not in text and "2 more NOT IN SATNOGS" in text and "not of a link" in text
assert "VELA 3" in z.format_report(res, show_all=True)

res, err = z.run(TARGETS, net=FakeNet(fail_obs={2412}), now=NOW)
assert res["unchecked"] == 1 and "at least" in res["verdict"] and res["heard"] == 1

res, err = z.run(TARGETS, net=FakeNet(db_ok=False), now=NOW)
assert res is None and err.startswith("SatNOGS DB unavailable")             # never a silent zero

# paginated DB form (in case SatNOGS ever switches)
class PagedNet(FakeNet):
    def get_json(self, url, params=None, **kw):
        if url == z.DB_SATELLITES_URL:
            return Result({"results": SATS[:3], "next": "page2"})
        if url == "page2":
            return Result({"results": SATS[3:], "next": None})
        return super().get_json(url, params, **kw)


res, err = z.run(TARGETS, net=PagedNet(), now=NOW)
assert not err and res["heard"] == 2

print("PASS: hannibal_zombie (targets, tiers, window and foreign rows, page cap, unchecked, fake net, paging)")
