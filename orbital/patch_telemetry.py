#!/usr/bin/env python3
"""
patch_telemetry.py — evidence-gated link health for the Hannibal orbital module.

Dry run by default. Nothing is written until you pass --apply.

    python patch_telemetry.py              # show what would change
    python patch_telemetry.py --apply      # write changes (.bak backups first)
    python patch_telemetry.py --revert     # restore every .bak
    python patch_telemetry.py --selftest   # run the classifier on the 2026-10 scan numbers

Touches three files (whichever are in --dir):
    run_telemetry.py          the maths (all of the behaviour change is here)
    hannibal_orbital.py       colours for the new labels, red TLE epoch when stale
    blueglobe_dashboard.html  same colours on the web dashboard, STALE tag in the HUD

Compatible with the 2026-10-11 Earth-export patch (hannibal_sat): that one adds
a block after MENU; these anchors are elsewhere in the file. Either order works.

WHAT CHANGES AND WHY
1. Packet health = good / (good + bad). SatNOGS "failed" means the ground
   station broke (no audio / waterfall uploaded); it said nothing about the
   satellite, so it no longer counts against it. Reported as "Station Failures".
2. Verdicts need evidence. Under 8 vetted observations -> LOW SAMPLE (the % is
   still shown). ONLINE needs >= 75% AND a 95% Wilson lower bound >= 50%;
   OFFLINE needs < 25% AND an upper bound < 50%; everything else INTERMITTENT.
   Before, one observation could produce OFFLINE and four could produce 100%.
3. Packet Health shows the counts and the 95% range: "78% 64/82 [68-86]".
4. TLE age. Each row gets "TLE Age Days" and "TLE Stale" (> 14 days). Stale
   epochs show red in the terminal and get "(STALE)" in the dashboard HUD.
5. Page cap. A satellite whose observations ran past MAX_PAGES (6 x 25) is
   flagged "Truncated": its health came from a partial window.
6. Only good+bad == 0 with failures present -> STATION FAULT (was OFFLINE-ish
   or NO PASSES depending on path).
"""

from __future__ import annotations

import argparse
import ast
import shutil
import sys
from pathlib import Path

# =============================================================== run_telemetry
RT_IMPORT_OLD = "import json\nimport os\n"
RT_IMPORT_NEW = "import json\nimport math\nimport os\n"

RT_CONST_OLD = "HTTP_TIMEOUT = 15\n"
RT_CONST_NEW = '''HTTP_TIMEOUT = 15

# Link-health evidence gate (patch_telemetry 2026-10-11). See classify().
MIN_SAMPLE = 8          # vetted observations needed before a verdict is issued
ONLINE_PCT = 0.75       # point estimate needed for ONLINE ...
OFFLINE_PCT = 0.25      # ... and below this for OFFLINE
CONFIDENT = 0.50        # the 95% interval must sit on the right side of 50%
WILSON_Z = 1.96         # 95% two-sided
STALE_TLE_DAYS = 14     # older element sets are flagged; SGP4 error grows with age
_TRUNCATED = set()      # NORAD ids whose last fetch hit MAX_PAGES
'''

RT_FETCH_OLD = '''    url, observations = SATNOGS_URL, []
    try:
        for _ in range(MAX_PAGES):
            res = session.get(url, params=params, headers=HEADERS, timeout=HTTP_TIMEOUT)
            res.raise_for_status()
            page = res.json()
            if not isinstance(page, list):
                return [], "unexpected SatNOGS response shape"
            observations.extend(page)
            nxt = res.links.get("next", {}).get("url")
            if not nxt:
                break
            url, params = nxt, None  # the next-link already carries the query string
        return observations, None'''

RT_FETCH_NEW = '''    url, observations = SATNOGS_URL, []
    _TRUNCATED.discard(norad_id)
    try:
        for _ in range(MAX_PAGES):
            res = session.get(url, params=params, headers=HEADERS, timeout=HTTP_TIMEOUT)
            res.raise_for_status()
            page = res.json()
            if not isinstance(page, list):
                return [], "unexpected SatNOGS response shape"
            observations.extend(page)
            nxt = res.links.get("next", {}).get("url")
            if not nxt:
                break
            url, params = nxt, None  # the next-link already carries the query string
        else:
            # Loop ran out with a next-link still pending: the window is partial.
            _TRUNCATED.add(norad_id)
        return observations, None'''

