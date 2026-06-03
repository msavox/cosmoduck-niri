#!/usr/bin/python3
"""Per-app notification count for the waybar dock badges (semantics "B").

Counts the notifications that have *arrived and not yet been handled* for each
pinned dock app. A notification:
  - INCREMENTS on arrival                  -> `receive` subcommand (swaync run-on receive)
  - DECREMENTS when it is closed           -> daemon, DBus signal NotificationClosed
    (closed = expired by timeout, clicked/dismissed, or closed by the app)
  - is CLEARED (whole app) on dock click   -> `clear` subcommand

State: ~/.config/waybar/notif-counts.json = { "<dock-id>": [id1, id2, ...] }
The shown count is len(list). We keep the list of IDs (not an integer) for:
dedup on updates (replaces_id reuses the same id) and precise decrement on
NotificationClosed (which carries only the id, not the app).

The notification -> dock-id mapping is derived from dock-apps.json (single
source of truth): for each app we try `notify_match`/`notify_names` (optional)
and then fall back to `match` (app_id regex), `app_ids`, `name`. This way new
apps need no extra work here.
"""
import fcntl
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime

CFG = os.path.expanduser("~/.config/waybar")
APPS = os.path.join(CFG, "dock-apps.json")
STATE = os.path.join(CFG, "notif-counts.json")
LOCK = os.path.join(CFG, ".notif-counts.lock")
LOG = os.path.join(CFG, "notif-count.log")


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(f"{datetime.now():%H:%M:%S} {msg}\n")
    except OSError:
        pass


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


@contextmanager
def state_locked():
    """Exclusive lock + load/save the JSON state atomically."""
    with open(LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            with open(STATE) as sf:
                data = json.load(sf)
        except (OSError, json.JSONDecodeError):
            data = {}
        box = {"data": data}
        yield box
        tmp = STATE + ".tmp"
        with open(tmp, "w") as sf:
            json.dump(box["data"], sf)
        os.replace(tmp, STATE)


def load_apps():
    try:
        with open(APPS) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def resolve_dock_id(app_name, desktop_entry):
    """Find the dock id for a notification, or None if no reliable match."""
    de = os.path.basename(desktop_entry or "").lower()
    if de.endswith(".desktop"):
        de = de[:-8]
    de_n = norm(de)
    name_n = norm(app_name)

    best, best_score = None, 0
    for e in load_apps():
        eid = e.get("id")
        score = 0
        # optional notification fields (explicit override, wins over everything)
        for nn in e.get("notify_names", []) or []:
            if norm(nn) and norm(nn) == name_n:
                score = max(score, 120)
        nm = e.get("notify_match")
        if nm and (de and re.search(nm, de) or app_name and re.search(nm, app_name)):
            score = max(score, 120)
        # fallback: app_id regex match using the desktop-entry
        m = e.get("match")
        if m and de and re.search(m, de):
            score = max(score, 100)
        # desktop-entry equal to a declared app_id
        if de and de in [a.lower() for a in e.get("app_ids", []) or []]:
            score = max(score, 100)
        # name: substring either way (len>=4 to avoid noise)
        en = norm(e.get("name"))
        if name_n and en and len(name_n) >= 4 and (name_n in en or en in name_n):
            score = max(score, 40)
        if score > best_score:
            best, best_score = eid, score

    return best if best_score >= 40 else None


def cmd_receive():
    app_name = os.environ.get("SWAYNC_APP_NAME", "")
    desktop_entry = os.environ.get("SWAYNC_DESKTOP_ENTRY", "")
    raw_id = os.environ.get("SWAYNC_ID", "")
    try:
        nid = int(raw_id)
    except ValueError:
        log(f"receive: invalid SWAYNC_ID {raw_id!r}")
        return 0
    dock_id = resolve_dock_id(app_name, desktop_entry)
    if not dock_id:
        log(f"receive: no match app_name={app_name!r} de={desktop_entry!r} id={nid}")
        return 0
    with state_locked() as box:
        ids = box["data"].setdefault(dock_id, [])
        if nid not in ids:
            ids.append(nid)
    log(f"receive: +{dock_id} id={nid} (app_name={app_name!r})")
    return 0


def cmd_closed(nid):
    with state_locked() as box:
        for dock_id, ids in box["data"].items():
            if nid in ids:
                ids.remove(nid)
                log(f"closed: -{dock_id} id={nid}")
                break


def cmd_clear(dock_id):
    with state_locked() as box:
        if box["data"].get(dock_id):
            log(f"clear: {dock_id} ({len(box['data'][dock_id])} cleared)")
            box["data"][dock_id] = []
    return 0


def cmd_daemon():
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    def on_closed(_conn, _sender, _path, _iface, _signal, params):
        try:
            nid = params.unpack()[0]
        except Exception:
            return
        cmd_closed(int(nid))

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    bus.signal_subscribe(
        None, "org.freedesktop.Notifications", "NotificationClosed",
        "/org/freedesktop/Notifications", None, Gio.DBusSignalFlags.NONE,
        on_closed,
    )
    log("daemon: started, listening on NotificationClosed")
    GLib.MainLoop().run()


def main(argv):
    if not argv:
        print("usage: notif-count.py {daemon|receive|clear <id>|count <id>}", file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd == "daemon":
        return cmd_daemon()
    if cmd == "receive":
        return cmd_receive()
    if cmd == "clear":
        return cmd_clear(argv[1]) if len(argv) > 1 else 2
    if cmd == "closed":
        if len(argv) > 1:
            cmd_closed(int(argv[1]))
        return 0
    if cmd == "count":
        if len(argv) < 2:
            return 2
        try:
            with open(STATE) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
        print(len(data.get(argv[1], [])))
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
