"""Breach/probe log, IP geolocation and offline phone-number metadata.

Scope, deliberately:
  * Any inbound request that looks like a probe or breach attempt (bad Host header,
    unknown route, failed login, whatever a caller flags) gets appended to a local,
    append-only compliance log -- timestamp, source IP, what it tried.
  * IP geolocation resolves that source IP to country/region/city/ISP for an incident
    write-up. Uses a free, keyless provider (ipapi.co), cached hard (IP geography
    barely changes) and routed through hannibal_net so it gets the same masking,
    throttling and offline-degrade guarantees as every other API call here.
  * Phone-number lookups are metadata only -- country, registered number range,
    carrier, line type (mobile / VOIP / landline / toll-free) -- parsed locally from
    the number itself via the `phonenumbers` library. No network call, no live
    location: a number range's registered region is not where a handset is right now.

What this module does NOT do, on purpose: it does not resolve a phone number to a
live or approximate location. That requires a carrier's own lawful-intercept
process; it is not something a local script can provide regardless of what calls
it, so there is no code path here for it.
"""
import ipaddress
import json
import os
import threading
import time
from datetime import datetime, timezone as _tz
from pathlib import Path

from hannibal_net import base_dir, default_net, redact_text

NOT_LOGGED = ("not in the breach log -- log it first (menu [I] -> [M], or let the server record "
              "an actual probe) before it can be looked up here")

GEO_URL = "https://ipapi.co/{ip}/json/"
GEO_TTL = 7 * 86400            # IP geolocation is coarse and stable; refetch weekly at most
LOG_FILENAME = "hannibal_breach_log.jsonl"
MAX_LOG_ENTRIES = 2000         # oldest trimmed first -- this is a rolling compliance log, not forever storage
COALESCE_SECONDS = 60          # repeats of the same (ip, kind) within this window bump a counter instead of
                                # writing a new line, so one noisy prober can't flood the file

_file_lock = threading.Lock()
_recent_lock = threading.Lock()
_recent = {}   # (ip, kind) -> {"t": monotonic time of last write, "n": count since that line was written}


# ------------------------------------------------------------------- log file ----
def log_path():
    return Path(base_dir()) / LOG_FILENAME


def _iso_now():
    return datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_lines():
    try:
        with open(log_path(), "r", encoding="utf-8") as fh:
            return [ln for ln in fh.read().splitlines() if ln.strip()]
    except OSError:
        return []


def _write_lines(lines):
    """Write the log, then drop it to read-only (0o400 / the Windows read-only attribute) so a
    stray edit outside this module needs a deliberate permission change first. This deters casual
    or accidental tampering with the compliance record; it is not a defence against a user (or
    process) with full control of the machine, and that limit should stay visible rather than
    implied as stronger than it is."""
    path = log_path()
    try:
        if path.exists():
            try:
                path.chmod(0o600)   # must be writable before os.replace() can land on it, notably on Windows
            except OSError:
                pass
        tmp = path.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + ("\n" if lines else ""))
        os.replace(tmp, path)
        try:
            path.chmod(0o400)
        except OSError:
            pass
    except OSError:
        pass  # a log that cannot be written must never break the caller (server thread, menu screen, ...)


def _append(entry):
    with _file_lock:
        lines = _read_lines()
        lines.append(json.dumps(entry, default=str))
        if len(lines) > MAX_LOG_ENTRIES:
            lines = lines[-MAX_LOG_ENTRIES:]
        _write_lines(lines)


def _bump_last_line(ip, phone, kind, count):
    """If the most recent line is the same (ip, phone, kind), update its count+timestamp in place
    instead of appending a new one. Best-effort coalescing, not a general search."""
    with _file_lock:
        lines = _read_lines()
        if not lines:
            return False
        try:
            last = json.loads(lines[-1])
        except ValueError:
            return False
        if last.get("ip") != ip or last.get("phone", "") != phone or last.get("kind") != kind:
            return False
        last["count"] = count
        last["ts"] = _iso_now()
        lines[-1] = json.dumps(last, default=str)
        _write_lines(lines)
        return True