RT_CLASSIFY_OLD = '''def summarize(observations):
    """SatNOGS `status` is lowercase: good / bad / failed / unknown / future.

    Only completed, vetted observations (good, bad, failed) count toward packet
    health. 'future' = scheduled, 'unknown' = awaiting vetting.
    """
    states = [str(o.get("status", "")).lower() for o in observations]
    good = states.count("good")
    done = good + states.count("bad") + states.count("failed")
    unvetted = states.count("unknown")
    return good, done, unvetted


def classify(good, done, unvetted):
    if done == 0:
        return "UNVETTED" if unvetted else "NO PASSES"
    pct = good / done * 100
    if pct >= 75:
        return "ONLINE"
    if pct >= 25:
        return "INTERMITTENT"
    return "OFFLINE"'''

RT_CLASSIFY_NEW = '''def wilson(k, n, z=WILSON_Z):
    """95% Wilson score interval for k successes in n trials -> (low, high).

    Used instead of the plain +/- interval because it stays inside [0, 1] and
    behaves at 0/n and n/n, which is exactly where small satellite samples sit.
    """
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    d = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def summarize(observations):
    """SatNOGS `status` is lowercase: good / bad / failed / unknown / future.

    good   = signal decoded            -> counts for the satellite
    bad    = listened, nothing heard   -> counts against the satellite
    failed = the STATION broke (no audio/waterfall uploaded) -> says nothing
             about the satellite, reported separately as Station Failures
    unknown = awaiting vetting, future = scheduled; neither is counted.
    Returns (good, bad, failed, unvetted).
    """
    states = [str(o.get("status", "")).lower() for o in observations]
    return (states.count("good"), states.count("bad"),
            states.count("failed"), states.count("unknown"))


def classify(good, bad, failed=0, unvetted=0):
    """Evidence-gated verdict. Thin samples get LOW SAMPLE, not a verdict.

    ONLINE        p >= 75%  and 95% lower bound >= 50%
    OFFLINE       p <  25%  and 95% upper bound <  50%
    INTERMITTENT  anything in between, or a confident-looking % the interval can't back
    LOW SAMPLE    fewer than MIN_SAMPLE vetted observations
    """
    n = good + bad
    if n == 0:
        if unvetted:
            return "UNVETTED"
        return "STATION FAULT" if failed else "NO PASSES"
    if n < MIN_SAMPLE:
        return "LOW SAMPLE"
    p = good / n
    low, high = wilson(good, n)
    if p >= ONLINE_PCT and low >= CONFIDENT:
        return "ONLINE"
    if p < OFFLINE_PCT and high < CONFIDENT:
        return "OFFLINE"
    return "INTERMITTENT"


def health_text(good, bad):
    """'78% 64/82 [68-86]' -> share, counts, 95% range. Whole percent so it fits the 20-wide column."""
    n = good + bad
    if n == 0:
        return "N/A (0 obs)"
    low, high = wilson(good, n)
    return f"{good / n * 100:.0f}% {good}/{n} [{low * 100:.0f}-{high * 100:.0f}]"


def tle_age_days(raw, now=None):
    """Days since a Space-Track EPOCH string ('2026-10-03T11:57:00.000000'); None if unparseable."""
    if not raw:
        return None
    try:
        epoch = datetime.fromisoformat(str(raw).split(".")[0].replace(" ", "T"))
    except ValueError:
        return None
    if epoch.tzinfo is None:
        epoch = epoch.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return (now - epoch).total_seconds() / 86400.0'''

RT_SCAN_OLD = '''            observations, err = fetch_satnogs(session, target["id"], hours)
            good, done, unvetted = summarize(observations)
            if err:
                errors += 1
                status, health = "LINK ERROR", "N/A (fetch failed)"
            else:
                status = classify(good, done, unvetted)
                health = f"{good / done * 100:.1f}% ({done} rx)" if done else "N/A (0 rx)"
            if epochs.get(target["id"]):
                epoch = format_epoch(epochs[target["id"]])
            else:
                epoch = "N/A (No Auth)" if st_state == "no credentials" else "N/A"
            row = {"NORAD ID": target["id"], "Target Name": target["name"], "TLE Epoch": epoch,
                   "Status": status, "Packet Health": health}'''

