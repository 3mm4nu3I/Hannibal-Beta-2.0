"""Shared HTTP layer for every Hannibal API client (Space-Track, JPL, SatNOGS-style feeds).

Everything that talks to the network in the orbital modules goes through here, so
the same guarantees hold everywhere:

  * MASKING    URLs, parameters, headers and exception text are passed through
               secret_masking before they can reach a log, a screen or the cache.
               Cached payloads are redacted too. Credentials are never part of a
               cache key and never written to disk.
  * CACHING    JSON responses are cached on disk with a per-call TTL (and served
               stale if the live call fails). Space-Track *requires* this: its policy
               is 1 GP pull per hour, 1 SATCAT/DECAY pull per day.
  * THROTTLING per-host token windows (Space-Track: <30/min and <300/h).
  * RETRIES    429 / 5xx / connection errors, honouring Retry-After (capped).

Importing this module has no side effects and never touches the network.
"""
import hashlib
import json
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlparse

try:
    from secret_masking import redact, redact_text
except ImportError:  # pragma: no cover - degrade to pass-through rather than crash
    def redact_text(value):
        return str(value)

    def redact(value):
        return value

FROZEN = getattr(sys, "frozen", False)
USER_AGENT = "Hannibal-Orbital/3.0 (+personal OSINT terminal)"
CACHE_DIRNAME = "hannibal_cache"

# Ground truth from the providers' own published policies.
HOST_LIMITS = {
    "www.space-track.org": {"per_minute": 25, "per_hour": 250, "min_interval": 1.0},  # policy: <30/min, <300/h
    "ssd.jpl.nasa.gov": {"min_interval": 1.0},
    "ssd-api.jpl.nasa.gov": {"min_interval": 1.0},
    "network.satnogs.org": {"min_interval": 0.3},
    "api.satellitemap.space": {"min_interval": 2.0},   # feed docs: accepts updates every >=2 s
    "api.n2yo.com": {"min_interval": 0.5, "per_hour": 900},  # docs: 1000/h (tle, positions), 100/h (passes, above)
    "ipapi.co": {"min_interval": 1.0, "per_hour": 500},
    "api.stlouisfed.org": {"min_interval": 0.6, "per_minute": 100},   # FRED: 120 requests/minute per key       # free tier: keep well under the documented 1000/day
}


# ---------------------------------------------------------------- paths ----
def base_dir():
    """Folder for user-editable files: next to the .exe when frozen, else next to the scripts."""
    if FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(name):
    """Find a file in the user folder first, then in PyInstaller's bundle."""
    for folder in (base_dir(), Path(getattr(sys, "_MEIPASS", base_dir()))):
        candidate = folder / name
        if candidate.exists():
            return candidate
    return base_dir() / name


def home_location():
    """Observer location used by the sky / pass features. Override with env vars."""
    def _f(name, default):
        try:
            return float(os.getenv(name, default))
        except ValueError:
            return float(default)
    # No real coordinates in source: this file travels with the repository.
    # Set HANNIBAL_HOME_LAT / _LON / _NAME for the sky and pass features.
    return {"lat": _f("HANNIBAL_HOME_LAT", 0.0), "lon": _f("HANNIBAL_HOME_LON", 0.0),
            "alt_km": _f("HANNIBAL_HOME_ALT_KM", 0.1), "name": os.getenv("HANNIBAL_HOME_NAME", "Home Station")}


def mask_id(value, keep=4):
    """Show only the tail of an identifier (feeder ids etc.)."""
    value = str(value or "")
    return value if len(value) <= keep else "*" * (len(value) - keep) + value[-keep:]


# --------------------------------------------------------------- results ----
@dataclass
class Result:
    data: object = None
    error: str = ""
    cached: bool = False     # served from the disk cache without a live call
    stale: bool = False      # live call failed; an expired cached copy was served instead
    age: float = 0.0         # seconds since the data was fetched (0 for live)
    note: str = ""

    @property
    def ok(self):
        return not self.error and self.data is not None


