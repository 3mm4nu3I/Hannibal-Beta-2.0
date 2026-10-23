# Mission report and debrief, 22–23 October 2026

`Project_Hannibal_Mission_Report_2026-10-23.pdf` (9 pages): the zombie-satellite check over Antwerp (2 of 148 heard,
0 with an uplink), ERS 15's reception history, the Apophis exclusion, the moonbounce planner, a Voyager 1 link
budget calibrated against JPL's design tables, the receive-only rules in Belgium, and next steps.

Everything in it is reproducible from this folder:

| File | What |
|---|---|
| `calcs.json` | every calculated figure: Wilson intervals, EME budgets by band, Voyager 1 link, Apophis (JPL, 23 Oct 16:05 UTC) |
| `zombie_23oct.json` | `hannibal_zombie.py --json` output for the 148, run 23 Oct 2026 |
| `ers15_good_all.json` | every vetted good SatNOGS observation of ERS 15 (NORAD 2412) to 23 Oct 2026: id, start time, station |
| `charts.py` | the three charts (matplotlib, DejaVu Sans) |
| `build_report.py` | the PDF (ReportLab, A4) |

Rebuild: `python charts.py && python build_report.py` (needs `matplotlib`, `reportlab` and the DejaVu fonts).
Fresh data: `python ../../../orbital/hannibal_zombie.py --json zombie_23oct.json`, `python ../../../orbital/hannibal_neo.py 99942 --json apophis.json`.
