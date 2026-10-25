#!/usr/bin/env python3
"""Offline tests for the study pipeline: integrity check, criteria tallies, fixed conclusion wording.
Run: python docs/investigation/apophis/study/test_build_study.py"""
import hashlib
import tempfile
from pathlib import Path

import build_study as b

# integrity: a changed byte is caught, a missing file is caught
with tempfile.TemporaryDirectory() as tmp:
    d = Path(tmp)
    (d / "a.json").write_text('{"x": 1}')
    (d / "SHA256SUMS").write_text(f"{hashlib.sha256(b'{\"x\": 1}').hexdigest()}  a.json\n")
    assert b.verify(d) == "OK"
    (d / "a.json").write_text('{"x": 2}')
    assert b.verify(d).startswith("FAILED")
    (d / "a.json").unlink()
    assert b.verify(d).startswith("FAILED")


def row(stamp, integrity="OK", fired=None, unchecked=(), km=38011.46):
    r = {"stamp": stamp, "taken_utc": f"2026-10-24T{stamp[-4:-2]}:00:00Z", "integrity": integrity, "jpl_orbit_id": "220",
         "jpl_2029_km": km, "esa_2029_km": km + 2.3, "diff_2029_km": 2.3, "nsigma_2029": 1.4, "sources_failed": ""}
    for i in range(1, 7):
        k = f"C{i}"
        r[k] = None if k in unchecked else (k == fired)
    return r


# nothing fired -> the fixed null wording, verbatim
s = b.summarise([row("2026-10-24_0100"), row("2026-10-24_0200")])
assert s["outcome"] == "none" and s["conclusion"] == b.CONCLUSION_TEXT["none"]
assert s["bet_status"] == {"Bram": False, "Claude": True}

# one criterion fired -> the fixed 'fired' wording naming it, and the snapshot listed
s = b.summarise([row("2026-10-24_0100"), row("2026-10-24_0200", fired="C5", km=38020.0)])
assert s["outcome"] == "fired" and "C5" in s["conclusion"] and s["criteria"]["C5"]["fired_in"] == ["2026-10-24_0200"]

# a tampered snapshot is excluded from statistics even if it would 'fire'
s = b.summarise([row("2026-10-24_0100"), row("2026-10-24_0200", integrity="FAILED: x", fired="C1")])
assert s["outcome"] == "none" and s["snapshots_verified"] == 1 and len(s["integrity_failures"]) == 1

# a criterion never checkable is reported, not treated as passed
s = b.summarise([row("2026-10-24_0100", unchecked=("C4",))])
assert "C4 could not be checked" in s["conclusion"]

# the bet flips when the data does
assert b.summarise([row("2026-10-24_0100", km=28_500)])["bet_status"] == {"Bram": True, "Claude": False}

print("PASS: study pipeline (integrity, criteria tallies, fixed conclusions, tamper exclusion, bet)")
