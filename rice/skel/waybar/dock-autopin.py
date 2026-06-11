#!/usr/bin/python3
"""
dock-autopin.py — temporary dock pins for unpinned running apps.

The dock shows pinned apps as waybar custom modules (full right-click context
menu via dock-menu.py). Unpinned apps used to go through wlr/taskbar, which
only supports waybar's built-in click actions — no context menu. Instead, the
dock now carries SLOTS permanent "auto-slot" custom modules (dock-gen.sh):
a vacant slot hides itself (dock-status.sh returns empty text — the waybar
quirk used as a feature), an occupied one shows the app's icon via a
pre-generated CSS class and behaves exactly like a pinned app, context menu
included.

This daemon fills the slots: it polls `niri msg --json windows`, and when an
unpinned app has a window it writes an entry (id "auto-slot<n>") into
dock-apps-auto.json; dock-status/dock-click/dock-menu all look ids up in the
pinned+auto merge. Crucially the dock waybar is NEVER restarted — the slots
already exist — so windows never re-layout (no exclusive-zone flicker).

Mechanics:
  • an app must be present for CONFIRM consecutive polls before being
    slotted (ephemeral dialogs/portals never blink a slot in) and absent
    for LINGER polls before the slot is freed (app restarts don't flicker)
  • an app keeps its slot while open; a new app takes the lowest free slot;
    when every slot is busy the app simply doesn't appear (logged)
  • icon CSS class from auto-icon-classes.json (written by dock-gen.sh for
    every installed .desktop app); apps installed after the last dock-gen
    run fall back to the generic executable icon until the next run.

Spawned from niri's config at startup. Run with /usr/bin/python3 so the GIR
typelibs resolve.
"""

import json
import os
import re
import subprocess
import sys
import time
import traceback

from gi.repository import Gio

CFG = os.path.expanduser("~/.config/waybar")
APPS = os.path.join(CFG, "dock-apps.json")
AUTO = os.path.join(CFG, "dock-apps-auto.json")
ICONS = os.path.join(CFG, "auto-icon-classes.json")
LOG = os.path.join(CFG, "dock-autopin.log")

SLOTS = 16    # must match SLOTS in dock-gen.sh
POLL = 2.0    # seconds between niri polls
CONFIRM = 2   # consecutive sightings before slotting
LINGER = 2    # consecutive absences before freeing the slot
FALLBACK_ICON = "application-x-executable"

# app_ids that must never be auto-pinned (shell pieces, portals, pickers)
SKIP = {
    "xdg-desktop-portal-gtk", "xdg-desktop-portal-gnome",
    "ulauncher", "dock-manager", "dock-manager.py",
}


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def single_instance_or_exit():
    """Same comm-filtered pattern as dock-menu.py: only real pythons count."""
    me = os.getpid()
    try:
        out = subprocess.check_output(["pgrep", "-f", r"dock-autopin\.py"],
                                      text=True)
    except subprocess.CalledProcessError:
        return
    for tok in out.split():
        pid = int(tok)
        if pid == me:
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip().startswith("python"):
                    sys.exit(0)
        except OSError:
            continue


class MtimeJson:
    """A JSON file re-read only when its mtime changes."""

    def __init__(self, path, default):
        self.path = path
        self.default = default
        self._mtime = None
        self.data = default

    def get(self):
        try:
            mt = os.stat(self.path).st_mtime
        except OSError:
            return self.data
        if mt != self._mtime:
            try:
                with open(self.path) as f:
                    self.data = json.load(f)
                self._mtime = mt
            except (OSError, json.JSONDecodeError):
                pass
        return self.data


class Pinned:
    """Filters from dock-apps.json, so pinning an app for real in
    dock-manager retires its auto-slot."""

    def __init__(self):
        self._file = MtimeJson(APPS, [])
        self._cache_id = None
        self.regexes, self.app_ids = [], set()

    def refresh(self):
        entries = self._file.get()
        if id(entries) == self._cache_id:
            return
        self._cache_id = id(entries)
        self.regexes, self.app_ids = [], set()
        for e in entries:
            m = e.get("match")
            if m:
                try:
                    self.regexes.append(re.compile(m))
                except re.error:
                    pass
            self.app_ids.update(e.get("app_ids") or [])

    def covers(self, aid):
        return aid in self.app_ids or any(r.search(aid) for r in self.regexes)


def open_app_ids():
    """app_ids with at least one niri window; None if niri is unreachable."""
    try:
        wins = json.loads(subprocess.check_output(
            ["niri", "msg", "--json", "windows"], text=True, timeout=5))
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None
    return {w.get("app_id") for w in wins if w.get("app_id")}


