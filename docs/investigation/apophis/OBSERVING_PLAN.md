# Apophis observing plan: two methods, two windows (remote telescopes)

Made with `orbital/hannibal_obsplan.py` from JPL Horizons on 23 Oct 2026; the full numbers are in `observing_plan.json`. Everything here is receive-only.

## The two methods

1. **Astrometry: where it is (decisive for C3, C5 and C6).** Take at least 3 positions per night (a tracklet) over 30 to 60 minutes at SNR ≥ 10, measured against Gaia DR3. Timestamp each frame at mid-exposure from a synchronised clock: Apophis moves 1 to 4" a minute, so a 1-second clock error costs up to 0.07". Check every tracklet with `orbital/hannibal_astrometry_check.py`, which compares it with JPL's prediction (O−C). Then submit it to the Minor Planet Center in ADES format, under the telescope's observatory code. That's how it enters JPL's and ESA's orbit fits, and the daily cross-check would then see any effect.
2. **Photometry: how bright it is (C8 and C9).** Use SNR ≥ 50 per point and long runs. Apophis tumbles, with a main period of about 30.6 h, so one night covers only part of a cycle; nights from sites on different continents fill the gaps. Use the same filter every time (r or V), and add colour (g−r) on the brightest nights.

## The two windows

- **Window 1:** 20 Dec 2026 to 5 Aug 2028, magnitude about 19 to 21.5. Use 1 m telescopes; the faintest months, spring 2027, need about 10 to 16 minutes per astrometric point.
- **Window 2:** 7 Oct 2028 to closest approach, brightening from magnitude 20 to 7.5. From January 2029 even 0.4 m telescopes are enough.

Apophis approaches from the night side, so there is no blind spot before closest approach. The one gap is August to early October 2028 (too close to the Sun).

## Best site per month

The planning model is conservative: 1 m, 60 s gives SNR 10 at V = 20.0, in 2" seeing. "sub s" is the longest single exposure before the trail exceeds the seeing; stack sub-exposures on the asteroid's motion.

```
  month    best site                          ap m nights     V  "/min sub s astro min photo min  best night
  2026-12  V37 McDonald, Texas (LCO)          1.00      2  20.7   3.26    37         4        97  2026-12-27
  2027-01  V37 McDonald, Texas (LCO)          1.00     20  20.8   3.13    38         5       114  2027-01-18
  2027-02  V37 McDonald, Texas (LCO)          1.00     23  21.0   2.81    43         6       151  2027-02-01
  2027-03  V37 McDonald, Texas (LCO)          1.00     27  21.2   2.44    49         9       224  2027-03-01
  2027-04  V37 McDonald, Texas (LCO)          1.00     26  21.4   2.18    55        13      >240  2027-04-01
  2027-05  V37 McDonald, Texas (LCO)          1.00     27  21.5   2.06    58        16      >240  2027-05-01
  2027-06  W85 Cerro Tololo, Chile (LCO)      1.00     26  21.5   2.05    59        14      >240  2027-06-30
  2027-07  K91 Sutherland, South Africa (LCO) 1.00     22  21.3   2.15    56        10      >240  2027-07-31
  2027-08  W85 Cerro Tololo, Chile (LCO)      1.00     12  20.9   2.38    51         5       133  2027-08-31
  2027-09  Q63 Siding Spring, Australia (LCO) 1.00     22  20.7   2.53    47         4        87  2027-09-30
  2027-10  K91 Sutherland, South Africa (LCO) 1.00     18  20.5   2.72    44         3        66  2027-10-30
  2027-11  Q63 Siding Spring, Australia (LCO) 1.00     21  20.3   3.24    37         2        41  2027-11-30
  2027-12  V37 McDonald, Texas (LCO)          1.00     26  19.5   4.03    30        <1         9  2027-12-28
  2028-01  V37 McDonald, Texas (LCO)          1.00     26  19.1   3.31    36        <1         5  2028-01-20
  2028-02  V37 McDonald, Texas (LCO)          1.00     25  19.6   2.33    52        <1        11  2028-02-05
  2028-03  V37 McDonald, Texas (LCO)          1.00     24  20.1   1.91    63         1        29  2028-03-06
  2028-04  V37 McDonald, Texas (LCO)          1.00     24  20.4   1.78    67         2        55  2028-04-04
  2028-05  W85 Cerro Tololo, Chile (LCO)      1.00     25  20.6   1.75    69         3        73  2028-05-03
  2028-06  W85 Cerro Tololo, Chile (LCO)      1.00     26  20.6   1.72    70         3        69  2028-06-21
  2028-07  W85 Cerro Tololo, Chile (LCO)      1.00     22  20.5   1.51    80         2        60  2028-07-11
  2028-08  Q63 Siding Spring, Australia (LCO) 1.00      3  20.7   0.85   142         4        90  2028-08-01
  2028-10  V37 McDonald, Texas (LCO)          1.00     22  20.1   0.85   141         1        28  2028-10-31
  2028-11  K91 Sutherland, South Africa (LCO) 1.00     12  19.8   1.38    87        <1        16  2028-11-30
  2028-12  V37 McDonald, Texas (LCO)          1.00     27  19.5   1.35    89        <1        10  2028-12-31
  2029-01  W85 Cerro Tololo, Chile (LCO)      1.00     27  18.8   1.17   103        <1         3  2029-01-31
  2029-02  W85 Cerro Tololo, Chile (LCO)      1.00     24  17.6   0.81   147        <1        <1  2029-02-28
  2029-03  K91 Sutherland, South Africa (LCO) 1.00     25  15.5   0.39   300        <1        <1  2029-03-29
  2029-04  W85 Cerro Tololo, Chile (LCO)      1.00     10  11.8   1.83    66        <1        <1  2029-04-11
```

LCO = Las Cumbres Observatory; iTelescope = rented remote telescopes. Check each network's own exposure calculator before booking.

## Final days and C7 radio listening (12 to 14 Apr 2029)

The sky motion grows from about 2"/min to tens of "/min on 12 to 13 April, so single exposures must drop to seconds. Use the telescope's non-sidereal tracking on JPL's ephemeris if it has it. Closest approach is at 21:45 UTC on 13 April, over the mid-Atlantic; Europe and Africa have it high in a dark sky.

For C7 (radio, hypothesis H-A):
- Listen only. Point at Apophis's predicted position from a topocentric ephemeris (`hannibal_neo_where.py --target LAT LON NAME` gives the track).
- Record the line-of-sight speed. The Doppler shift is −f × (range rate) / c: up to about ±7 km/s, so ±33 kHz at 1420 MHz, changing fast near closest approach.
- Alternate on-source and off-source pointings. A real signal must follow Apophis's position and Doppler and be absent off-source.
- A second station must confirm it before it counts (PREREGISTRATION section 7).

## Workflow per observing night

1. Book the site and night from the table, ideally on the "best night".
2. Take frames, plate-solve them against Gaia DR3, and measure positions (Astrometrica, Tycho Tracker or similar) and magnitudes.
3. Run `python orbital/hannibal_astrometry_check.py night.csv` (columns: utc, ra_deg, dec_deg, station, sigma_arcsec).
4. Run `python orbital/hannibal_photometry_check.py night_phot.csv` (columns: utc, mag, mag_err, station, band). This is pre-registered criterion C9: brighter than predicted, and so possibly closer, judged against the same station's own first nights.
5. If the result is consistent: submit to the MPC and archive the CSV and report under `evidence/observations/`. If a tracklet is flagged: check the clock, catalogue and mid-exposure times, re-observe, and get a second station. Only then does it count toward C3, C5 or C6.
