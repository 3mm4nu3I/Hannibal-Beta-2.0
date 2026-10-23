"""Offline tests for the N2YO altitude sanity guard (sane_alt_km + above()/position()).

Regression for the 2026-10-17 bug: N2YO served a satalt of ~2.4e12 km for a freshly
catalogued object (USA 568 / NORAD 66551) from a degenerate element set, and the module
printed it verbatim. The guard must reject non-physical altitudes at ingestion.

Run: python -m pytest test_hannibal_altguard.py   (or: python test_hannibal_altguard.py)
"""
import math

import hannibal_n2yo as n2
from hannibal_net import Result


def test_sane_alt_accepts_real_orbits():
    # LEO, GEO, VELA-near-apogee, and out to lunar distance are all physical.
    for km in (420.0, 1105.0, 35786.0, 163445.0, 384400.0):
        val, suspect = n2.sane_alt_km(km)
        assert val == km and suspect is False, km


def test_sane_alt_rejects_garbage():
    for bad in (2408092187602.0, n2.ALT_MAX_KM + 1.0, -5.0,
                float("nan"), float("inf"), float("-inf"), None, "", "n/a"):
        val, suspect = n2.sane_alt_km(bad)
        assert val is None and suspect is True, bad


def test_ceiling_boundary():
    assert n2.sane_alt_km(n2.ALT_MAX_KM) == (n2.ALT_MAX_KM, False)   # inclusive
    assert n2.sane_alt_km(n2.ALT_MAX_KM + 0.1)[1] is True


def _client_with_payload(payload):
    client = n2.N2YO(key="TESTKEY", net=object())
    client._call = lambda kind, path: Result(data=payload)
    return client


def test_above_rejects_garbage_row_and_keeps_it_last():
    payload = {
        "info": {"satcount": 2},
        "above": [
            {"satid": 111, "satname": "GOOD GEO", "satlat": 5.0, "satlng": 4.0, "satalt": 35786.0},
            {"satid": 66551, "satname": "USA 568", "satlat": 51.6, "satlng": -107.2,
             "satalt": 2408092187602.0},
        ],
    }
    res = _client_with_payload(payload).above(lat=51.22, lon=4.40, alt_km=0.1)
    assert res.ok
    rows = {r["norad"]: r for r in res.data["rows"]}

    bad = rows[66551]
    assert bad["alt_km"] is None and bad["alt_suspect"] is True and bad["el"] is None

    good = rows[111]
    assert good["alt_km"] == 35786.0 and good["alt_suspect"] is False and good["el"] is not None

    # The garbage object is still "above" per N2YO, so it is retained -- just sunk to the bottom.
    assert res.data["rows"][-1]["norad"] == 66551
    assert res.data["count"] == 2 and len(res.data["rows"]) == 2


def test_position_flags_suspect_altitude():
    payload = {
        "info": {"satid": 66551, "satname": "USA 568"},
        "positions": [{"satlatitude": 51.6, "satlongitude": -107.2,
                       "sataltitude": 2408092187602.0, "azimuth": 315.0,
                       "elevation": 27.9, "timestamp": 1792259338}],
    }
    res = _client_with_payload(payload).position(66551, lat=51.22, lon=4.40, alt_km=0.1)
    assert res.ok
    assert res.data["alt_km"] is None and res.data["alt_suspect"] is True
    # Elevation is reported directly by N2YO and is untouched by the altitude guard.
    assert res.data["el"] == 27.9


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok  ", fn.__name__)
    print(f"\n{len(fns)} tests passed")
