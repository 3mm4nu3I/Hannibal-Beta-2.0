# Daily brief

`build_daily.py` writes one A4 PDF and its JSON per run, named `YYYY-MM-DD_HHMM` (UTC):

1. **Apophis (99942)**: the `[W]` "where it won't be" verdict, orbit solution and Sentry status, every pass to 2200, the 2029 closest point and 3-sigma box, the 3-sigma envelope at each pass, and the impossible-event test for an impact off Lisbon (`[L]`).
1b. **Independent check**: NASA/JPL vs ESA NEOCC (`orbital/hannibal_crosscheck.py`), judged against the pre-registered criteria in `docs/investigation/apophis/PREREGISTRATION.md`. The raw replies are hashed into `docs/investigation/apophis/evidence/<stamp>/`.
2. **Satellite health**: SatNOGS evidence for the seven watch targets: LIVE/SILENT, age of the last good decode, stations, next scheduled pass and DB status.
3. **Debris cascade**: CelesTrak catalog counts and the altitude shells over the linearised Kessler line (`[D]`).

Each run compares itself with the newest earlier JSON in this folder and lists what changed. Exit code 3 means an alert: a new Apophis orbit solution, a Sentry listing, a verdict change, Lisbon no longer IMPOSSIBLE, a satellite going SILENT, JPL unreachable, or any of criteria C1 to C5 (an agency risk listing, a pass reaching the atmosphere, JPL and ESA disagreeing, or the 2029 distance moving more than 3 sigma). A section that can't reach its source says NO DATA and makes no claim.

```
python docs/reports/daily/build_daily.py            # needs requests + reportlab
```

Everything is receive-only and goes through `orbital/hannibal_net`. A scheduled routine runs it three times a day (Brussels 06:40, 11:40 and 20:40) and commits the result here.
