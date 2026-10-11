#!/usr/bin/env python3
"""patch_hannibal.py -- wire the Orbital Directorate into hannibal_terminal.py.

    python patch_hannibal.py                     patch hannibal_terminal.py next to this file
    python patch_hannibal.py path\\to\\terminal.py  patch a specific copy
    python patch_hannibal.py --dry-run           show what would change, write nothing
    python patch_hannibal.py --status            report which parts are already applied
    python patch_hannibal.py --revert            restore the backup made by the first patch
    python patch_hannibal.py --no-fixes          skip the optional host-bug fixes (see below)

What it adds to the terminal
    [L] fleet link health (SatNOGS + Space-Track)        [B] open the 3D BlueGlobe dashboard
    [V] Orbital Ops menu (re-entries, conjunctions, box score, sky tonight, NASA/JPL, ADS-B feeder)
    plus the import of hannibal_security_bootstrap so every API call and every printed line is masked.

Safety
    * all-or-nothing: if any anchor is missing nothing is written
    * idempotent: run it twice and the second run changes nothing
    * a backup (<file>.pre-orbital.bak) is made once, before the first change
    * the result is compiled (ast.parse) before it is written; the write is atomic
    * a first-generation integration (the in-file satellite glue) is migrated automatically

Optional host-bug fixes (on by default, --no-fixes to skip). These are bugs in the terminal itself
that stop it from running at all, found while integrating:
    audit_event()          uses datetime.now(timezone.utc) but `datetime` is the module  -> AttributeError at login
    sanitize_terminal_text referenced but never defined                                   -> NameError
    log_to_db / log_insider_to_db referenced but never defined                            -> NameError on first kinetic/insider item
    hotkeys R,A,J,E,N      lowercase keypress never matched the uppercase MARKETS keys
"""
import argparse
import ast
import os
import re
import shutil
import sys
from pathlib import Path

BACKUP_SUFFIX = ".pre-orbital.bak"
TAG = "[ORBITAL-PATCH:{}]"

# ------------------------------------------------------------------ snippets ----
IMPORT_BLOCK = '''
# ---------------------------------------------------------
# ORBITAL DIRECTORATE (satellites, re-entries, NASA/JPL)   # [ORBITAL-PATCH:imports]
# ---------------------------------------------------------
# Every import is guarded: a missing or broken optional file must never stop the terminal from
# starting. HANNIBAL_NO_MASK=1 skips the output redaction. The bootstrap is imported explicitly
# because sitecustomize.py is not picked up by `python hannibal_terminal.py` and never by the .exe.
if os.environ.get("HANNIBAL_NO_MASK") != "1":
    try:
        import hannibal_security_bootstrap  # noqa: F401  (installs redaction on import)
    except Exception:
        pass

SAT_IMPORT_ERROR = ""
try:
    import hannibal_orbital as sat_ops
except Exception as _sat_exc:  # pragma: no cover
    sat_ops = None
    SAT_IMPORT_ERROR = f"{type(_sat_exc).__name__}: {_sat_exc}"


def _sat_missing():
    print(f" {RED}Orbital module not loaded:{RESET} {SAT_IMPORT_ERROR}")
    print(f" {GRAY}Keep hannibal_orbital.py and its hannibal_*.py / run_telemetry.py siblings next to the terminal.{RESET}")


def render_sat_view():
    sat_ops.render_sat_view() if sat_ops else _sat_missing()


def sat_refresh_async(force=False):
    if sat_ops:
        sat_ops.sat_refresh_async(force)


def sat_launch_dashboard():
    if sat_ops:
        sat_ops.sat_launch_dashboard()


def render_ops_home():
    sat_ops.render_ops_home() if sat_ops else _sat_missing()


def sat_ops_menu():
    """Blocking menu -- same pattern as the [T] chat and [Y] speed prompts."""
    if not sat_ops:
        return
    try:
        clear_screen()
    except Exception:
        pass
    try:
        sat_ops.run_menu(animate=False)
    except (EOFError, KeyboardInterrupt):
        pass

'''

VIEW_L = '''                elif view_key == "L":  # [ORBITAL-PATCH:view_L]
                    render_sat_view()

'''
VIEW_V = '''                elif view_key == "V":  # [ORBITAL-PATCH:view_V]
                    render_ops_home()

'''
HANDLER_LB = '''            elif key_pressed == 'L':  # [ORBITAL-PATCH:handler_L]
                # Orbital view. Pressing [L] while already on it forces a rescan; otherwise the
                # view only rescans when the cached report is stale.
                with view_lock:
                    already_there = (current_view == 'L')
                    current_view = 'L'
                if already_there:
                    sat_refresh_async(force=True)
            elif key_pressed == 'B':  # [ORBITAL-PATCH:handler_B]
                # Launch the localhost-only BlueGlobe dashboard without leaving the current page.
                threading.Thread(target=sat_launch_dashboard, name="Sat-Dashboard", daemon=True).start()
'''
HANDLER_V = '''            elif key_pressed == 'V':  # [ORBITAL-PATCH:handler_V]
                # First press shows the Orbital Ops page; pressing [V] again opens the menu.
                with view_lock:
                    already_there = (current_view == 'V')
                    current_view = 'V'
                if already_there:
                    sat_ops_menu()
'''

