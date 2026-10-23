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

Any one of these, from professional data, counts. Each one is checked automatically on every run of the daily brief (C6 to C8 for hypothesis H-A are in 4b):

- **C1 Risk list:** JPL Sentry or ESA's risk list carries Apophis again.
- **C2 Atmosphere:** in JPL's or ESA's numbers, the minimum possible distance of any pass reaches Earth's radius plus 100 km.
- **C3 Agencies disagree:** JPL and ESA disagree on a pass by more than 3 combined sigma, where the uncertainty window is smaller than the distance. Wider windows are expected to disagree and are logged as notes, not concerns.
- **C4 Lisbon:** the impossible-event test off Lisbon returns POSSIBLE.
- **C5 Orbit shift:** a new JPL orbit solution moves the 2029 nominal distance by more than 3 sigma of solution 220 (3 × 1.1 km).

### 4b. Named hypothesis H-A: Apophis is artificial or under control (added 23 Oct 2026, 21:20 UTC)

Reason for adding it: the investigators stated this hypothesis openly, linking 'Oumuamua (2017, "the test") to Apophis's 2029 pass inside the geostationary ring ("the follow-up"). It is recorded here before any data was collected to test it.

Background, recorded so the test is judged fairly:
- Apophis was discovered in 2004, and its 2029 close approach was known well before 'Oumuamua's 2017 passage.
- Its measured non-gravitational push is the transverse (Yarkovsky) term. Solution 220: A2 = −2.9018e−14 ± 1.9e−16 au/d². ESA's independent fit: −2.9001e−14 ± 2.3e−16. They agree to 0.06 sigma. No radial or out-of-plane push is detected (A1 = 5e−13 ± 4.9e−13, consistent with zero; no A3).

If H-A is true, at least one of these should eventually show up:

- **C6 Unexplained push** (automatic, every run): any one of
  - JPL's A2 moves by more than 3 sigma from solution 220,
  - a radial (A1) or out-of-plane (A3) push becomes significant at more than 3 sigma,
  - JPL and ESA disagree on A2 by more than 3 sigma.

  A manoeuvre would also show up under C3 and C5.
- **C7 Radio emission** (manual, 2029 flyby): a narrowband signal that tracks Apophis's sky position and Doppler shift. It must be absent when the antenna points off-source and be confirmed by a second, independent station. Receive-only.
- **C8 Not behaving like a natural body** (manual): a light curve, spin state or colour that contradicts the known ones (tumbling, 30.6 h main period, stony Sq-type), or close-up images from ESA Ramses or NASA OSIRIS-APEX showing something other than a natural rocky or rubble surface.

H-A is refuted if, by the end of the spacecraft missions' first close-up imaging after the 2029 flyby:
- C6 never fired on any orbit solution through the flyby,
- the C7 listening campaign found no confirmed source-tracking signal, and
- the close-up images and photometry show a natural body.

H-A is supported only by a C6, C7 or C8 result that survives the checks in section 7. One unconfirmed observation is not support.

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
