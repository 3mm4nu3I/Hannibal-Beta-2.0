"""Optional ADS-B feeder for satellitemap.space (docs: api-reference/feed-adsb).

WHAT IT DOES   Reads aircraft.json from YOUR OWN local readsb / tar1090 receiver and POSTs it
               to https://api.satellitemap.space/re-api/feed with an X-Feeder-ID header.
WHAT IT SENDS  Your receiver's aircraft positions (hex, flight, lat/lon, altitude, ...) -- which
               also reveals roughly where your receiver is. Nothing else leaves this machine.
OFF BY DEFAULT It only runs when you start it yourself and confirm; there is a dry-run mode that
               reads and counts but never posts.

Documented limits honoured here: JSON or binCraft body (JSON used), <= 2 MB per request, one push
every 5 s recommended (never faster than 2 s). The feeder id is a stable identifier (>= 8 chars);
it is persisted next to the scripts and masked in every line this module prints.
"""
import json
import os
import time
import uuid

from hannibal_net import Net, Result, base_dir, default_net, mask_id, redact_text

FEED_URL = "https://api.satellitemap.space/re-api/feed"
DEFAULT_SOURCE = "http://localhost/tar1090/data/aircraft.json"
MAX_BODY_BYTES = 2 * 1024 * 1024
MIN_INTERVAL = 2.0
DEFAULT_INTERVAL = 5.0
ID_FILE = ".hannibal_feeder_id"


def get_feeder_id():
    """HANNIBAL_FEEDER_ID env var, else a UUID generated once and persisted (>= 8 chars required)."""
    fid = os.getenv("HANNIBAL_FEEDER_ID", "").strip()
    if len(fid) >= 8:
        return fid
    path = base_dir() / ID_FILE
    try:
        stored = path.read_text("utf-8").strip()
        if len(stored) >= 8:
            return stored
    except OSError:
        pass
    fid = "hannibal-" + uuid.uuid4().hex[:16]
    try:
        path.write_text(fid, "utf-8")
    except OSError:
        pass
    return fid


def read_local_aircraft(net=None, source=None):
    """Fetch the receiver's aircraft.json. Returns Result(data=list of aircraft dicts)."""
    net = net or default_net()
    src = source or os.getenv("HANNIBAL_ADSB_SOURCE", DEFAULT_SOURCE)
    res = net.request("GET", src, ttl=0, stale_ok=False, retries=0, timeout=5)
    if res.error:
        return Result(None, error=f"could not read local receiver at {Net.safe_url(src)}: {res.error}")
    data = res.data
    aircraft = data.get("aircraft") if isinstance(data, dict) else data
    if not isinstance(aircraft, list):
        return Result(None, error="receiver returned an unexpected aircraft.json shape")
    return Result(aircraft)


def build_body(aircraft):
    """JSON body {"aircraft": [...]}, trimmed so it never exceeds the documented 2 MB limit."""
    items = list(aircraft)
    body = json.dumps({"aircraft": items}, separators=(",", ":"))
    while len(body.encode("utf-8")) > MAX_BODY_BYTES and items:
        items = items[: int(len(items) * 0.9)]
        body = json.dumps({"aircraft": items}, separators=(",", ":"))
    return body, len(items)


def push_once(feeder_id, aircraft, net=None):
    """POST one batch. Returns Result(data=response dict)."""
    net = net or default_net()
    if len(str(feeder_id)) < 8:
        return Result(None, error="feeder id must be at least 8 characters")
    body, sent = build_body(aircraft)
    res = net.request("POST", FEED_URL, data=body, expect="json", ttl=0, stale_ok=False, retries=1,
                      headers={"X-Feeder-ID": feeder_id, "Content-Type": "application/json"})
    if res.error:
        hint = {"HTTP 401": " (feeder id missing/invalid)", "HTTP 400": " (invalid or oversized body)"}
        for k, v in hint.items():
            if k in res.error:
                res.error += v
        return res
    if isinstance(res.data, dict):
        res.data.setdefault("sent", sent)
    return res


def run(loop=False, interval=DEFAULT_INTERVAL, dry_run=False, confirm=None, print_fn=print, net=None,
        max_cycles=None, sleep=time.sleep):
    """Run the feeder. `confirm` is a callable returning the user's typed answer (defaults to input()).

    Returns 0 on success, 1 on failure/declined. Never raises on network errors.
    """
    interval = max(MIN_INTERVAL, float(interval))
    fid = get_feeder_id()
    print_fn(f"  Feeder id : {mask_id(fid)}   (stable; stored in {ID_FILE})")
    print_fn(f"  Source    : {Net.safe_url(os.getenv('HANNIBAL_ADSB_SOURCE', DEFAULT_SOURCE))}")
    print_fn(f"  Target    : {FEED_URL}")
    if dry_run:
        print_fn("  Mode      : DRY RUN -- reads your receiver, posts nothing")
    else:
        print_fn("  This UPLOADS your receiver's aircraft positions to satellitemap.space.")
        answer = (confirm or (lambda: input("  Type FEED to start, anything else to cancel: ")))()
        if str(answer).strip() != "FEED":
            print_fn("  Cancelled -- nothing was sent.")
            return 1
    cycles = 0
    while True:
        cycles += 1
        got = read_local_aircraft(net)
        if got.error:
            print_fn("  [!] " + redact_text(got.error))
            return 1
        if dry_run:
            print_fn(f"  [dry-run] receiver reports {len(got.data)} aircraft (not sent)")
        else:
            res = push_once(fid, got.data, net)
            if res.error:
                print_fn("  [!] feed failed: " + redact_text(res.error))
                return 1
            merged = res.data.get("merged", "?") if isinstance(res.data, dict) else "?"
            print_fn(f"  [+] sent {res.data.get('sent', len(got.data))} aircraft, merged {merged}")
        if not loop or (max_cycles and cycles >= max_cycles):
            return 0
        sleep(interval)