FIX_LOG_FUNCS = '''# INTEGRATION FIX [ORBITAL-PATCH:fix_log_funcs]: log_to_db() and log_insider_to_db() are called from
# process_feed / the SEC pipeline but were never defined (NameError the first time a kinetic / infra /
# labor / macro / insider item was classified). They match the intel_logs / insider_logs tables created
# in init_db() and never raise: a logging failure must not take down feed processing.
def log_to_db(category, region, headline, data_val, prediction):
    if db_conn is None:
        return
    try:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        with db_lock:
            db_conn.execute(
                "INSERT INTO intel_logs (timestamp, category, region, headline, data_val, prediction) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ts, str(category), str(region), sanitize_text(headline, 500), str(data_val)[:200],
                 _ansi_re.sub("", str(prediction))[:200]))
            db_conn.commit()
    except Exception as exc:
        logger.debug("log_to_db failed: %s", exc)


def log_insider_to_db(tx):
    if db_conn is None:
        return
    try:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        with db_lock:
            db_conn.execute(
                "INSERT INTO insider_logs (timestamp, issuer, owner, role, code, shares, price, value_usd) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (ts, str(tx["issuer"]), sanitize_text(tx["owner"], 200), sanitize_text(tx["role"], 200),
                 str(tx["code"]), float(tx["shares"]), float(tx["price"]), float(tx["value"])))
            db_conn.commit()
    except Exception as exc:
        logger.debug("log_insider_to_db failed: %s", exc)


'''
FIX_SANITIZE = '''# INTEGRATION FIX [ORBITAL-PATCH:fix_sanitize]: referenced by audit_event() and safe_request() but never defined.
def sanitize_terminal_text(value, limit=2000):
    return sanitize_text(value, limit)


'''


# ------------------------------------------------------------------ helpers ----
class PatchError(Exception):
    pass


def _once(text, anchor, what):
    n = text.count(anchor)
    if n != 1:
        raise PatchError(f"{what}: expected exactly one anchor, found {n}  ({anchor.strip()[:70]!r})")
    return text.index(anchor)


def _insert_before(text, anchor, block, what):
    i = _once(text, anchor, what)
    return text[:i] + block + text[i:]


def _legacy_strip(text):
    """Remove the first-generation in-file satellite glue (if present). Returns (text, changed)."""
    changed = False
    # 1. the guarded import block
    m = re.search(r"# -{20,}\n# OPTIONAL MODULES: output redaction \+ orbital/satellite telemetry\n.*?"
                  r"SAT_IMPORT_ERROR = f\"\{type\(_sat_exc\)\.__name__\}: \{_sat_exc\}\"\n\n?", text, re.S)
    if m:
        text, changed = text[:m.start()] + text[m.end():], True
    # 2. the glue functions, up to the MAIN UI LOOP banner
    m = re.search(r"# -{20,}\n# ORBITAL / SATELLITE TELEMETRY\s+--\s+\[L\] view, \[B\] dashboard\n.*?(?=# -{20,}\n# MAIN UI LOOP)",
                  text, re.S)
    if m:
        text, changed = text[:m.start()] + text[m.end():], True
    return text, changed


