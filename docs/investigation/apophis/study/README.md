# Apophis study pipeline

```
python docs/investigation/apophis/collect.py                        # one evidence snapshot (hourly task runs this)
python docs/investigation/apophis/study/build_study.py              # aggregate all snapshots -> out/
python docs/investigation/apophis/study/build_study.py --until 2026-10-26T11:00Z   # fixed cutoff for a citable build
python docs/investigation/apophis/study/test_build_study.py         # offline tests
```

`out/` contains:
- `apophis_snapshots.csv`: one row per snapshot, fixed columns
- `summary.json`: statistics and criteria tallies
- three figures
- `Apophis_Study_Report.pdf`: abstract, pre-registration, methods, results, threats to validity, conclusion, reproducibility, appendix
- `STUDY_MANIFEST.json`: SHA-256 of every input folder and output file

How it guards against bias:
- **Integrity:** snapshots that fail their hash check are listed but excluded from the statistics.
- **No editing of values:** nothing is smoothed or filled in.
- **Fixed conclusions:** the conclusion is picked from wording written in advance (`CONCLUSION_TEXT`), based only on the pre-registered criteria.
- **Honest sample size:** the report states that hourly snapshots of one orbit solution are not independent measurements.

Needs `requests`, `reportlab` and `matplotlib`.
