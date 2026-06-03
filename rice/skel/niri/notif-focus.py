#!/usr/bin/env python3
"""Move niri's focus to the window of the app that emitted the notification.

Invoked by swaync as a `run-on: action` script: when the user clicks a
notification, swaync runs this with the SWAYNC_* environment variables.
On Wayland an app cannot focus itself (niri blocks focus-stealing and at most
marks the window as `is_urgent`); here we do it via `niri msg action
focus-window`.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime

LOG = os.path.expanduser("~/.config/niri/notif-focus.log")

# app-name (from the notification) -> token to look for in the niri app_id.
# Needed when the notification name does not resemble the app_id.
ALIASES = {
    "microsoft teams": "teams-for-linux",
    "teams": "teams-for-linux",
}


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(f"{datetime.now():%H:%M:%S} {msg}\n")
    except OSError:
        pass


def norm(s):
    """lowercase, alphanumerics only"""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def main():
    app_name = os.environ.get("SWAYNC_APP_NAME", "")
    desktop_entry = os.environ.get("SWAYNC_DESKTOP_ENTRY", "")

    # basename without .desktop
    de = os.path.basename(desktop_entry).lower()
    if de.endswith(".desktop"):
        de = de[:-8]
    de_n = norm(de)
    name_n = norm(app_name)
    alias_n = norm(ALIASES.get(app_name.lower(), ""))

    log(f"click app_name={app_name!r} desktop_entry={desktop_entry!r}")

    try:
        out = subprocess.run(
            ["niri", "msg", "--json", "windows"],
            capture_output=True, text=True, check=True,
        ).stdout
        wins = json.loads(out)
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
        log(f"error reading windows: {e}")
        return 1

    best = None
    best_score = 0
    for w in wins:
        aid = (w.get("app_id") or "").lower()
        aid_n = norm(aid)
        title_n = norm(w.get("title") or "")
        score = 0

        # strong match on desktop-entry <-> app_id
        if de_n and (de_n in aid_n or aid_n in de_n):
            score += 100
        # known alias (e.g. Microsoft Teams -> teams-for-linux)
        if alias_n and alias_n in aid_n:
            score += 100
        # app-name inside the app_id
        if name_n and (name_n in aid_n or aid_n in name_n):
            score += 60
        # app-name inside the title (useful for PWAs: app_id is a ULID)
        if name_n and name_n in title_n:
            score += 30
        # niri marked this window as urgent -> great hint
        if w.get("is_urgent"):
            score += 50

        if score > best_score:
            best_score = score
            best = w

    # threshold: require at least a nominal match to avoid focusing at random
    if best and best_score >= 30:
        wid = best["id"]
        log(f"-> focus id={wid} app_id={best.get('app_id')!r} score={best_score}")
        subprocess.run(["niri", "msg", "action", "focus-window", "--id", str(wid)])
        return 0

    log(f"no reliable match (best_score={best_score})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