# ------------------------------------------------------------------ the patches ----
def apply_patches(text, fixes=True):
    """Return (new_text, [(name, 'applied'|'present'|'migrated')])."""
    report = []
    text, migrated = _legacy_strip(text)
    if migrated:
        report.append(("legacy in-file glue", "migrated"))

    # -- imports + thin wrappers (after the cryptography imports; RED/GRAY/RESET are looked up at call time)
    if TAG.format("imports") in text:
        report.append(("imports", "present"))
    else:
        anchor = "from cryptography.hazmat.primitives import hashes\n"
        i = _once(text, anchor, "imports") + len(anchor)
        text = text[:i] + IMPORT_BLOCK + text[i:]
        report.append(("imports", "applied"))

    # -- views
    views = [("view_L", 'view_key == "L"', VIEW_L), ("view_V", 'view_key == "V"', VIEW_V)]
    for name, probe, block in views:
        if probe in text:
            report.append((name, "present"))
        else:
            text = _insert_before(text, '                elif view_key == "H":', block, name)
            report.append((name, "applied"))

    # -- footer hint
    if "[V] Ops" in text:
        report.append(("footer", "present"))
    elif "[L] Orbital | [B] Globe" in text:  # first-generation footer
        text = text.replace("[L] Orbital | [B] Globe", "[L] Orbital | [B] Globe | [V] Ops", 1)
        report.append(("footer", "applied"))
    else:
        _once(text, "[T] Chat | [Y] Speed", "footer")
        text = text.replace("[T] Chat | [Y] Speed", "[T] Chat | [L] Orbital | [B] Globe | [V] Ops | [Y] Speed", 1)
        report.append(("footer", "applied"))

    # -- hotkey list: also fixes lowercase r/a/j/e/n never matching the uppercase MARKETS keys
    new_keys = "elif key.upper() in MARKETS or key in ['w', 'k', 'i', 'c', 'p', 'h', 'g', 'm', 's', 't', 'y', 'l', 'b', 'v']:"
    if "'l', 'b', 'v']" in text:
        report.append(("hotkeys", "present"))
    else:
        for old in ("elif key.upper() in MARKETS or key in ['w', 'k', 'i', 'c', 'p', 'h', 'g', 'm', 's', 't', 'y', 'l', 'b']:",
                    "elif key in MARKETS or key in ['w', 'k', 'i', 'c', 'p', 'h', 'g', 'm', 's', 't', 'y']:"):
            if old in text:
                text = text.replace(old, new_keys, 1)
                report.append(("hotkeys", "applied"))
                break
        else:
            raise PatchError("hotkeys: could not find the key-list line in the input loop")

    # -- key handlers (before the [Y] speed handler)
    anchor = "            elif key_pressed == 'Y':"
    if "key_pressed == 'L'" in text:
        report.append(("handler_L/B", "present"))
    else:
        text = _insert_before(text, anchor, HANDLER_LB, "handler_L/B")
        report.append(("handler_L/B", "applied"))
    if "key_pressed == 'V'" in text:
        report.append(("handler_V", "present"))
    else:
        text = _insert_before(text, anchor, HANDLER_V, "handler_V")
        report.append(("handler_V", "applied"))

    # -- optional host-bug fixes
    if fixes:
        old_ts = '"ts": datetime.now(timezone.utc).isoformat()'
        if old_ts in text:
            text = text.replace(old_ts, '"ts": datetime.datetime.now(datetime.timezone.utc).isoformat()', 1)
            report.append(("fix: audit_event datetime", "applied"))
        else:
            report.append(("fix: audit_event datetime", "present"))
        if re.search(r"^def sanitize_terminal_text\b", text, re.M):
            report.append(("fix: sanitize_terminal_text", "present"))
        else:
            text = _insert_before(text, "def sanitize_text(", FIX_SANITIZE, "fix_sanitize")
            report.append(("fix: sanitize_terminal_text", "applied"))
        if re.search(r"^def log_to_db\b", text, re.M) and re.search(r"^def log_insider_to_db\b", text, re.M):
            report.append(("fix: log_to_db / log_insider_to_db", "present"))
        else:
            text = _insert_before(text, "def audit_event(event, **details):", FIX_LOG_FUNCS, "fix_log_funcs")
            report.append(("fix: log_to_db / log_insider_to_db", "applied"))
    return text, report


# ------------------------------------------------------------------ CLI ----
def _read(path):
    """Returns (text_with_LF, had_crlf, had_bom). Windows editors often save CRLF / BOM."""
    raw = Path(path).read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
    crlf = "\r\n" in text
    return text.replace("\r\n", "\n"), crlf, bom


def _write_atomic(path, text, crlf=False, bom=False):
    data = text.replace("\n", "\r\n") if crlf else text
    raw = (b"\xef\xbb\xbf" if bom else b"") + data.encode("utf-8")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Wire the Orbital Directorate into hannibal_terminal.py")
    ap.add_argument("target", nargs="?", help="terminal file (default: hannibal_terminal.py next to this script)")
    ap.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    ap.add_argument("--status", action="store_true", help="report which parts are applied; write nothing")
    ap.add_argument("--revert", action="store_true", help="restore the backup made by the first patch")
    ap.add_argument("--no-fixes", action="store_true", help="skip the optional host-bug fixes")
    args = ap.parse_args(argv)

    target = Path(args.target) if args.target else Path(__file__).resolve().parent / "hannibal_terminal.py"
    if not target.is_file():
        print(f"[!] {target} not found. Pass the path to hannibal_terminal.py.")
        return 2
    backup = target.with_name(target.name + BACKUP_SUFFIX)

    if args.revert:
        if not backup.is_file():
            print(f"[!] no backup found at {backup.name}; nothing to revert.")
            return 1
        shutil.copy2(backup, target)
        print(f"[+] restored {target.name} from {backup.name}")
        return 0

    original, crlf, bom = _read(target)
    try:
        patched, report = apply_patches(original, fixes=not args.no_fixes)
        ast.parse(patched)
    except PatchError as exc:
        print(f"[!] not patched -- {exc}")
        print("    The terminal file differs from what this patcher expects; nothing was changed.")
        return 1
    except SyntaxError as exc:
        print(f"[!] not patched -- the result would not compile ({exc}); nothing was changed.")
        return 1

    width = max(len(n) for n, _ in report)
    for name, state in report:
        print(f"  {name:<{width}}  {state}")
    changed = patched != original
    if args.status:
        print("[=] up to date" if not changed else "[~] not fully applied -- run without --status to apply")
        return 0
    if not changed:
        print("[=] already patched -- nothing to do")
        return 0
    if args.dry_run:
        print("[dry-run] would modify", target.name, "(nothing written)")
        return 0
    if not backup.exists():
        shutil.copy2(target, backup)
        print(f"[+] backup: {backup.name}")
    _write_atomic(target, patched, crlf, bom)
    print(f"[+] patched {target.name}. Restart the terminal; press [V] for the Orbital Ops menu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
