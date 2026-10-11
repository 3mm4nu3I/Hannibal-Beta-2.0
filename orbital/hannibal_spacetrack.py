"""Space-Track client (https://www.space-track.org/documentation#api).

Built around the documented policy, which is what keeps an account alive:
  * stay under 30 requests/minute and 300/hour        -> limiter in hannibal_net (25 / 250)
  * GP (TLEs) at most 1 pull per hour                  -> 1 h cache
  * SATCAT / DECAY / BOXSCORE at most 1 per day        -> 24 h cache
  * CDM at most 3 per day                              -> 8 h cache
  * "do not send hundreds of individual queries"       -> comma-separated NORAD id lists
Cached copies are served first; the client only logs in on a cache miss, and falls
back to an expired copy if the live call fails.

Credentials: SPACETRACK_USER / SPACETRACK_PASS environment variables first, then the
space_track_auth block of norad_targets.json (placeholders ignored). They are only
ever sent in the login POST body and are never logged, cached or put in a URL.
"""
import json
import os
import re
from urllib.parse import quote

from hannibal_net import Net, Result, default_net, resource_path, redact_text

BASE = "https://www.space-track.org"
LOGIN_URLS = (BASE + "/auth/login",          # documented
              BASE + "/ajaxauth/login")      # long-standing legacy endpoint, same fields

# seconds -- never lower these below the documented pull frequency
CLASS_TTL = {
    "gp": 3600, "gp_history": 30 * 86400, "decay": 86400, "satcat": 86400, "satcat_debut": 86400,
    "boxscore": 86400, "cdm_public": 8 * 3600, "tip": 3600, "launch_site": 7 * 86400,
    "announcement": 86400,
}
_CLASS_RE = re.compile(r"^[a-z_]+$")
_PRED_RE = re.compile(r"^[A-Za-z_]+$")
CREDENTIALS_HELP = "press [K] in the menu to enter your login, or set SPACETRACK_USER / SPACETRACK_PASS (free account at space-track.org)"


def get_credentials(config=None):
    """env vars -> credentials typed at start-up (this process only) -> norad_targets.json."""
    user = os.getenv("SPACETRACK_USER", "").strip()
    pw = os.getenv("SPACETRACK_PASS", "")
    if user and pw:
        return user, pw
    try:
        from hannibal_creds import session_get
        user, pw = session_get("spacetrack_user"), session_get("spacetrack_pass")
        if user and pw:
            return user, pw
    except ImportError:
        pass
    auth = config
    if auth is None:
        try:
            with open(resource_path("norad_targets.json"), "r", encoding="utf-8") as fh:
                auth = json.load(fh).get("space_track_auth", {})
        except (OSError, ValueError, AttributeError):
            auth = {}
    user, pw = str((auth or {}).get("username", "")), str((auth or {}).get("password", ""))
    if user and pw and not user.startswith("YOUR_") and not pw.startswith("YOUR_"):
        return user, pw
    return "", ""


def build_url(cls, predicates=(), fmt="json"):
    """/basicspacedata/query/class/<cls>/<PRED>/<value>/.../format/<fmt>

    Class and predicate NAMES are validated; VALUES are percent-encoded, so nothing a caller
    passes can add path segments (no query injection).
    """
    if not _CLASS_RE.match(cls):
        raise ValueError(f"bad Space-Track class: {cls!r}")
    parts = [BASE, "basicspacedata", "query", "class", cls]
    for name, value in predicates:
        if not _PRED_RE.match(name):
            raise ValueError(f"bad predicate name: {name!r}")
        parts += [name, quote(str(value), safe=",<>^~-.:+=")]
    parts += ["format", fmt]
    return "/".join(parts)


class SpaceTrack:
    def __init__(self, net=None, user=None, password=None):
        self.net = net or default_net()
        if user is None:
            user, password = get_credentials()
        self._user, self._password = user, password
        self._logged_in = False

    @property
    def configured(self):
        return bool(self._user and self._password)

    # -- auth ---------------------------------------------------------------
    def login(self):
        """Returns an error string, or '' on success."""
        if not self.configured:
            return "no Space-Track credentials (" + CREDENTIALS_HELP + ")"
        last = ""
        for url in LOGIN_URLS:
            res = self.net.request("POST", url, data={"identity": self._user, "password": self._password},
                                   expect="text", stale_ok=False, retries=1)
            if res.error:
                last = res.error
                continue
            if "Failed" in str(res.data)[:300]:
                return "Space-Track login failed (check username/password)"
            self._logged_in = True
            return ""
        return last or "Space-Track login failed"

    # -- generic query ------------------------------------------------------
    def query(self, cls, predicates=(), ttl=None, force=False):
        ttl = CLASS_TTL.get(cls, 3600) if ttl is None else ttl
        url = build_url(cls, predicates)
        if not force:
            hit = self.net.peek("GET", url, ttl=ttl)
            if hit:
                return hit

        def _stale(reason):
            old = self.net.peek("GET", url, ttl=float("inf"))
            if old:
                old.cached, old.stale = False, True
                old.note = f"{reason}; showing cached copy"
                return old
            return Result(None, error=reason)

        if not self.configured:
            return _stale("no Space-Track credentials (" + CREDENTIALS_HELP + ")")
        if not self._logged_in:
            err = self.login()
            if err:
                return _stale(err)
        res = self.net.request("GET", url, ttl=ttl, expect="json", stale_ok=True)
        # an expired session comes back as HTTP 401 or an HTML login page (not JSON): log in once more
        if (res.error and ("401" in res.error or "not JSON" in res.error)) or res.stale:
            self._logged_in = False
            if not self.login():
                res = self.net.request("GET", url, ttl=ttl, expect="json", stale_ok=True)
        if res.ok and not isinstance(res.data, list):
            return Result(None, error="unexpected Space-Track response shape")
        return res

    # -- convenience --------------------------------------------------------
    def gp_epochs(self, norad_ids):
        """Latest TLE epoch per object. Returns (dict, error). One comma-list query, cached 1 h."""
        ids = ",".join(str(int(i)) for i in norad_ids)
        res = self.query("gp", [("NORAD_CAT_ID", ids), ("orderby", "EPOCH desc")])
        if not res.ok:
            return {}, res.error
        epochs = {}
        for row in res.data:
            try:
                epochs.setdefault(int(row["NORAD_CAT_ID"]), str(row["EPOCH"]))
            except (KeyError, TypeError, ValueError):
                continue
        return epochs, (res.note or None)

    def decay(self, limit=30):
        """Re-entry predictions from three days ago onward, soonest first."""
        return self.query("decay", [("DECAY_EPOCH", ">now-3"), ("orderby", "DECAY_EPOCH asc"), ("limit", limit)])

    def tip(self, limit=15):
        return self.query("tip", [("orderby", "MSG_EPOCH desc"), ("limit", limit)])

    def boxscore(self):
        return self.query("boxscore")

    def conjunctions(self, limit=10):
        return self.query("cdm_public", [("TCA", ">now"), ("orderby", "TCA asc"), ("limit", limit)])

    def satcat(self, norad_ids):
        ids = ",".join(str(int(i)) for i in norad_ids)
        return self.query("satcat", [("NORAD_CAT_ID", ids)])

    def launch_sites(self):
        return self.query("launch_site")
