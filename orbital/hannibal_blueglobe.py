"""Hannibal BlueGlobe dashboard server.

Serves the WebGL satellite dashboard to your own browser.

Security model (changed from the original, which used SimpleHTTPRequestHandler
on all interfaces and therefore published the WHOLE project folder -- including
norad_targets.json with Space-Track credentials, the intel database and logs):

  * binds to 127.0.0.1 only
  * serves an explicit allow-list of URLs, nothing else (one pattern route: /api/sat/<digits>.json)
  * rejects requests whose Host header isn't localhost (DNS-rebinding guard)

Usable two ways:
  python hannibal_blueglobe.py        standalone (prints banner, opens browser)
  import hannibal_blueglobe           the terminal's [B] key calls ensure_server()
  Routes: / (dashboard), /telemetry_report.json, /config.json,
  /api/{sky,decay,boxscore,status,above,moons,breach}.json, /api/sat/<norad>.json

  Requests that fail the Host-header guard or hit no known route are recorded by
  hannibal_geoint as probe/breach attempts (source IP + what they tried) -- see
  hannibal_geoint.py. Because this server only ever binds 127.0.0.1, that log is
  mostly useful if you proxy/forward this port from somewhere less trusted; it is
  the hook other front doors (a login form, an [U] dev page, etc.) can call into
  via hannibal_geoint.record_attempt(ip, kind, detail) directly.
"""
import http.server
import json
import os
import re
import sys
import threading
import time
import webbrowser
from urllib.parse import urlparse

try:
    from run_telemetry import base_dir, report_path, resource_path
except ImportError:  # standalone copy without the engine next to it
    from pathlib import Path

    def base_dir():
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

    def resource_path(name):
        return base_dir() / name

    def report_path():
        return base_dir() / "telemetry_report.json"

try:
    from secret_masking import redact_text
except ImportError:  # pragma: no cover
    def redact_text(value):
        return str(value)

# ANSI colour codes
RED_BG = "\033[41m"
YELLOW_FG = "\033[1;33m"
WHITE_FG = "\033[1;37m"
CYAN_FG = "\033[1;36m"
RESET = "\033[0m"

# Raw f-string: the art contains backslashes that are not escape sequences.
SOVIET_BANNER = rf"""
{RED_BG}{YELLOW_FG}================================================================================{RESET}
{RED_BG}{YELLOW_FG}   _____   _____   _____   _____     ____    ____  _     _ _____ _____ _____    {RESET}
{RED_BG}{YELLOW_FG}  /  ___| /  ___| /  ___| /  _  \   / ___|  / __ \| |   | | ____|_   _|  ___|   {RESET}
{RED_BG}{YELLOW_FG}  | |     | |     | |     | | | |  | |  _  | |  | | |   | |  _|   | | |  _|     {RESET}
{RED_BG}{YELLOW_FG}  | |___  | |___  | |___  | |_| |  | |_| | | |__| | |___| | |___  | | | |___    {RESET}
{RED_BG}{YELLOW_FG}  \_____| \_____| \_____| \_____/   \____|  \____/|_____|_____| |_| |_____|   {RESET}
{RED_BG}{YELLOW_FG}                                                                                {RESET}
{RED_BG}{YELLOW_FG}             .---.                     CCCP SATELLITE TRACKING NODE              {RESET}
{RED_BG}{YELLOW_FG}            / /"- \                    PROJECT HANNIBAL V7 INTEGRATION          {RESET}
{RED_BG}{YELLOW_FG}           / /   | |                   ORBITAL TRANSIT & METRICS SYSTEM        {RESET}
{RED_BG}{YELLOW_FG}          / /    | |                                                            {RESET}
{RED_BG}{YELLOW_FG}         / /    / /    /\__/\      ☭ WORKERS OF THE WORLD, UNITE! ☭            {RESET}
{RED_BG}{YELLOW_FG}        / /    / /    (  ''  )                                                  {RESET}
{RED_BG}{YELLOW_FG}       / /    / /      =(  )=                                                   {RESET}
{RED_BG}{YELLOW_FG}      / /    / /         /||\                                                   {RESET}
{RED_BG}{YELLOW_FG}================================================================================{RESET}
"""

HOST = "127.0.0.1"
PORTS = range(8080, 8091)
DASHBOARD = "blueglobe_dashboard.html"
# route -> hannibal_orbital provider function (read-only; no parameters are taken from the URL)
API_ROUTES = {
    "/api/sky.json": "get_sky",
    "/api/decay.json": "get_decay",
    "/api/boxscore.json": "get_boxscore",
    "/api/status.json": "get_status",
    "/api/above.json": "get_overhead",         # N2YO: Military + Globalstar above the home location
    "/api/moons.json": "get_moons",           # JPL sb_sat: every small body with satellites
    "/api/breach.json": "get_breach_log_api",  # local probe/breach log, IP-geolocated
}
# one satellite: /api/sat/<NORAD id>.json -- the id is validated (digits only, 1-9 long) and handed to a provider
SAT_ROUTE = re.compile(r"^/api/sat/([0-9]{1,9})\.json\Z")


