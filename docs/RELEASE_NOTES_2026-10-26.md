# Project Hannibal — Orbital Directorate · release 2026-10-26 (beta 2.0)

```
                               /\
                               ||
                              /||\
                              /  \
                             /    \
                             |    |
                 |X|         |----|          |X|
                 |-|         |    |          |-|
                 |X|         |CCCP|          |X|
                 |-|      /| |    | |\       |-|
                 |X|     / |/======\| \      |X|
                 |-|    /  ||      ||  \     |-|
                 |X|    |  ||      ||  |     |X|
                 |-|    |  ||      ||  |     |-|
                 |X|    | o||    ..||  |:    |X|
                 |-|    |__||.     ||__|     |-|
                 |X|    /__\/__||__\/__\     |X|
#===#===#===#===#===#===#'|'#=`V|W.=#'|'#===#===#===#===#===#===
                          W    'W.    W
                                v

    П О Е Х А Л И !     P O Y E K H A L I !
    Hannibal ad portas  //  the Orbital Directorate, receive-only
```

A receive-only, open-data intelligence terminal in Python: orbital awareness, planetary defence, satellite reception and market conditions, with every reading carrying its source, sample size and uncertainty. It never transmits and never fills a gap with invented data.

## What is in this release
- The merged Orbital Directorate (`orbital/`): SatNOGS link health with 95% Wilson intervals, Space-Track, N2YO, NASA/JPL, CelesTrak, the BlueGlobe dashboard, and one hardened network layer (secret masking, disk cache, rate limits, retries).
- `[W]` Where it won't be: Earth-impact exclusion for any asteroid or comet from JPL close-approach data, deferring to JPL Sentry (Apophis 2029 reproduced at 38,011 km by the project's own output).
- `[D]` Debris cascade watch with sensitivity, `[Z]` zombie-satellite check (2 of 148 heard on 22 Oct), `[E]` moonbounce link budgets, `[M]` FRED macro board and the developer-only market brain behind a PBKDF2 gate.
- Whitepaper README, per-release changelog, roadmap, the 22–23 Oct mission report (PDF with its data and scripts), and the Soviet-styled launchers.

## Verified on 2026-10-26
All 8 offline test files pass: neo, zombie, kessler, eme (14), altguard (5), subsea/spatial, volcano anomaly, evidence-confidence fixtures.
**Not re-verified in this release:** live endpoints (last exercised 22–23 Oct), the BlueGlobe dashboard against the real `blueglobe.js`, the ADS-B feeder, and any forecasting accuracy (none is claimed).

## Known limitations
Two terminals still exist; V10/V11 need a `core/` folder that is not in this repository; two `.bat` hashes in `MANIFEST_SHA256.json` match LF line endings only. See README section 8 and `ROADMAP.md`.

## Assets
`SHA256SUMS.txt` lists the checksum of each attached file. The source archive is `git archive` of the tagged commit.

Author: Bram Noffels, Antwerp · https://github.com/3mm4nu3I