RT_SCAN_NEW = '''            observations, err = fetch_satnogs(session, target["id"], hours)
            good, bad, failed, unvetted = summarize(observations)
            if err:
                errors += 1
                status, health = "LINK ERROR", "N/A (fetch failed)"
            else:
                status = classify(good, bad, failed, unvetted)
                health = health_text(good, bad)
            raw_epoch = epochs.get(target["id"])
            if raw_epoch:
                epoch = format_epoch(raw_epoch)
            else:
                epoch = "N/A (No Auth)" if st_state == "no credentials" else "N/A"
            age = tle_age_days(raw_epoch)
            row = {"NORAD ID": target["id"], "Target Name": target["name"], "TLE Epoch": epoch,
                   "Status": status, "Packet Health": health,
                   "Station Failures": failed,
                   "TLE Age Days": round(age, 1) if age is not None else None,
                   "TLE Stale": bool(age is not None and age > STALE_TLE_DAYS),
                   "Truncated": target["id"] in _TRUNCATED}'''

# ============================================================ hannibal_orbital
OR_FLEET_OLD = '''    colors = {"ONLINE": art.GREEN, "INTERMITTENT": art.GOLD, "OFFLINE": art.RED, "LINK ERROR": art.RED}
    body = [[r.get("NORAD ID", ""), r.get("Target Name", ""), r.get("TLE Epoch", ""), r.get("Status", ""),
             r.get("Packet Health", "")] for r in rows]
    lines = _table(["NORAD", "TARGET", "TLE EPOCH", "SIGNAL", "PACKET HEALTH"], body, [7, 26, 19, 13, 20], color=color)
    if color:  # colour only the SIGNAL cell
        for i, r in enumerate(rows):
            code = colors.get(r.get("Status", ""))
            if code:
                cells = lines[2 + i].split(" | ")
                cells[3] = _c(cells[3], code)
                lines[2 + i] = " | ".join(cells)
    return lines'''

OR_FLEET_NEW = '''    colors = {"ONLINE": art.GREEN, "INTERMITTENT": art.GOLD, "OFFLINE": art.RED, "LINK ERROR": art.RED,
              "LOW SAMPLE": art.GRAY, "STATION FAULT": art.GRAY, "UNVETTED": art.GRAY, "NO PASSES": art.GRAY}
    body = [[r.get("NORAD ID", ""), r.get("Target Name", ""), r.get("TLE Epoch", ""), r.get("Status", ""),
             r.get("Packet Health", "")] for r in rows]
    lines = _table(["NORAD", "TARGET", "TLE EPOCH", "SIGNAL", "PACKET HEALTH"], body, [7, 26, 19, 13, 20], color=color)
    if color:  # colour the SIGNAL cell; a stale TLE epoch goes red
        for i, r in enumerate(rows):
            code = colors.get(r.get("Status", ""))
            stale = r.get("TLE Stale")
            if code or stale:
                cells = lines[2 + i].split(" | ")
                if code:
                    cells[3] = _c(cells[3], code)
                if stale:
                    cells[2] = _c(cells[2], art.RED)
                lines[2 + i] = " | ".join(cells)
    return lines'''

OR_SCREEN_OLD = '''    colors = {"ONLINE": art.GREEN, "INTERMITTENT": art.GOLD, "OFFLINE": R, "LINK ERROR": R}
    for r in rows:
        color = colors.get(r.get("Status", ""), G)
        print(f" {str(r.get('NORAD ID', '')):<7} | {str(r.get('Target Name', ''))[:26]:<26} | "
              f"{str(r.get('TLE Epoch', ''))[:19]:<19} | {color}{str(r.get('Status', '')):<13}{RS} | "
              f"{str(r.get('Packet Health', ''))}")'''

OR_SCREEN_NEW = '''    colors = {"ONLINE": art.GREEN, "INTERMITTENT": art.GOLD, "OFFLINE": R, "LINK ERROR": R}
    for r in rows:
        color = colors.get(r.get("Status", ""), G)
        ep_color = R if r.get("TLE Stale") else ""
        print(f" {str(r.get('NORAD ID', '')):<7} | {str(r.get('Target Name', ''))[:26]:<26} | "
              f"{ep_color}{str(r.get('TLE Epoch', ''))[:19]:<19}{RS if ep_color else ''} | "
              f"{color}{str(r.get('Status', '')):<13}{RS} | "
              f"{str(r.get('Packet Health', ''))}")'''