def desktop_info(aid):
    """Best-effort .desktop lookup for a niri app_id (same ladder waybar's
    taskbar used: exact id, lowercase, StartupWMClass, executable name)."""
    for cand in (aid, aid.lower()):
        try:
            info = Gio.DesktopAppInfo.new(cand + ".desktop")
        except TypeError:
            # pygobject raises "constructor returned NULL" for a missing
            # .desktop instead of returning None (this killed the daemon
            # before the per-pass guard existed)
            info = None
        if info is not None:
            return info
    low = aid.lower()
    all_infos = [ai for ai in Gio.AppInfo.get_all()
                 if isinstance(ai, Gio.DesktopAppInfo)]
    for ai in all_infos:
        if (ai.get_startup_wm_class() or "").lower() == low:
            return ai
    for ai in all_infos:
        if os.path.basename(ai.get_executable() or "").lower() == low:
            return ai
    return None


def make_entry(aid, slot, icon_classes):
    info = desktop_info(aid)
    name, icon, cmd = aid, FALLBACK_ICON, aid
    if info is not None:
        name = info.get_display_name() or aid
        icon = info.get_string("Icon") or FALLBACK_ICON
        cmd = "gtk-launch " + info.get_id()
    if icon not in icon_classes:
        icon = FALLBACK_ICON
    return {
        "id": f"auto-slot{slot}",
        "icon": " ",
        "name": name,
        "command": cmd,
        "color": "#8aadf4",
        "match": "^" + re.escape(aid) + "$",
        "app_ids": [aid],
        "icon_name": icon,
        "icon_class": icon_classes.get(icon, "icon-" + FALLBACK_ICON),
        "auto": True,
    }


def publish(auto):
    entries = sorted(auto.values(),
                     key=lambda e: int(e["id"].replace("auto-slot", "") or 0))
    tmp = AUTO + ".tmp"
    with open(tmp, "w") as f:
        json.dump(entries, f, indent=1)
    os.replace(tmp, AUTO)


def main():
    single_instance_or_exit()
    # Don't wipe the log on start (it may hold the previous run's crash);
    # just cap its growth.
    try:
        if os.path.getsize(LOG) > 256 * 1024:
            os.truncate(LOG, 0)
    except OSError:
        pass
    pinned = Pinned()
    icons = MtimeJson(ICONS, {})

    # Adopt leftovers from a previous session: slots stay stable, and the
    # first pass frees any whose app is no longer open (no LINGER wait).
    auto = {}
    try:
        with open(AUTO) as f:
            for e in json.load(f):
                aids = e.get("app_ids") or []
                if aids and e.get("id", "").startswith("auto-slot"):
                    auto[aids[0]] = e
    except (OSError, json.JSONDecodeError):
        pass

    seen, gone = {}, {}
    first = True
    log(f"started pid {os.getpid()}")
    while True:
        # The whole pass is guarded: one bad app entry / transient error must
        # not kill the daemon — log the traceback and try again next poll.
        try:
            ids = open_app_ids()
            if ids is None:
                time.sleep(POLL)
                continue
            pinned.refresh()
            cand = {a for a in ids if a not in SKIP and not pinned.covers(a)}

            changed = False
            # departures first: their slots free up for this pass's arrivals
            for a in list(auto):
                if a in cand:
                    gone.pop(a, None)
                    continue
                gone[a] = gone.get(a, 0) + 1
                if first or gone[a] >= LINGER:
                    log(f"free {auto[a]['id']} ({a})")
                    del auto[a]
                    gone.pop(a, None)
                    changed = True

            used = {e["id"] for e in auto.values()}
            free = [s for s in range(1, SLOTS + 1)
                    if f"auto-slot{s}" not in used]
            for a in sorted(cand):
                seen[a] = seen.get(a, 0) + 1
                if a in auto or seen[a] < CONFIRM:
                    continue
                if not free:
                    log(f"no free slot for {a}")
                    continue
                slot = free.pop(0)
                auto[a] = make_entry(a, slot, icons.get())
                log(f"slot{slot} <- {a} ({auto[a]['name']}, "
                    f"{auto[a]['icon_class']})")
                changed = True
            for a in list(seen):
                if a not in cand:
                    del seen[a]

            if changed:
                publish(auto)
            first = False
        except Exception:
            log("pass failed:\n" + traceback.format_exc())
        time.sleep(POLL)


if __name__ == "__main__":
    main()