def record_attempt(ip="", kind="unknown", detail="", source="blueglobe", phone=""):
    """Append one breach/probe record (IP and/or a phone number involved in it). Never raises --
    a logging bug must never break whatever triggered it (a malformed request, a bad login, a
    suspicious call/SMS someone is writing down, ...).

    This is the ONLY way an IP or phone number enters the log, and lookup_ip() / phone_metadata()
    refuse to resolve anything that isn't in it -- see NOT_LOGGED above. So logging an attempt
    here, by hand or automatically, is also what authorises looking it up afterwards."""
    ip = str(ip or "").strip()
    phone = str(phone or "").strip()
    kind = str(kind or "unknown").strip()[:60]
    key = (ip, phone, kind)
    now = time.monotonic()
    with _recent_lock:
        last = _recent.get(key)
        if last is not None and now - last["t"] < COALESCE_SECONDS:
            last["t"] = now
            last["n"] += 1
            n = last["n"]
            bumped = True
        else:
            _recent[key] = {"t": now, "n": 1}
            n = 1
            bumped = False
    try:
        if bumped and _bump_last_line(ip, phone, kind, n):
            return
        _append({"ts": _iso_now(), "ip": ip, "phone": phone, "kind": kind,
                  "detail": redact_text(str(detail))[:200], "source": str(source)[:40], "count": n})
    except Exception:
        pass  # logging must never raise into the caller


def log_count():
    return len(_read_lines())


def clear_log():
    """Used by tests / an explicit reset. Not wired to any menu key -- this is a
    compliance record and should not be casually wiped from inside the app."""
    with _file_lock:
        _write_lines([])
    with _recent_lock:
        _recent.clear()


def _logged_values():
    """(ip set, e164-normalised phone set) seen anywhere in the log. Used to gate lookups so this
    module can only ever resolve something that actually showed up as a probe/breach -- never an
    arbitrary address or number handed to it."""
    ips, phones = set(), set()
    for ln in _read_lines():
        try:
            entry = json.loads(ln)
        except ValueError:
            continue
        if entry.get("ip"):
            ips.add(entry["ip"])
        if entry.get("phone"):
            phones.add(_normalize_phone(entry["phone"]))
    return ips, phones


def is_logged_ip(ip):
    return bool(str(ip or "").strip()) and str(ip).strip() in _logged_values()[0]


def is_logged_phone(number):
    norm = _normalize_phone(number)
    return bool(norm) and norm in _logged_values()[1]


# ------------------------------------------------------------------- IP geoint ----
def _is_lookupable(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified)


def _empty_geo(ip, error="", note=""):
    return {"ip": ip, "error": error, "note": note, "country": "", "country_code": "", "region": "",
             "city": "", "isp": "", "asn": "", "lat": None, "lon": None, "timezone": "",
             "cached": False, "stale": False, "age": 0.0}


def _geo_validate(payload):
    if isinstance(payload, dict) and payload.get("error"):
        return str(payload.get("reason") or "lookup failed")
    return ""


def lookup_ip(ip, net=None, require_logged=True):
    """Country/region/city/ISP for a public IP. Private/loopback/reserved addresses are
    recognised locally and never sent anywhere. Cached for GEO_TTL since geography for a
    given IP rarely changes, so repeated hits from the same prober cost one live call.

    require_logged=True (the default, and what every interactive/menu/dashboard caller uses)
    refuses anything that isn't already in the breach log -- see record_attempt(). Internal
    callers that are themselves iterating the log (get_breach_log) pass False to skip the
    redundant check."""
    ip = str(ip or "").strip()
    if not ip:
        return _empty_geo(ip, error="no IP given")
    if require_logged and not is_logged_ip(ip):
        return _empty_geo(ip, error=NOT_LOGGED)
    if not _is_lookupable(ip):
        return _empty_geo(ip, note="private / loopback / reserved address -- not looked up")
    net = net or default_net()
    res = net.request("GET", GEO_URL.format(ip=ip), ttl=GEO_TTL, validate=_geo_validate, timeout=10)
    if not res.ok:
        return _empty_geo(ip, error=res.error)
    d = res.data if isinstance(res.data, dict) else {}
    return {
        "ip": ip, "error": "", "note": "",
        "country": d.get("country_name") or "", "country_code": d.get("country_code") or "",
        "region": d.get("region") or "", "city": d.get("city") or "",
        "isp": d.get("org") or "", "asn": d.get("asn") or "",
        "lat": d.get("latitude"), "lon": d.get("longitude"), "timezone": d.get("timezone") or "",
        "cached": res.cached, "stale": res.stale, "age": res.age,
    }


