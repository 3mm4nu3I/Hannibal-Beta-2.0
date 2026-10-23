# Apophis (99942): pre-registration

An independent amateur check, by Project Hannibal, of whether there is real reason for concern about 99942 Apophis. This file is written **before** the results it judges. Git records when each line was committed, so nobody (us included) can move the goalposts afterwards.

Registered: 23 Oct 2026. Investigators: Project Hannibal (Bram).

## 1. Question

Is there evidence, in public data from independent professional sources, that Apophis poses a real risk of hitting Earth? This includes a specific impact in the Atlantic off Lisbon (38.70N 9.60W) during the 13 April 2029 flyby.

## 2. Sealed hypothesis (private for now)

We have a specific reason for concern that we can't state yet. It is sealed with `seal.py`: the text stays private and only its SHA-256 hash is committed here. When we reveal the text, anyone can check that it existed, unchanged, on the date of this commit.

```
sealed hypothesis SHA-256:  <paste the output of: python seal.py my_hypothesis.txt>
sealed on (UTC):            <date and time>
```

The sealed statement should say what we expect the data to show, and by when. That is what makes it testable.

## 3. Baseline (23 Oct 2026, before any further checks)

| | NASA/JPL | ESA NEOCC |
|---|---|---|
| Orbit | solution 220, U=0, 7,370 observations used, last 2022-04-09 | own fit, 9,577 observations on file (50 radar, 1,364 from space), last 2022-04-09 |
| Risk list | Sentry: removed 2021-02-21 | not on the risk list |
| 2029 pass | 38,011 km from Earth's centre, nearest 3-sigma edge 38,008 km, at 21:44:50 UTC | 38,014 km, minimum possible 38,010 km, at 21:45:03 UTC |
| Agreement | | 2.3 km apart = 1.4 combined sigma: **AGREE** |
| Off Lisbon | closest 32,495 km at 21:39 UTC, nearest edge 32,492 km: **IMPOSSIBLE** | (same physics: the ESA distances agree with JPL) |

Raw replies, hashes and the analysis for each run are kept in `evidence/<UTC stamp>/` (see `SHA256SUMS` and `manifest.json` there).

## 4. What counts as real reason for concern (fixed now, in advance)

Any one of these, from professional data, counts. Each one is checked automatically on every run of the daily brief:

- **C1 Risk list:** JPL Sentry or ESA's risk list carries Apophis again.
- **C2 Atmosphere:** in JPL's or ESA's numbers, the minimum possible distance of any pass reaches Earth's radius plus 100 km.
- **C3 Agencies disagree:** JPL and ESA disagree on a pass by more than 3 combined sigma, where the uncertainty window is smaller than the distance. Wider windows are expected to disagree and are logged as notes, not concerns.
- **C4 Lisbon:** the impossible-event test off Lisbon returns POSSIBLE.
- **C5 Orbit shift:** a new JPL orbit solution moves the 2029 nominal distance by more than 3 sigma of solution 220 (3 × 1.1 km).

## 5. What would refute the concern

If none of C1 to C5 is triggered by new orbit solutions that use observations from Apophis's next observing window (expected from about 2027), professional data gives no reason for concern. The sealed hypothesis may make its own prediction; it is judged against what it said.

## 6. Signals that are not concerns on their own

- New observations appearing (ESA's file gets entries after 2022-04-09). This is expected and is a reason to watch for a new orbit solution.
- A source that cannot be reached. This is recorded as NO DATA and never counted as either an all-clear or a concern.
- Disagreement on passes after about 2100, where both agencies' uncertainty is millions of km.

## 7. What we do if a concern is triggered

1. Re-run and save the evidence folder for that run.
2. Check by hand that the trigger is real: read the raw files and recompute.
3. If it holds up, report it with the evidence to ESA's Planetary Defence Office and the International Asteroid Warning Network, the bodies that can test it with telescopes.

## 8. Changes to this file

Changes after registration are new commits with a reason. Nothing above is edited in place once the sealed hash is filled in.
