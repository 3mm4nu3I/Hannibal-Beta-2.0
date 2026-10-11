"""Optional "remember me" store for the Space-Track login and the N2YO key.

Nothing is stored unless you answer **y** to "Remember these on this computer?". Then:

  1. the operating system's credential store is used if the `keyring` package is installed
     (Windows Credential Manager / macOS Keychain / Secret Service), otherwise
  2. a small JSON file in YOUR user profile folder (~/.hannibal/credentials.json, owner-only
     permissions where the OS supports them). It is readable plain text, so anyone who can read
     your profile folder can read it. The project folder is never used, so the dashboard server
     can never serve it and a zip of the project can never contain it.

Pick menu [K] and answer y to "Forget saved logins?" to delete it again.
Set HANNIBAL_VAULT_DIR to use another folder (used by the tests).
"""
import json
import os
from pathlib import Path

SERVICE = "hannibal-orbital"
ACCOUNT = "logins"
FILE_NAME = "credentials.json"
KEYS = ("spacetrack_user", "spacetrack_pass", "n2yo_key")


def _dir():
    return Path(os.environ.get("HANNIBAL_VAULT_DIR") or (Path.home() / ".hannibal"))


def _path():
    return _dir() / FILE_NAME


def _keyring():
    if os.environ.get("HANNIBAL_VAULT_DIR"):      # explicit folder = file backend
        return None
    try:
        import keyring
        from keyring.backends import fail
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring
    except Exception:
        return None


def _clean(data):
    return {k: str(data[k]) for k in KEYS if isinstance(data, dict) and data.get(k)}


def load():
    """Saved values as a dict (empty if nothing is saved or it cannot be read). Never raises."""
    kr = _keyring()
    if kr is not None:
        try:
            raw = kr.get_password(SERVICE, ACCOUNT)
            if raw:
                return _clean(json.loads(raw))
        except Exception:
            pass
    try:
        with open(_path(), "r", encoding="utf-8") as fh:
            return _clean(json.load(fh))
    except (OSError, ValueError):
        return {}


def save(data):
    """Store `data`. Returns a plain-language description of where it went, or '' on failure."""
    data = _clean(data)
    if not data:
        return ""
    raw = json.dumps(data)
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE, ACCOUNT, raw)
            return "your operating system's credential store"
        except Exception:
            pass
    try:
        d = _dir()
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
        tmp = _path().with_name(FILE_NAME + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(raw)
        os.replace(tmp, _path())
        try:
            os.chmod(_path(), 0o600)
        except OSError:
            pass
        return f"{_path()} (plain text in your user profile folder)"
    except OSError:
        return ""


def forget():
    """Delete everything saved. Returns True if something was removed."""
    removed = False
    kr = _keyring()
    if kr is not None:
        try:
            if kr.get_password(SERVICE, ACCOUNT):
                kr.delete_password(SERVICE, ACCOUNT)
                removed = True
        except Exception:
            pass
    try:
        _path().unlink()
        removed = True
    except OSError:
        pass
    return removed


def has_saved():
    return bool(load())
