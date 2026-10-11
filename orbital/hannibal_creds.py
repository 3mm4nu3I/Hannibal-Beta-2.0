"""Credential lookup for the Orbital modules (environment variables are checked by the callers first).

Order, first match wins:
  1. typed this run          kept in memory only (start-up prompt / menu [K])
  2. saved on this computer  only if you answered "y" to "Remember ...?" (hannibal_vault: OS credential store,
                             or ~/.hannibal/credentials.json in YOUR user folder)
  3. hannibal_credentials.local.json next to the program, if you put one there
                             {"spacetrack_user": "...", "spacetrack_pass": "...", "n2yo_key": "..."}

Everything that comes from here is registered with secret_masking, so the literal value is scrubbed from every
screen, log line, error message and cache file even when it is not preceded by a "password=" label.
Nothing in this module prints or logs a secret.
"""
import json
import threading
from pathlib import Path

try:
    from secret_masking import register_secret
except ImportError:  # pragma: no cover
    def register_secret(value):
        pass

NAMES = ("spacetrack_user", "spacetrack_pass", "n2yo_key")
SECRET_NAMES = ("spacetrack_pass", "n2yo_key")
LOCAL_FILE = "hannibal_credentials.local.json"

_lock = threading.Lock()
_store = {}
_persistent = {}        # {name: value} from the saved / local layers, loaded lazily
_loaded = False         # set to False (or call reload_saved) to force a re-read


def local_file():
    try:
        from hannibal_net import base_dir
        return Path(base_dir()) / LOCAL_FILE
    except Exception:  # pragma: no cover
        return Path(__file__).resolve().parent / LOCAL_FILE


def _read_local():
    try:
        with open(local_file(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {k: str(data[k]).strip() for k in NAMES if isinstance(data, dict) and data.get(k)}
    except (OSError, ValueError):
        return {}


def _load_saved():
    found = _read_local()
    try:
        import hannibal_vault
        found.update(hannibal_vault.load())            # what you saved yourself beats the loose file
    except Exception:
        pass
    found = {k: v for k, v in found.items() if v and not str(v).upper().startswith("YOUR_")}
    for k in SECRET_NAMES:
        if found.get(k):
            register_secret(found[k])
    return found


def reload_saved():
    """Forget the cached saved/local values (after saving or forgetting) so the next lookup re-reads them."""
    global _loaded
    with _lock:
        _loaded = False


def session_set(name, value, secret=True):
    with _lock:
        _store[name] = str(value or "")
    if secret:
        register_secret(value)


def session_get(name, default=""):
    global _persistent, _loaded
    with _lock:
        if _store.get(name):
            return _store[name]
        if not _loaded:
            _persistent, _loaded = _load_saved(), True
        return _persistent.get(name, default)


def session_clear(name=None):
    with _lock:
        if name is None:
            _store.clear()
        else:
            _store.pop(name, None)