def get_breach_log(limit=50, resolve=True, net=None):
    """Most recent entries first, each optionally enriched with its IP's geolocation and/or
    its phone number's metadata. require_logged is skipped here (False) since every value
    iterated is, by construction, already a line in this same log."""
    lines = _read_lines()
    entries = []
    for ln in reversed(lines[-limit:]):
        try:
            entry = json.loads(ln)
        except ValueError:
            continue
        if resolve and entry.get("ip"):
            entry["geo"] = lookup_ip(entry["ip"], net=net, require_logged=False)
        if resolve and entry.get("phone"):
            entry["phone_meta"] = phone_metadata(entry["phone"], require_logged=False)
        entries.append(entry)
    return entries


# --------------------------------------------------------------- phone metadata ----
_LINE_TYPE_NAMES = None  # built lazily -- importing phonenumbers only when first needed


def _line_type_names():
    global _LINE_TYPE_NAMES
    if _LINE_TYPE_NAMES is None:
        import phonenumbers
        t = phonenumbers.PhoneNumberType
        _LINE_TYPE_NAMES = {
            t.MOBILE: "mobile", t.FIXED_LINE: "fixed line", t.FIXED_LINE_OR_MOBILE: "fixed line or mobile",
            t.VOIP: "VOIP", t.TOLL_FREE: "toll-free", t.PREMIUM_RATE: "premium rate",
            t.SHARED_COST: "shared cost", t.PERSONAL_NUMBER: "personal number", t.PAGER: "pager",
            t.UAN: "UAN", t.VOICEMAIL: "voicemail", t.UNKNOWN: "unknown",
        }
    return _LINE_TYPE_NAMES


def _normalize_phone(raw, default_region="PT"):
    """Best-effort E.164 form, used only to compare 'is this number already in the log' across
    formatting differences (spaces, dashes, a leading 00 vs +). Falls back to the digits as
    typed if the library can't parse it, so an unusual but exactly-matching entry still matches."""
    raw = str(raw or "").strip()
    if not raw:
        return ""
    try:
        import phonenumbers
        n = phonenumbers.parse(raw, default_region)
        return phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        return raw


def phone_metadata(raw, default_region="PT", require_logged=True):
    """Offline metadata for a phone number: country, the registered number range's area,
    carrier and line type. This is NOT a location lookup -- it says what kind of number
    it is and where it was issued, never where the handset is right now.

    require_logged=True (the default, and what every interactive/menu caller uses) refuses
    any number that isn't already in the breach log -- see record_attempt()."""
    raw = str(raw or "").strip()
    empty = {"number": raw, "error": "", "e164": "", "valid": False, "country_code": None,
             "number_range_region": "", "carrier": "", "line_type": "", "timezones": []}
    if not raw:
        empty["error"] = "no number given"
        return empty
    if require_logged and not is_logged_phone(raw):
        empty["error"] = NOT_LOGGED
        return empty
    try:
        import phonenumbers
        from phonenumbers import carrier as pn_carrier, geocoder as pn_geocoder, timezone as pn_timezone
    except ImportError:
        empty["error"] = "phonenumbers package not installed (pip install phonenumbers)"
        return empty
    try:
        n = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException as exc:
        empty["error"] = str(exc)
        return empty
    if not phonenumbers.is_possible_number(n):
        empty["error"] = "not a possible phone number"
        return empty
    kind = phonenumbers.number_type(n)
    return {
        "number": raw, "error": "",
        "e164": phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164),
        "valid": phonenumbers.is_valid_number(n),
        "country_code": n.country_code,
        "number_range_region": pn_geocoder.description_for_number(n, "en") or "",
        "carrier": pn_carrier.name_for_number(n, "en") or "(carrier not published / ported)",
        "line_type": _line_type_names().get(kind, "unknown"),
        "timezones": list(pn_timezone.time_zones_for_number(n)),
    }
