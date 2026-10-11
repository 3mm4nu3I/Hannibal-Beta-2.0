"""FRED (Federal Reserve Bank of St. Louis) macro feed for Project Hannibal.

One place for the FRED API key and one client for every Hannibal module that needs
macro series (the [M] Macro screen in the orbital menu, hannibal_estimation.py).

THE KEY NEVER GOES IN SOURCE
  Looked up in this order, first hit wins:
    1. FRED_API_KEY environment variable           (setx FRED_API_KEY "...")
    2. the operating system's credential store     (python hannibal_fred.py --set-key)
       Windows Credential Manager / macOS Keychain / Secret Service, via `keyring`
    3. a key typed in the [M] screen               (memory only, gone when Hannibal closes)
  It is sent only to api.stlouisfed.org, through hannibal_net, so it is masked in every
  URL, log line and error message, never part of a cache key, and never written to disk
  by this module.

USAGE
  python hannibal_fred.py --set-key      store the key (typed hidden)
  python hannibal_fred.py --check        is a key available? (shows a masked form)
  python hannibal_fred.py --delete       remove the stored key
  python hannibal_fred.py                print the macro board once

Importing this module has no side effects and never touches the network.
"""
from __future__ import annotations

import getpass
import os
import sys

from hannibal_net import default_net

ENV_VAR = "FRED_API_KEY"
KEYRING_SERVICE = "Project Hannibal"
KEYRING_USER = "FRED_API_KEY"
BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# The board shown in [M]. Picked to match Hannibal's inflation-transmission work:
# prices, policy rate, curve, money velocity, energy and the dollar.
BOARD = [
    # series id       label                         units  yoy?
    ("CPIAUCSL",     "CPI, all items",              "idx", True),
    ("CPILFESL",     "Core CPI (ex food & energy)", "idx", True),
    ("PCEPILFE",     "Core PCE price index",        "idx", True),
    ("FEDFUNDS",     "Effective fed funds rate",    "%",   False),
    ("DGS10",        "10-year Treasury yield",      "%",   False),
    ("T10Y2Y",       "10y minus 2y spread",         "pp",  False),
    ("UNRATE",       "Unemployment rate",           "%",   False),
    ("M2V",          "Velocity of M2",              "x",   False),
    ("DCOILBRENTEU", "Brent crude, $/bbl",          "$",   False),
    ("DTWEXBGS",     "Broad trade-weighted dollar", "idx", False),
]

TTL_SECONDS = 6 * 3600   # FRED updates daily at most; low-internet profile stretches this 4x in hannibal_net

_session_key = ""        # typed in [M]; never persisted unless the user says so


# ------------------------------------------------------------------ the key ----
def _keyring():
    try:
        import keyring
        from keyring.backends import fail
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring
    except Exception:  # noqa: BLE001 - no keyring package / no backend: fall back quietly
        return None


def get_key() -> str:
    """The FRED key from env, the credential store or this session; '' if none."""
    env = os.environ.get(ENV_VAR, "").strip()
    if env:
        return env
    kr = _keyring()
    if kr is not None:
        try:
            stored = (kr.get_password(KEYRING_SERVICE, KEYRING_USER) or "").strip()
            if stored:
                return stored
        except Exception:  # noqa: BLE001
            pass
    return _session_key


def key_source() -> str:
    if os.environ.get(ENV_VAR, "").strip():
        return f"environment ({ENV_VAR})"
    kr = _keyring()
    if kr is not None:
        try:
            if kr.get_password(KEYRING_SERVICE, KEYRING_USER):
                return "credential store"
        except Exception:  # noqa: BLE001
            pass
    return "typed this session" if _session_key else ""


def set_session_key(value: str) -> None:
    global _session_key
    _session_key = (value or "").strip()


def store_key(value: str) -> str:
    """Save to the credential store. Returns where it went, or '' if no store is available."""
    kr = _keyring()
    if kr is None or not value.strip():
        return ""
    try:
        kr.set_password(KEYRING_SERVICE, KEYRING_USER, value.strip())
        if (kr.get_password(KEYRING_SERVICE, KEYRING_USER) or "") == value.strip():
            return "your operating system's credential store"
    except Exception:  # noqa: BLE001
        pass
    return ""


def delete_key() -> bool:
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.delete_password(KEYRING_SERVICE, KEYRING_USER)
        return True
    except Exception:  # noqa: BLE001
        return False


def masked(value: str) -> str:
    """Enough to recognise a key, never enough to use it."""
    if not value:
        return ""
    return value[:2] + "*" * max(4, len(value) - 4) + value[-2:] if len(value) > 6 else "*" * len(value)


# ------------------------------------------------------------------- client ----
def _validate(payload):
    if not isinstance(payload, dict):
        return "FRED returned something unexpected"
    if "error_message" in payload:
        return f"FRED: {payload.get('error_message')}"
    if not isinstance(payload.get("observations"), list):
        return "FRED returned no observations"
    return ""