OR_FOOT_OLD = '''    print(f" {G}Targets are edited in norad_targets.json; packet health = good / vetted SatNOGS observations (24h).{RS}")'''

OR_FOOT_NEW = '''    print(f" {G}Targets are edited in norad_targets.json; packet health = good / (good + bad) SatNOGS observations (24h), "
          f"[95% range]. LOW SAMPLE = under 8 observations; red epoch = TLE older than 14 days.{RS}")'''

# ======================================================== blueglobe_dashboard
DB_COLORS_OLD = """        const STATUS_COLORS = { 'ONLINE': '#00ff00', 'INTERMITTENT': '#ffd700', 'OFFLINE': '#ff4040',
                                'NO PASSES': '#999999', 'UNVETTED': '#999999', 'LINK ERROR': '#ff4040' };"""

DB_COLORS_NEW = """        const STATUS_COLORS = { 'ONLINE': '#00ff00', 'INTERMITTENT': '#ffd700', 'OFFLINE': '#ff4040',
                                'NO PASSES': '#999999', 'UNVETTED': '#999999', 'LINK ERROR': '#ff4040',
                                'LOW SAMPLE': '#999999', 'STATION FAULT': '#999999' };"""

DB_FALLBACK_OLD = """                { text: item['Status'], color: STATUS_COLORS[item['Status']] || '#00ff00' },"""
DB_FALLBACK_NEW = """                { text: item['Status'], color: STATUS_COLORS[item['Status']] || '#999999' },  // unknown label is never green"""

DB_HUD_OLD = """                $('hud-epoch').textContent = data ? data['TLE Epoch'] : 'LIVE TLE';"""
DB_HUD_NEW = """                $('hud-epoch').textContent = data ? (data['TLE Epoch'] + (data['TLE Stale'] ? ' (STALE)' : '')) : 'LIVE TLE';"""

PATCHES = {
    "run_telemetry.py": [
        ("import math", RT_IMPORT_OLD, RT_IMPORT_NEW),
        ("evidence-gate constants", RT_CONST_OLD, RT_CONST_NEW),
        ("page-cap truncation flag", RT_FETCH_OLD, RT_FETCH_NEW),
        ("summarize / classify / wilson / TLE age", RT_CLASSIFY_OLD, RT_CLASSIFY_NEW),
        ("scan rows carry new fields", RT_SCAN_OLD, RT_SCAN_NEW),
    ],
    "hannibal_orbital.py": [
        ("fleet table colours + stale epoch", OR_FLEET_OLD, OR_FLEET_NEW),
        ("[L] screen stale epoch", OR_SCREEN_OLD, OR_SCREEN_NEW),
        ("[L] screen footer text", OR_FOOT_OLD, OR_FOOT_NEW),
    ],
    "blueglobe_dashboard.html": [
        ("dashboard status colours", DB_COLORS_OLD, DB_COLORS_NEW),
        ("unknown status not green", DB_FALLBACK_OLD, DB_FALLBACK_NEW),
        ("HUD stale tag", DB_HUD_OLD, DB_HUD_NEW),
    ],
}


def apply_to(path: Path, name: str, write: bool):
    original = path.read_text(encoding="utf-8")
    text = original
    notes, count = [], 0
    for label, old, new in PATCHES[name]:
        if new in text:
            notes.append(f"  {label}: already applied")
            continue
        if old not in text:
            notes.append(f"  {label}: ANCHOR NOT FOUND - file differs from the reviewed copy, left alone")
            continue
        text = text.replace(old, new, 1)
        notes.append(f"  {label}: patched")
        count += 1
    if write and text != original:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(path, backup)
            notes.append(f"  backup written to {backup.name}")
        else:
            notes.append(f"  backup {backup.name} already exists, kept")
        path.write_text(text, encoding="utf-8")
    return count, notes


def verify(path: Path) -> list[str]:
    if path.suffix != ".py":
        return []
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [f"  SYNTAX ERROR line {exc.lineno}: {exc.msg} - run --revert"]
    return []