def _config_payload():
    """Runtime config for the page. The API key is read from the environment so it
    is never hard-coded into the HTML."""
    def _float(name, default):
        try:
            return float(os.getenv(name, default))
        except ValueError:
            return float(default)

    # No real coordinates in source: this payload is served to the browser (127.0.0.1 only).
    # Same lookup as every terminal screen: env vars, then ~/.hannibal/home.json (--set-home).
    try:
        from hannibal_net import home_location
        h = home_location()
        home = {"lat": h["lat"], "lon": h["lon"], "name": h["name"], "set": h.get("set", True)}
    except Exception:  # never let the globe fail to start over its home marker
        home = {"lat": _float("HANNIBAL_HOME_LAT", 0.0), "lon": _float("HANNIBAL_HOME_LON", 0.0),
                "name": os.getenv("HANNIBAL_HOME_NAME", "Home Station")}
    return {
        "apiKey": os.getenv("BLUEGLOBE_API_KEY", "blueglobe-test"),
        "home": home,
    }


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    server_version = "HannibalGlobe/1.0"
    sys_version = ""

    def _allowed_host(self):
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("localhost", "127.0.0.1", "[::1]")

    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_file(self, path, ctype):
        try:
            self._send(200, path.read_bytes(), ctype)
        except OSError:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def _send_api(self, provider, *args):
        """Allow-listed data routes. Providers live in hannibal_orbital, are cached/throttled by
        hannibal_net and return plain dicts that never contain credentials."""
        try:
            import hannibal_orbital
            payload = getattr(hannibal_orbital, provider)(*args)
            body = json.dumps(payload, default=str).encode("utf-8")
            self._send(200, body, "application/json")
        except Exception as exc:  # a provider bug must not kill the server thread
            err = {"error": redact_text(f"{type(exc).__name__}: {exc}")}
            self._send(500, json.dumps(err).encode("utf-8"), "application/json")

    def _log_probe(self, kind, detail=""):
        try:
            import hannibal_geoint
            hannibal_geoint.record_attempt(self.client_address[0], kind, detail=detail, source="blueglobe")
        except Exception:
            pass  # a logging bug must never affect the response already being sent

    def do_GET(self):
        if not self._allowed_host():
            self._log_probe("bad_host", self.headers.get("Host", ""))
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return
        route = urlparse(self.path).path
        if route in ("/", "/" + DASHBOARD):
            self._serve_file(resource_path(DASHBOARD), "text/html; charset=utf-8")
        elif route == "/telemetry_report.json":
            path = report_path()
            if path.exists():
                self._serve_file(path, "application/json")
            else:  # no scan yet: an empty report makes the page fall back cleanly
                self._send(200, b"[]", "application/json")
        elif route == "/config.json":
            self._send(200, json.dumps(_config_payload()).encode("utf-8"), "application/json")
        elif route in API_ROUTES:
            self._send_api(API_ROUTES[route])
        elif SAT_ROUTE.match(route):
            self._send_api("get_satellite", int(SAT_ROUTE.match(route).group(1)))
        else:
            self._log_probe("unknown_route", route)
            self._send(404, b"not found", "text/plain; charset=utf-8")

    do_HEAD = do_GET

    def log_message(self, fmt, *args):  # keep the terminal quiet and secret-free
        pass


class _Server(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


_server = None
_server_port = None
_server_lock = threading.Lock()


def ensure_server():
    """Start the local server once (idempotent). Returns the dashboard URL.

    Binds synchronously, so the URL is valid the moment this returns. Raises
    OSError if no port in 8080-8090 is free.
    """
    global _server, _server_port
    with _server_lock:
        if _server is None:
            last_error = None
            for port in PORTS:
                try:
                    _server = _Server((HOST, port), DashboardHandler)
                    _server_port = port
                    break
                except OSError as exc:
                    last_error = exc
            if _server is None:
                raise OSError(f"could not bind any port in {PORTS.start}-{PORTS.stop - 1}: "
                              f"{redact_text(last_error)}")
            threading.Thread(target=_server.serve_forever, name="BlueGlobe-Server", daemon=True).start()
        return f"http://localhost:{_server_port}/{DASHBOARD}"


def stop_server():
    global _server, _server_port
    with _server_lock:
        if _server is not None:
            _server.shutdown()
            _server.server_close()
            _server = _server_port = None


def main():
    if os.name == "nt":
        os.system("")  # enable ANSI colours in the Windows console
    print(SOVIET_BANNER)
    print(f"{CYAN_FG}[*] Initiating Hannibal Telemetry & BlueGlobe WebGL Orbit Suite...{RESET}")
    try:
        url = ensure_server()
    except OSError as exc:
        print(f"\n[!] ERROR: {exc}")
        return 1
    print(f"\n[+] Local server operational at {url}  (localhost only)")
    print(f"{WHITE_FG}[*] Launching browser interface...{RESET}")
    webbrowser.open(url)
    print(f"\n{YELLOW_FG}[!] Press CTRL+C to terminate node server.{RESET}\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{RED_BG}{WHITE_FG}[*] Shutting down Soviet Tracking Node. Dosvidaniya!{RESET}")
        stop_server()
        return 0


if __name__ == "__main__":
    sys.exit(main())