def observations(series_id: str, limit: int = 13, net=None):
    """Latest `limit` observations, newest first, as [(date, float|None)], plus (error, note).

    Missing values ('.') come back as None. Goes through hannibal_net: masked, cached
    (6 h, served stale if the live call fails), throttled.
    """
    key = get_key()
    if not key:
        return [], "no FRED key: menu [M] -> K, or python hannibal_fred.py --set-key", ""
    res = (net or default_net()).request(
        "GET", BASE_URL,
        params={"series_id": series_id, "api_key": key, "file_type": "json",
                "sort_order": "desc", "limit": int(limit)},
        ttl=TTL_SECONDS, cache_key=f"fred:{series_id}:{int(limit)}", validate=_validate)
    if res.error and res.data is None:
        return [], res.error, ""
    rows = []
    for obs in (res.data or {}).get("observations", []):
        raw = obs.get("value", ".")
        try:
            val = float(raw)
        except (TypeError, ValueError):
            val = None
        rows.append((obs.get("date", ""), val))
    return rows, "", (res.note or ("cached" if getattr(res, "cached", False) else ""))


def board(net=None):
    """One row per BOARD series: latest value, change vs previous print, and YoY where it makes sense."""
    out = []
    for sid, label, units, yoy in BOARD:
        rows, error, note = observations(sid, limit=13, net=net)
        vals = [(d, v) for d, v in rows if v is not None]
        row = {"id": sid, "label": label, "units": units, "date": "", "value": None,
               "change": None, "yoy": None, "error": error, "note": note}
        if vals:
            row["date"], row["value"] = vals[0]
            if len(vals) > 1:
                row["change"] = vals[0][1] - vals[1][1]
            if yoy and len(vals) >= 13 and vals[12][1]:
                row["yoy"] = (vals[0][1] / vals[12][1] - 1.0) * 100.0
        out.append(row)
    return out


# ------------------------------------------------------------------- screen ----
def _fmt(v, units):
    if v is None:
        return "--"
    if units in ("%", "pp"):
        return f"{v:.2f}{'%' if units == '%' else ' pp'}"
    if units == "$":
        return f"${v:,.2f}"
    return f"{v:,.2f}" if abs(v) < 1000 else f"{v:,.1f}"


def screen_macro(ask, out, color):
    """[M] in the orbital menu."""
    import hannibal_art as art

    def c(text, code):
        return art.paint(text, code, enabled=color)

    out(art.section("MACRO // FRED  (Federal Reserve Bank of St. Louis)", 89, color))
    if not get_key():
        out("  No FRED key found (FRED_API_KEY, the credential store, or this session).")
        typed = getpass.getpass("  Paste your FRED key (hidden, Enter to skip): ").strip()
        if not typed:
            out("  Skipped. Free key: fred.stlouisfed.org > My Account > API Keys.")
            return
        set_session_key(typed)
        if ask("  Remember it on this computer (credential store)? [y/N]: ", "n").lower().startswith("y"):
            where = store_key(typed)
            out(f"  Saved to {where}." if where else "  No credential store here: kept for this session only "
                f"(or: setx {ENV_VAR} \"...\").")
    out(f"  key: {c(masked(get_key()), art.GRAY)}  from {key_source()}")
    out("")
    rows = board()
    head = f"  {'SERIES':<13}{'WHAT':<30}{'LATEST':>12}  {'DATE':<11}{'CHANGE':>10}{'YoY':>9}"
    out(c(head, art.GOLD))
    out(c("  " + "-" * 85, art.RED))
    errors = set()
    for r in rows:
        if r["error"]:
            errors.add(r["error"])
            out(f"  {r['id']:<13}{r['label'][:29]:<30}{c('--', art.GRAY):>21}")
            continue
        chg = r["change"]
        chg_txt = "--" if chg is None else f"{chg:+.2f}"
        chg_col = art.GRAY if not chg else (art.RED if chg > 0 and r["units"] != "$" else art.GREEN)
        yoy = "" if r["yoy"] is None else f"{r['yoy']:+.1f}%"
        stale = c(" *", art.GOLD) if r["note"] and "failed" in r["note"] else ""
        out(f"  {r['id']:<13}{r['label'][:29]:<30}{_fmt(r['value'], r['units']):>12}  {r['date']:<11}"
            f"{c(f'{chg_txt:>10}', chg_col)}{c(f'{yoy:>9}', art.GOLD)}{stale}")
    if errors:
        out("")
        for e in sorted(errors):
            out(c(f"  ! {e}", art.RED))
    out("")
    out(c(f"  {art.sym('star')} Source: FRED, Federal Reserve Bank of St. Louis. Cached 6 h; * = live call failed, "
          f"last cached value shown.", art.GRAY))


# ---------------------------------------------------------------------- CLI ----
def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    arg = argv[0] if argv else ""
    if arg == "--set-key":
        value = getpass.getpass("FRED API key (hidden): ").strip()
        if not value:
            print("[-] Nothing entered.")
            return 1
        where = store_key(value)
        if where:
            print(f"[+] Stored in {where} ({masked(value)}).")
            return 0
        print(f"[-] No credential store available (pip install keyring). Use: setx {ENV_VAR} \"...\"")
        return 1
    if arg == "--check":
        key = get_key()
        print(f"[+] FRED key from {key_source()}: {masked(key)}" if key else "[-] No FRED key found.")
        return 0 if key else 1
    if arg == "--delete":
        print("[+] Deleted from the credential store." if delete_key() else "[-] Nothing stored.")
        return 0
    if arg in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        import hannibal_security_bootstrap  # noqa: F401  (masks stdout for standalone runs)
    except ImportError:
        pass
    screen_macro(lambda prompt, default="": input(prompt) or default, print, sys.stdout.isatty())
    return 0


if __name__ == "__main__":
    sys.exit(main())