def describe_age(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 172800:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


class RateLimitExceeded(Exception):
    pass


class RateLimiter:
    """Sliding-window limiter: min spacing between calls plus per-minute / per-hour caps.

    Short waits (<= max_wait seconds) are slept through; longer ones raise
    RateLimitExceeded so a UI thread never blocks for an hour.
    """

    def __init__(self, per_minute=None, per_hour=None, min_interval=0.0, clock=time.monotonic, sleep=time.sleep):
        self.per_minute, self.per_hour, self.min_interval = per_minute, per_hour, min_interval
        self._clock, self._sleep = clock, sleep
        self._calls = deque()
        self._last = None
        self._lock = threading.Lock()

    def _delay(self, now):
        delay = 0.0
        if self._last is not None:
            delay = max(delay, self.min_interval - (now - self._last))
        for limit, window in ((self.per_minute, 60.0), (self.per_hour, 3600.0)):
            if limit:
                recent = [t for t in self._calls if now - t < window]
                if len(recent) >= limit:
                    delay = max(delay, window - (now - recent[0]) + 0.05)
        return delay

    def acquire(self, max_wait=60.0):
        with self._lock:
            while True:
                now = self._clock()
                while self._calls and now - self._calls[0] >= 3600.0:
                    self._calls.popleft()
                delay = self._delay(now)
                if delay <= 1e-6:   # float noise must not turn into a zero-length sleep loop
                    self._calls.append(now)
                    self._last = now
                    return
                if delay > max_wait:
                    raise RateLimitExceeded(f"rate limit reached; next call allowed in {int(delay)} s")
                self._sleep(delay)


# ------------------------------------------------------------------- Net ----
class Net:
    def __init__(self, cache_dir=None, session_factory=None, clock=time.time, sleep=time.sleep,
                 limiter_clock=time.monotonic):
        self.cache_dir = Path(cache_dir) if cache_dir else base_dir() / CACHE_DIRNAME
        self._session_factory = session_factory
        self._session = None
        self._limiters = {}
        self._clock, self._sleep, self._limiter_clock = clock, sleep, limiter_clock
        self._lock = threading.Lock()

    # -- plumbing ---------------------------------------------------------
    def session(self):
        with self._lock:
            if self._session is None:
                if self._session_factory:
                    self._session = self._session_factory()
                else:
                    import requests  # lazy: importing this module can never fail
                    self._session = requests.Session()
                    self._session.headers.update({"User-Agent": USER_AGENT})
            return self._session

    def limiter(self, host):
        with self._lock:
            if host not in self._limiters:
                self._limiters[host] = RateLimiter(clock=self._limiter_clock, sleep=self._sleep, **HOST_LIMITS.get(host, {"min_interval": 0.2}))
            return self._limiters[host]

    @staticmethod
    def safe_url(url, params=None):
        """The only form of a URL that may be printed or logged.

        Each query pair is redacted on its own, so one secret parameter does not swallow the
        harmless ones after it (the shared redaction patterns would otherwise mask to end of line).
        """
        base, _, query = url.partition("?")
        pairs = [p for p in query.split("&") if p]
        if params:
            pairs += [p for p in urlencode(params, doseq=True).split("&") if p]
        masked = [redact_text(p) for p in pairs]
        return redact_text(base) + ("?" + "&".join(masked) if masked else "")

    # -- cache ------------------------------------------------------------
    def _key(self, method, url, params, explicit):
        material = explicit or json.dumps([method, url, sorted((params or {}).items())], default=str)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]

    def _cache_read(self, key):
        try:
            with open(self.cache_dir / f"{key}.json", "r", encoding="utf-8") as fh:
                blob = json.load(fh)
            return blob["data"], max(0.0, self._clock() - float(blob["t"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None, None

    def _cache_write(self, key, data):
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_dir / f"{key}.json.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"t": self._clock(), "data": redact(data)}, fh)
            os.replace(tmp, self.cache_dir / f"{key}.json")
        except (OSError, TypeError, ValueError):
            pass  # a cache that cannot be written must never break a request

    def clear_cache(self):
        n = 0
        for f in self.cache_dir.glob("*.json") if self.cache_dir.exists() else []:
            try:
                f.unlink(); n += 1
            except OSError:
                pass
        return n

    # -- requests ---------------------------------------------------------
    def request(self, method, url, *, params=None, data=None, headers=None, ttl=0, cache_key=None,
                expect="json", timeout=20, retries=2, stale_ok=True, session=None, max_wait=60.0,
                validate=None):
        """Perform a request. Never raises: failures come back as Result(error=...).

        validate(payload) -> error string ('' if fine): lets an API that reports errors inside a
        200 response (N2YO, Horizons) be treated as a failure and never cached.
        """
        if os.getenv("HANNIBAL_NET_PROFILE", "normal").strip().lower() == "low":
            # Low-internet launcher (patch_telemetry 1.2.0): patient timeouts, one more retry,
            # and cached answers reused 4x longer so fewer downloads happen at all.
            if isinstance(timeout, (int, float)):
                timeout = (20, max(60, timeout))
            retries = max(retries, 3)
            ttl = ttl * 4
        key = self._key(method, url, params, cache_key) if (ttl or stale_ok) else None
        if ttl and key:
            cached, age = self._cache_read(key)
            if cached is not None and age < ttl:
                return Result(cached, cached=True, age=age)

        host = urlparse(url).hostname or ""
        error = ""
        try:
            self.limiter(host).acquire(max_wait=max_wait)
        except RateLimitExceeded as exc:
            error = str(exc)
        else:
            try:
                sess = session or self.session()
            except Exception as exc:  # e.g. the requests package is not installed
                sess = None
                error = redact_text(f"{type(exc).__name__}: {exc}") + " (pip install requests)"
            for attempt in range(retries + 1 if sess is not None else 0):
                try:
                    res = sess.request(method, url, params=params, data=data, headers=headers, timeout=timeout)
                    if res.status_code in (429, 503) and attempt < retries:
                        try:
                            wait = min(float(res.headers.get("Retry-After", 2 * (attempt + 1))), 20.0)
                        except (TypeError, ValueError):
                            wait = 2.0
                        self._sleep(wait)
                        continue
                    if res.status_code >= 400:
                        error = f"HTTP {res.status_code} from {urlparse(url).hostname}"
                        break
                    payload = res.json() if expect == "json" else res.text
                    if validate:
                        problem = validate(payload)
                        if problem:
                            error = redact_text(problem)
                            break
                    if key and ttl:
                        self._cache_write(key, payload)
                    return Result(payload)
                except ValueError:
                    error = f"{urlparse(url).hostname} returned something that is not JSON"
                    break
                except Exception as exc:  # requests.RequestException and friends
                    error = redact_text(f"{type(exc).__name__}: {exc}")
                    if attempt < retries:
                        self._sleep(1.0 + attempt)
                        continue
                    break

        if stale_ok and key:
            cached, age = self._cache_read(key)
            if cached is not None:
                return Result(cached, stale=True, age=age,
                              note=f"live fetch failed ({error}); showing cached copy from {describe_age(age)}")
        return Result(None, error=error or "request failed")

    def peek(self, method, url, *, params=None, ttl=0, cache_key=None):
        """Cache-only lookup. Returns a Result if a copy younger than `ttl` exists, else None.
        ttl=float('inf') accepts a copy of any age (used to fall back to stale data)."""
        cached, age = self._cache_read(self._key(method, url, params, cache_key))
        if cached is not None and age < ttl:
            return Result(cached, cached=True, age=age)
        return None

    def get_json(self, url, **kw):
        return self.request("GET", url, **kw)


_default_net = None


def default_net():
    global _default_net
    if _default_net is None:
        _default_net = Net()
    return _default_net