# Numbers from the 2026-10 fleet scan (good, bad). Failed counts weren't shown
# on screen, so they are treated as bad here: the worst case for the satellite.
SCAN = [
    ("ISS (ZARYA)", 64, 18), ("FUNcube-1 (AO-73)", 4, 1), ("ESTCube-1", 0, 0),
    ("LAPAN-A2", 4, 0), ("METEOR M-2", 0, 1), ("OSCAR 7 (AO-7)", 0, 4), ("JAS-2 (FO-29)", 5, 8),
]
EXPECT = {
    "ISS (ZARYA)": "ONLINE", "FUNcube-1 (AO-73)": "LOW SAMPLE", "ESTCube-1": "NO PASSES",
    "LAPAN-A2": "LOW SAMPLE", "METEOR M-2": "LOW SAMPLE", "OSCAR 7 (AO-7)": "LOW SAMPLE",
    "JAS-2 (FO-29)": "INTERMITTENT",
}
EDGES = [  # (good, bad, failed, unvetted) -> expected
    ((8, 0, 0, 0), "ONLINE"), ((0, 8, 0, 0), "OFFLINE"), ((6, 2, 0, 0), "INTERMITTENT"),
    ((0, 0, 3, 0), "STATION FAULT"), ((0, 0, 0, 2), "UNVETTED"), ((7, 0, 9, 0), "LOW SAMPLE"),
    ((1, 9, 0, 0), "OFFLINE"), ((2, 8, 0, 0), "INTERMITTENT"),
]


def selftest(root: Path) -> int:
    sys.path.insert(0, str(root))
    sys.modules.pop("run_telemetry", None)
    try:
        import run_telemetry as rt
    except Exception as exc:  # noqa: BLE001
        print(f"[-] could not import run_telemetry from {root}: {exc}")
        return 1
    if not hasattr(rt, "wilson"):
        print("[-] run_telemetry is not patched yet (no wilson()); apply first")
        return 1
    failed = 0
    print("\nself-test: 2026-10 scan numbers")
    for name, good, bad in SCAN:
        got = rt.classify(good, bad, 0, 0)
        ok = got == EXPECT[name]
        failed += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:20s} {rt.health_text(good, bad):22s} {got}")
    print("self-test: edge cases")
    for args, want in EDGES:
        got = rt.classify(*args)
        ok = got == want
        failed += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] good/bad/failed/unvetted={args} -> {got}")
    from datetime import datetime, timezone
    age = rt.tle_age_days("2025-05-31T04:27:33.000000", datetime(2026, 10, 11, tzinfo=timezone.utc))
    ok = age is not None and 496 < age < 498 and rt.tle_age_days("garbage") is None
    failed += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] LAPAN-A2 TLE age = {age:.1f} days (stale > {rt.STALE_TLE_DAYS})")
    print("  all pass" if not failed else f"  {failed} FAILED")
    return 1 if failed else 0


def revert(root: Path) -> int:
    restored = 0
    for name in PATCHES:
        backup = (root / name).with_suffix(Path(name).suffix + ".bak")
        if backup.exists():
            shutil.copy2(backup, root / name)
            print(f"[+] restored {name} from {backup.name}")
            restored += 1
    if not restored:
        print("[-] no .bak files found")
    return 0 if restored else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default=".", help="folder holding the orbital modules")
    parser.add_argument("--apply", action="store_true", help="write changes (default is dry run)")
    parser.add_argument("--revert", action="store_true", help="restore every .bak")
    parser.add_argument("--selftest", action="store_true", help="run the classifier checks only")
    args = parser.parse_args()

    root = Path(args.dir).resolve()
    if args.revert:
        return revert(root)
    if args.selftest:
        return selftest(root)

    present = [n for n in PATCHES if (root / n).exists()]
    if not present:
        print(f"[-] none of {', '.join(PATCHES)} found in {root}")
        return 1
    print(f"{'APPLYING' if args.apply else 'DRY RUN - nothing will be written'}\n{root}\n")
    total = 0
    for name in present:
        print(name)
        count, notes = apply_to(root / name, name, args.apply)
        for note in notes:
            print(note)
        total += count
        if args.apply and count:
            for problem in verify(root / name):
                print(problem)
        print()
    for missing in [n for n in PATCHES if n not in present]:
        print(f"{missing}\n  not in this folder, skipped\n")

    if not args.apply:
        print(f"{total} change(s) staged. Re-run with --apply to write them.")
        return 0
    print(f"{total} change(s) written. Originals kept as .bak - `--revert` restores them.")
    return selftest(root) if (root / "run_telemetry.py").exists() else 0


if __name__ == "__main__":
    sys.exit(main())
