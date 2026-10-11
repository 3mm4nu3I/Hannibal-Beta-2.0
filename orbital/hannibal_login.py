"""Ask for the Space-Track login and the N2YO key once per run.

* Typed passwords/keys are hidden (getpass), kept in this process's memory only (hannibal_creds), and
  registered with the secret masker so they are scrubbed from anything printed or logged.
* Nothing is written to disk unless you answer y to "Remember these on this computer?" (hannibal_vault). For a permanent setup use the environment variables
  (SPACETRACK_USER / SPACETRACK_PASS / N2YO_API_KEY): if they are set, you are never asked.
* Press Enter at any prompt to skip that service; you are not asked again until you pick
  [K] Logins & keys in the menu.
* Skipped automatically when input is not a terminal (pipes, scheduled runs).
"""
import getpass
import os
import sys

import hannibal_vault
from hannibal_creds import reload_saved, session_clear, session_get, session_set

_asked = {"spacetrack": False, "n2yo": False}


def _short(text, n=150):
    """One readable line: network exceptions can be very long."""
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 3] + "..."


def reset():
    _asked.update({"spacetrack": False, "n2yo": False})


def have_spacetrack():
    from hannibal_spacetrack import get_credentials
    return bool(get_credentials()[0])


def have_n2yo():
    from hannibal_n2yo import get_api_key
    return bool(get_api_key())


def _interactive(input_fn):
    return input_fn is not input or (hasattr(sys.stdin, "isatty") and sys.stdin.isatty())


def ask_spacetrack(input_fn=input, secret_fn=getpass.getpass, print_fn=print, verify=True, max_tries=3):
    """Prompt for username + password. Returns True if credentials are now set (and verified when possible)."""
    for attempt in range(max_tries):
        print_fn("")
        print_fn("  SPACE-TRACK LOGIN (free account: https://www.space-track.org/auth/createAccount)")
        print_fn("  Used for re-entries, close approaches, box score and TLE epochs. Press Enter to skip.")
        try:
            user = input_fn("  Username (your e-mail): ").strip()
            if not user:
                print_fn("  Skipped. Pick [K] in the menu any time to enter it.")
                return False
            pw = secret_fn("  Password (hidden as you type): ")
        except (EOFError, KeyboardInterrupt):
            print_fn("")
            return False
        if not pw:
            print_fn("  No password entered; skipped.")
            return False
        session_set("spacetrack_user", user, secret=False)
        session_set("spacetrack_pass", pw)           # memory only; also registered with the masker
        if not verify:
            return True
        try:
            from hannibal_spacetrack import SpaceTrack
            err = SpaceTrack(user=user, password=pw).login()
        except Exception as exc:  # never let a verification problem block the app
            err = f"could not verify ({type(exc).__name__})"
        if not err:
            print_fn("  Space-Track login OK. Kept for this session only.")
            return True
        print_fn(f"  [!] {_short(err)}")
        if "check username" not in err:       # network trouble, not a wrong password: keep what was typed
            print_fn("  Keeping it for this session anyway; the server could not be reached to confirm.")
            return True
        session_clear("spacetrack_user")
        session_clear("spacetrack_pass")
        if attempt < max_tries - 1:
            print_fn("  Try again.")
    return False


def ask_n2yo(input_fn=input, secret_fn=getpass.getpass, print_fn=print, verify=True):
    print_fn("")
    print_fn("  N2YO API KEY (free: n2yo.com > register > profile > API key; not the SOAP key)")
    print_fn("  Used for the Military / Globalstar overhead list and the satellite lookup. Press Enter to skip.")
    try:
        key = secret_fn("  API key (hidden as you type): ").strip()
    except (EOFError, KeyboardInterrupt):
        print_fn("")
        return False
    if not key:
        print_fn("  Skipped. Pick [K] in the menu any time to enter it.")
        return False
    session_set("n2yo_key", key)                     # memory only; also registered with the masker
    if verify:
        try:
            from hannibal_n2yo import N2YO
            res = N2YO(key=key).tle(25544)
            if res.ok:
                print_fn("  N2YO key OK. Kept for this session only.")
            elif "N2YO:" in res.error:
                print_fn(f"  [!] {_short(res.error)}")
                session_clear("n2yo_key")
                return False
            else:
                print_fn(f"  [~] could not confirm the key ({_short(res.error, 90)}); keeping it for this session.")
        except Exception as exc:
            print_fn(f"  [~] could not confirm the key ({type(exc).__name__}); keeping it for this session.")
    return True


def _typed_values(before):
    now = {k: session_get(k) for k in hannibal_vault.KEYS}
    return {k: v for k, v in now.items() if v and v != before.get(k)}


def offer_to_remember(typed, input_fn, print_fn):
    """Ask (default: no) whether to keep what was just typed for next time. Nothing is saved without a 'y'."""
    if not typed:
        return False
    names = " and ".join(n for n, k in (("Space-Track login", "spacetrack_pass"), ("N2YO key", "n2yo_key")) if k in typed)
    try:
        answer = input_fn(f"  Remember your {names} on this computer for next time? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer.startswith("y"):
        print_fn("  Not saved. You will be asked again next time.")
        return False
    where = hannibal_vault.save({**hannibal_vault.load(), **typed})
    reload_saved()
    print_fn(f"  Saved to {where}." if where else "  [!] Could not save it here; it stays in memory for this run.")
    return bool(where)


def offer_to_forget(input_fn, print_fn):
    if not hannibal_vault.has_saved():
        return False
    try:
        answer = input_fn("  Forget the logins saved on this computer? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if answer.startswith("y"):
        hannibal_vault.forget()
        reload_saved()
        session_clear()
        _asked.update({"spacetrack": False, "n2yo": False})
        print_fn("  Saved logins deleted.")
        return True
    return False


def ensure_logins(input_fn=input, secret_fn=getpass.getpass, print_fn=print, force=False, verify=True):
    """Ask for whatever is missing (once per run). Returns {'spacetrack': bool, 'n2yo': bool} = available now.

    Saved logins (only if you once said yes to "Remember...?") are loaded automatically and never asked for again.
    """
    if not force and not _interactive(input_fn):
        return {"spacetrack": have_spacetrack(), "n2yo": have_n2yo()}
    if force:
        offer_to_forget(input_fn, print_fn)
    before = {k: session_get(k) for k in hannibal_vault.KEYS}
    changed = False
    if force or (not have_spacetrack() and not _asked["spacetrack"]):
        _asked["spacetrack"] = True
        changed |= ask_spacetrack(input_fn, secret_fn, print_fn, verify)
    if force or (not have_n2yo() and not _asked["n2yo"]):
        _asked["n2yo"] = True
        changed |= ask_n2yo(input_fn, secret_fn, print_fn, verify)
    if changed:
        offer_to_remember(_typed_values(before), input_fn, print_fn)
    return {"spacetrack": have_spacetrack(), "n2yo": have_n2yo(), "changed": changed}
