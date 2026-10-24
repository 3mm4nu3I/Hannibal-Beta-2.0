"""Offline tests for the baseline-anomaly block in VolcanoLlamaNapalm.py.
The terminal itself needs yfinance, cryptography and a login, so this runs
only the block between the BEGIN/END BASELINE ANOMALY markers."""
import json
import time
import unittest
from collections import deque
from pathlib import Path

import numpy as np

SRC = (Path(__file__).resolve().parent / "VolcanoLlamaNapalm.py").read_text(encoding="utf-8")
BLOCK = SRC.split("# --- BEGIN BASELINE ANOMALY")[1].split("# --- END BASELINE ANOMALY ---")[0]
NS = {"time": time, "json": json, "deque": deque, "np": np, "SCRIPT_DIR": Path(".")}
exec(compile(BLOCK.split("\n", 1)[1], "anomaly_block", "exec"), NS)
BaselineAnomaly, fresh_count, bounded_multiplier = NS["BaselineAnomaly"], NS["fresh_count"], NS["bounded_multiplier"]
STEP = NS["ANOMALY_SAMPLE_SECONDS"]


def warm(a, values, t0=0.0):
    t = t0
    for v in values:
        assert a.maybe_sample({"K": v, "I": v, "L": v}, t)
        t += STEP
    return t


class AnomalyTest(unittest.TestCase):
    def test_quiet_day_stays_near_zero(self):
        a = BaselineAnomaly()
        rng = np.random.default_rng(1)
        warm(a, rng.poisson(12, 200))
        scores = [a.score("K", int(c)) for c in rng.poisson(12, 200)]
        self.assertLess(np.mean(scores), 0.15)  # Poisson noise alone gives ~0.11
        self.assertLess(np.percentile(scores, 95), 0.5)

    def test_busy_buffer_is_not_saturation(self):
        # the old rule: any item -> 1.0. A constantly full buffer must now score ~0.
        a = BaselineAnomaly()
        warm(a, [40] * 100)
        self.assertEqual(a.score("K", 40), 0.0)

    def test_spike_rises_and_caps(self):
        a = BaselineAnomaly()
        warm(a, [10, 11, 9, 12, 10, 8, 11, 10] * 10)
        self.assertGreater(a.score("K", 18), 0.5)
        self.assertEqual(a.score("K", 500), 1.0)
        self.assertEqual(a.score("K", 2), 0.0)

    def test_warmup_scores_zero(self):
        a = BaselineAnomaly()
        warm(a, [5] * (NS["ANOMALY_MIN_SAMPLES"] - 1))
        self.assertTrue(a.warming())
        self.assertEqual(a.score("K", 999), 0.0)

    def test_sampling_interval(self):
        a = BaselineAnomaly()
        self.assertTrue(a.maybe_sample({"K": 1, "I": 1, "L": 1}, 100.0))
        self.assertFalse(a.maybe_sample({"K": 1, "I": 1, "L": 1}, 100.0 + STEP - 1))
        self.assertTrue(a.maybe_sample({"K": 1, "I": 1, "L": 1}, 100.0 + STEP))
        self.assertEqual(len(a.hist["K"]), 2)

    def test_fresh_count(self):
        now = 1_000_000.0
        snap = [(now - 60, {}), (now - 29 * 60, {}), (now - 31 * 60, {}), (now - 3000, {})]
        self.assertEqual(fresh_count(snap, now=now), 2)

    def test_persistence_roundtrip(self):
        a = BaselineAnomaly()
        warm(a, range(30))
        b = BaselineAnomaly()
        b.load_json(a.to_json())
        self.assertEqual(list(b.hist["L"]), list(range(30)))
        b.load_json("not json")  # must not raise

    def test_bounded_multiplier(self):
        self.assertEqual(bounded_multiplier(1.0), 1.0)
        self.assertAlmostEqual(bounded_multiplier(1.3), 1.3)
        self.assertEqual(bounded_multiplier(16.0), 1.5)


if __name__ == "__main__":
    unittest.main()
