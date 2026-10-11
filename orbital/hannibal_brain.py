"""HANNIBAL // MARKET BRAIN  -  developer-only module.

Shows what the market is "thinking" as a living brain: the ten lobes of the Happiness
Formula Architect brain (same names, same palette) each carry one market region, and
flowing particles travel along the transmission paths Hannibal models
(energy -> inflation -> policy -> curve -> equities, fear -> equities, ...).
How fast and how densely they flow comes from real data, not from noise.

    lobe            market region            FRED series (stress direction)
    Prefrontal      policy & short rates     FEDFUNDS, DGS2           (up = stress)
    Motor           equities                 SP500                    (down = stress)
    Somatosensory   energy                   Brent, WTI, gasoline     (up = stress)
    Parietal        the dollar               broad dollar, EUR/USD    (dollar up = stress)
    Occipital       yield curve              10y-2y (down), 10y (up)
    Auditory        labour                   UNRATE, initial claims   (up = stress)
    Nucleus         liquidity                Fed balance sheet, M2    (down = stress)
    Amygdala        fear & credit            VIX, high-yield spread   (up = stress)
    Insula          inflation                CPI, core PCE            (up = stress)
    Cerebellum      signal health            Hannibal satellite link health (telemetry_report.json)

ACTIVITY  for each series: the latest move divided by the spread of its recent moves (a
z-score), squashed with the same bounded map Hannibal uses elsewhere: 1 - exp(-|z| / 1.5).
A lobe takes its loudest series (max-merge, as in the equation reference); its stress keeps
that series' sign (+ = worrying). Clamped below 1.0 like hannibal_calcs.bounded().
A lobe with no data stays dark rather than being guessed.

THINKING  every path gets strength sqrt(activity_src * activity_dst); the caption is the
strongest chain of active paths, e.g. "Energy -> Inflation -> Policy rate".

SECURITY (all layers on when it opens)
  * developer gate   a dev key you set once (python hannibal_brain.py --set-dev-key); only a
                     PBKDF2 hash is stored, in the OS credential store (or, without one, an
                     owner-only file in your user profile, never the project folder).
                     3 wrong tries -> 5 min lockout; every failure goes to the breach log.
  * local only       binds 127.0.0.1 on a random port; Host header must be localhost
                     (DNS-rebinding guard, same rule as BlueGlobe).
  * one-time launch  the browser opens with a single-use code (valid 60 s) that is swapped
                     for an HttpOnly, SameSite=Strict session cookie (2 h). No cookie, no data.
  * allow-list       / , /brain , /state.json only; anything else is 404 + breach log.
  * headers          strict Content-Security-Policy with a per-response nonce (no external
                     scripts, fonts or connections), frame-ancestors none, nosniff,
                     no-referrer, no-store.
  * masking          errors and console output pass through secret_masking; the FRED key
                     stays inside hannibal_fred / hannibal_net and never reaches the page.

USAGE
  python hannibal_brain.py --set-dev-key     set or change the developer key
  python hannibal_brain.py --check           is a dev key set? is FRED reachable?
  python hannibal_brain.py                   dev gate, then open the brain in your browser
  python hannibal_brain.py --export FILE     dev gate, then write the current state as JSON
                                             (feed for the Happiness Formula Architect app)
  orbital menu [R]                           same as the plain run, inside Hannibal

Importing this module has no side effects and never touches the network.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import http.server
import json
import math
import os
import secrets
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from secret_masking import redact_text
except ImportError:  # pragma: no cover
    def redact_text(value):
        return str(value)

HOST = "127.0.0.1"
SESSION_SECONDS = 2 * 3600
LAUNCH_CODE_SECONDS = 60
LOCKOUT_AFTER = 3
LOCKOUT_SECONDS = 300
PBKDF2_ROUNDS = 240_000
KEYRING_SERVICE = "Project Hannibal"
KEYRING_USER = "HANNIBAL_DEV_KEY_HASH"
REFRESH_SECONDS = 15 * 60   # recompute the state at most this often (FRED itself is cached 6 h)

# ------------------------------------------------------------------ lobes ----
# (id, lobe name, market region, colour from the Happiness Formula Architect palette, series)
# series: (FRED id, label, stress direction: +1 = a rise is stress, -1 = a fall is stress)
LOBES = [
    ("prefrontal", "Prefrontal", "Policy rate", "#22d3ee",
     [("FEDFUNDS", "Fed funds", +1), ("DGS2", "2y Treasury", +1)]),
    ("motor", "Motor", "Equities", "#a855f7",
     [("SP500", "S&P 500", -1)]),
    ("somato", "Somatosensory", "Energy", "#f59e0b",
     [("DCOILBRENTEU", "Brent", +1), ("DCOILWTICO", "WTI", +1), ("GASREGW", "US gasoline", +1)]),
    ("parietal", "Parietal", "Dollar", "#14b8a6",
     [("DTWEXBGS", "Broad dollar", +1), ("DEXUSEU", "USD per EUR", -1)]),
    ("occipital", "Occipital", "Yield curve", "#6366f1",
     [("T10Y2Y", "10y-2y spread", -1), ("DGS10", "10y Treasury", +1)]),
    ("auditory", "Auditory", "Labour", "#f97316",
     [("UNRATE", "Unemployment", +1), ("ICSA", "Initial claims", +1)]),
    ("nucleus", "Nucleus", "Liquidity", "#10b981",
     [("WALCL", "Fed balance sheet", -1), ("M2SL", "M2 money", -1)]),
    ("amygdala", "Amygdala", "Fear & credit", "#ef4444",
     [("VIXCLS", "VIX", +1), ("BAMLH0A0HYM2", "High-yield spread", +1)]),
    ("insula", "Insula", "Inflation", "#ec4899",
     [("CPIAUCSL", "CPI", +1), ("PCEPILFE", "Core PCE", +1)]),
    ("cerebellum", "Cerebellum", "Signal health", "#84cc16", []),   # from telemetry_report.json
]

# Transmission paths (source, target, what it means)
EDGES = [
    ("somato", "insula", "Energy prices feed inflation"),
    ("insula", "prefrontal", "Inflation pushes the policy rate"),
    ("prefrontal", "occipital", "Policy reshapes the yield curve"),
    ("occipital", "motor", "The curve reprices equities"),
    ("amygdala", "motor", "Fear hits equities"),
    ("nucleus", "motor", "Liquidity lifts equities"),
    ("parietal", "somato", "The dollar moves commodity prices"),
    ("auditory", "prefrontal", "Labour data steers policy"),
    ("amygdala", "parietal", "Fear bids the dollar"),
    ("prefrontal", "parietal", "Rates move the dollar"),
    ("nucleus", "amygdala", "Draining liquidity breeds fear"),
    ("cerebellum", "prefrontal", "Signal health sets confidence"),
]
ACTIVE = 0.25   # a path counts as "firing" above this strength
_ONE_MINUS_EPS = math.nextafter(1.0, 0.0)


# -------------------------------------------------------------- the maths ----
def series_activity(values, direction):
    """values newest first (floats, None allowed). -> (activity 0..1, signed stress -1..1, z) or None."""
    vals = [v for v in values if v is not None]
    if len(vals) < 6:
        return None
    moves = [vals[i] - vals[i + 1] for i in range(len(vals) - 1)]
    latest, history = moves[0], moves[1:]
    mean = sum(history) / len(history)
    var = sum((m - mean) ** 2 for m in history) / max(1, len(history) - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return 0.0, 0.0, 0.0
    z = (latest - mean) / sd
    # same clamp as hannibal_calcs.bounded(): float64 rounds 1 - exp(-38) up to exactly 1.0
    activity = min(1.0 - math.exp(-abs(z) / 1.5), _ONE_MINUS_EPS)
    stress = activity * (1 if z * direction > 0 else -1) if z else 0.0
    return activity, stress, z


def telemetry_activity():
    """Cerebellum: share of satellites NOT reported healthy in the last scan -> stress."""
    try:
        import run_telemetry as rt
        rows, _age = rt.load_cached_report()
    except Exception:  # noqa: BLE001
        rows = []
    judged = [r for r in rows if r.get("Status") in ("ONLINE", "INTERMITTENT", "OFFLINE")]
    if not judged:
        return None
    bad = sum(1 for r in judged if r.get("Status") != "ONLINE") / len(judged)
    return bad, bad, None


def compute_state(fetch=None, telemetry=telemetry_activity, now=None):
    """Build the full brain state. fetch(series_id) -> (rows newest-first [(date, val)], error)."""
    if fetch is None:
        import hannibal_fred

        def fetch(sid):
            rows, err, _note = hannibal_fred.observations(sid, limit=60)
            return rows, err
    lobes, errors = [], set()
    for lid, name, region, colour, series in LOBES:
        acts, stresses, detail = [], [], []
        if lid == "cerebellum":
            t = telemetry()
            if t is not None:
                acts.append(t[0]); stresses.append(t[1])
                detail.append({"id": "telemetry", "label": "Satellite links not ONLINE",
                               "value": round(t[0] * 100, 1), "date": "", "z": None})
        for sid, label, direction in series:
            rows, err = fetch(sid)
            if err:
                errors.add(redact_text(err))
            res = series_activity([v for _d, v in rows], direction)
            latest = next(((d, v) for d, v in rows if v is not None), ("", None))
            detail.append({"id": sid, "label": label, "value": latest[1], "date": latest[0],
                           "z": None if res is None else round(res[2], 2)})
            if res is not None:
                acts.append(res[0]); stresses.append(res[1])
        # max-merge, as in the Hannibal equation reference: the loudest channel speaks for the
        # lobe, so one quiet series cannot dilute a real shock in its neighbour.
        top = max(range(len(acts)), key=lambda i: acts[i]) if acts else None
        lobes.append({
            "id": lid, "name": name, "region": region, "color": colour,
            "activity": min(round(acts[top], 3), 0.999) if acts else None,   # rounding must not undo the clamp
            "stress": round(stresses[top], 3) if acts else None,
            "series": detail,
        })
    by = {l["id"]: l for l in lobes}
    edges = []
    for src, dst, label in EDGES:
        a, b = by[src]["activity"], by[dst]["activity"]
        strength = math.sqrt(a * b) if a is not None and b is not None else 0.0
        edges.append({"src": src, "dst": dst, "label": label, "strength": round(strength, 3)})
    return {
        "generated": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC"),
        "profile": os.getenv("HANNIBAL_NET_PROFILE", "normal").strip().lower() or "normal",
        "lobes": lobes, "edges": edges, "thinking": thinking(lobes, edges),
        "errors": sorted(errors),
        "source": "FRED, Federal Reserve Bank of St. Louis; Hannibal telemetry",
        "theorem": _theorem_state(),
    }


def _theorem_state():
    """The Grand Unified Happiness Theorem card (hannibal_theorem). Never breaks the market brain."""
    try:
        import hannibal_theorem
        return hannibal_theorem.evaluate(hannibal_theorem.load_profile())
    except Exception as exc:  # noqa: BLE001
        return {"mode": "error", "error": redact_text(f"{type(exc).__name__}: {exc}"), "lobes": []}


def thinking(lobes, edges):
    """Strongest chain of firing paths -> caption."""
    by = {l["id"]: l for l in lobes}
    firing = sorted((e for e in edges if e["strength"] >= ACTIVE), key=lambda e: -e["strength"])
    if not firing:
        calm = [l for l in lobes if l["activity"] is not None]
        if not calm:
            return {"path": [], "text": "No data yet - set a FRED key (menu [M]) and let the first scan finish.",
                    "strength": 0.0}
        return {"path": [], "text": "Quiet. No transmission path is firing; every region is inside its usual range.",
                "strength": 0.0}
    best = firing[0]
    path = [best["src"], best["dst"]]
    used = {(best["src"], best["dst"])}
    for _ in range(4):   # extend forward along the strongest firing continuation
        nxt = [e for e in firing if e["src"] == path[-1] and e["dst"] not in path and (e["src"], e["dst"]) not in used]
        if not nxt:
            break
        used.add((nxt[0]["src"], nxt[0]["dst"])); path.append(nxt[0]["dst"])
    for _ in range(4):   # and backward
        prv = [e for e in firing if e["dst"] == path[0] and e["src"] not in path]
        if not prv:
            break
        path.insert(0, prv[0]["src"])
    words = " -> ".join(by[p]["region"] for p in path)
    hot = max((l for l in lobes if l["activity"] is not None), key=lambda l: l["activity"])
    mood = "under stress" if (hot["stress"] or 0) > 0 else "easing"
    return {"path": path, "strength": best["strength"],
            "text": f"{words}.  Loudest region: {hot['region']} ({hot['name']}), {mood}."}


# --------------------------------------------------------------- dev gate ----
def _keyring():
    try:
        import keyring
        from keyring.backends import fail
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring
    except Exception:  # noqa: BLE001
        return None


def _gate_file():
    return Path(os.environ.get("HANNIBAL_VAULT_DIR") or (Path.home() / ".hannibal")) / "dev_gate.json"


def _hash(key, salt):
    return hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, PBKDF2_ROUNDS)


def _load_record():
    kr = _keyring()
    raw = ""
    if kr is not None:
        try:
            raw = kr.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
        except Exception:  # noqa: BLE001
            raw = ""
    if not raw:
        try:
            raw = _gate_file().read_text(encoding="utf-8")
        except OSError:
            raw = ""
    try:
        rec = json.loads(raw) if raw else {}
        return rec if {"salt", "hash"} <= set(rec) else {}
    except ValueError:
        return {}


def has_dev_key():
    return bool(_load_record())


def set_dev_key(key):
    """Store only a salted PBKDF2 hash. Returns where it went."""
    if len(key) < 8:
        raise ValueError("use at least 8 characters")
    salt = secrets.token_bytes(16)
    rec = json.dumps({"salt": base64.b64encode(salt).decode(), "hash": base64.b64encode(_hash(key, salt)).decode(),
                      "rounds": PBKDF2_ROUNDS})
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(KEYRING_SERVICE, KEYRING_USER, rec)
            if kr.get_password(KEYRING_SERVICE, KEYRING_USER) == rec:
                return "your operating system's credential store"
        except Exception:  # noqa: BLE001
            pass
    path = _gate_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(rec)
    return f"{path} (hash only, owner-only file)"


_gate = {"fails": 0, "locked_until": 0.0}


def _log_attempt(kind, detail=""):
    try:
        import hannibal_geoint
        hannibal_geoint.record_attempt("127.0.0.1", kind, detail=detail, source="brain")
    except Exception:  # noqa: BLE001 - the gate works even if the breach log can't be written
        pass


def verify_dev_key(key, clock=time.time):
    """True if `key` matches. Enforces the lockout; records failures in the breach log."""
    now = clock()
    if now < _gate["locked_until"]:
        return False
    rec = _load_record()
    if not rec or not key:
        return False
    salt = base64.b64decode(rec["salt"])
    ok = hmac.compare_digest(_hash(key, salt), base64.b64decode(rec["hash"]))
    if ok:
        _gate["fails"] = 0
        return True
    _gate["fails"] += 1
    _log_attempt("dev_gate_fail", f"wrong developer key ({_gate['fails']}/{LOCKOUT_AFTER})")
    if _gate["fails"] >= LOCKOUT_AFTER:
        _gate["locked_until"] = now + LOCKOUT_SECONDS
        _gate["fails"] = 0
        _log_attempt("dev_gate_lockout", f"{LOCKOUT_SECONDS} s lockout")
    return False


def locked_for(clock=time.time):
    return max(0, int(_gate["locked_until"] - clock()))


# ----------------------------------------------------------------- server ----
class _State:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = None
        self.at = 0.0
        self.busy = False
        self.launch_codes = {}   # code -> expiry
        self.sessions = {}       # token -> expiry

    def get(self):
        with self.lock:
            fresh = self.state is not None and time.time() - self.at < REFRESH_SECONDS
            if fresh or self.busy:
                return self.state
            self.busy = True
        try:
            st = compute_state()
        except Exception as exc:  # noqa: BLE001
            st = {"error": redact_text(f"{type(exc).__name__}: {exc}"), "lobes": [], "edges": [],
                  "thinking": {"text": "The brain could not read its inputs.", "path": []}}
        with self.lock:
            self.state, self.at, self.busy = st, time.time(), False
        return st


_S = _State()
_server = {"httpd": None, "port": None}

PAGE_FILE = "hannibal_brain.html"


def _page_template():
    here = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return (here / PAGE_FILE).read_text(encoding="utf-8")


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "Hannibal"
    sys_version = ""

    def _allowed_host(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
        return host in ("localhost", "127.0.0.1", "[::1]")

    def _send(self, status, body, ctype, nonce="", extra=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        csp = ("default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; "
               "connect-src 'self'; img-src 'self' data:; ")
        csp += f"script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'" if nonce else "script-src 'none'; style-src 'none'"
        self.send_header("Content-Security-Policy", csp)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _session_ok(self):
        cookie = self.headers.get("Cookie") or ""
        token = ""
        for part in cookie.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "hb_session":
                token = v
        now = time.time()
        with _S.lock:
            for t, exp in list(_S.sessions.items()):
                if exp < now:
                    del _S.sessions[t]
            return any(hmac.compare_digest(token, t) for t in _S.sessions) if token else False

    def _deny(self, status, kind, detail=""):
        _log_attempt_ip(self.client_address[0], kind, detail)
        self._send(status, "Forbidden" if status == 403 else "Not found", "text/plain; charset=utf-8")

    def do_GET(self):
        if not self._allowed_host():
            return self._deny(403, "bad_host", self.headers.get("Host", ""))
        url = urlparse(self.path)
        if url.path == "/":
            code = (parse_qs(url.query).get("code") or [""])[0]
            now = time.time()
            with _S.lock:
                exp = next((e for c, e in _S.launch_codes.items() if hmac.compare_digest(c, code)), None) if code else None
                if exp is not None:
                    _S.launch_codes.pop(code, None)   # single use
            if exp is None or exp < now:
                return self._deny(403, "brain_bad_launch_code", "missing, used or expired launch code")
            token = secrets.token_urlsafe(32)
            with _S.lock:
                _S.sessions[token] = now + SESSION_SECONDS
            return self._send(303, "", "text/plain; charset=utf-8", extra={
                "Location": "/brain",
                "Set-Cookie": f"hb_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}"})
        if url.path not in ("/brain", "/state.json"):
            return self._deny(404, "unknown_route", url.path[:80])
        if not self._session_ok():
            return self._deny(403, "brain_no_session", url.path)
        if url.path == "/state.json":
            return self._send(200, json.dumps(_S.get()), "application/json; charset=utf-8")
        nonce = secrets.token_urlsafe(16)
        page = _page_template().replace("{{NONCE}}", nonce)
        return self._send(200, page, "text/html; charset=utf-8", nonce=nonce)

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):  # nothing here accepts writes
        self._deny(405 if self._allowed_host() else 403, "brain_post", self.path[:80])

    def log_message(self, fmt, *args):  # quiet and secret-free
        pass


def _log_attempt_ip(ip, kind, detail=""):
    try:
        import hannibal_geoint
        hannibal_geoint.record_attempt(ip, kind, detail=redact_text(detail), source="brain")
    except Exception:  # noqa: BLE001
        pass


def ensure_server():
    """Start (once) on 127.0.0.1 with an OS-chosen port. Returns the port."""
    if _server["httpd"] is None:
        httpd = http.server.ThreadingHTTPServer((HOST, 0), _Handler)
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, name="hannibal-brain", daemon=True).start()
        _server["httpd"], _server["port"] = httpd, httpd.server_address[1]
        threading.Thread(target=_S.get, daemon=True).start()   # warm the state in the background
    return _server["port"]


def stop_server():
    if _server["httpd"] is not None:
        _server["httpd"].shutdown()
        _server["httpd"].server_close()
        _server["httpd"], _server["port"] = None, None


def launch_url():
    """A fresh single-use URL that logs the browser in. Only call after the dev gate."""
    port = ensure_server()
    code = secrets.token_urlsafe(24)
    with _S.lock:
        _S.launch_codes[code] = time.time() + LAUNCH_CODE_SECONDS
    return f"http://{HOST}:{port}/?code={code}"


# ------------------------------------------------------------------- gate ----
def dev_gate(ask_secret=getpass.getpass, out=print):
    """Ask for the developer key. True if it matches."""
    if not has_dev_key():
        out("  No developer key set. Set one first:  python hannibal_brain.py --set-dev-key")
        return False
    wait = locked_for()
    if wait:
        out(f"  Locked after repeated wrong keys. Try again in {wait} s.")
        return False
    if verify_dev_key(ask_secret("  Developer key (hidden): ")):
        return True
    wait = locked_for()
    out(f"  Wrong key. Locked for {wait} s." if wait else "  Wrong key.")
    return False


def screen_brain(ask, out, color):
    """[R] in the orbital menu."""
    import hannibal_art as art
    out(art.section("MARKET BRAIN  //  DEVELOPERS ONLY", 89, color))
    if not dev_gate(out=out):
        return
    url = launch_url()
    out("  Gate passed. Opening the brain in your browser (local only, single-use link, 2 h session).")
    out(art.paint("  First load computes ~20 FRED series; they are cached for 6 h after that.", art.GRAY, enabled=color))
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        out("  Could not open a browser. Run python hannibal_brain.py and use the link it prints.")


# -------------------------------------------------------------------- CLI ----
def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    arg = argv[0] if argv else ""
    if arg == "--set-dev-key":
        if has_dev_key() and not dev_gate():
            print("[-] Enter the current developer key to change it.")
            return 1
        k1 = getpass.getpass("New developer key (hidden, 8+ characters): ")
        k2 = getpass.getpass("Repeat: ")
        if k1 != k2:
            print("[-] The two entries differ. Nothing changed.")
            return 1
        try:
            print(f"[+] Stored a hash of it in {set_dev_key(k1)}.")
        except ValueError as exc:
            print(f"[-] {exc}")
            return 1
        return 0
    if arg == "--check":
        print(f"[{'+' if has_dev_key() else '-'}] Developer key {'set' if has_dev_key() else 'NOT set'}")
        try:
            import hannibal_fred
            print(f"[{'+' if hannibal_fred.get_key() else '-'}] FRED key "
                  f"{'from ' + hannibal_fred.key_source() if hannibal_fred.get_key() else 'NOT set (python hannibal_fred.py --set-key)'}")
        except ImportError:
            print("[-] hannibal_fred.py not found next to this file")
        return 0
    if arg in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        import hannibal_security_bootstrap  # noqa: F401  (masked stdout)
    except ImportError:
        pass
    if not dev_gate():
        return 1
    if arg == "--export":
        target = Path(argv[1] if len(argv) > 1 else "market_brain_state.json")
        target.write_text(json.dumps(compute_state(), indent=2), encoding="utf-8")
        print(f"[+] Wrote {target}")
        return 0
    url = launch_url()
    print("[+] Market brain is running on 127.0.0.1 (local only). Opening your browser...")
    print("    If it does not open, paste this single-use link within 60 s:")
    print(f"    {url}")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_server()
        print("\n[+] Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
