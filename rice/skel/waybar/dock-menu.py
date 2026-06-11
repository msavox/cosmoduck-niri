#!/usr/bin/python3
"""
dock-menu.py <id> — right-click context menu for a dock app.

Bound as on-click-right on each pinned dock module (see dock-gen.sh). A thin
consumer of the shared ctxmenu framework (ctxmenu.py): it gathers the app's
state from niri and hands a list of items to ContextMenu, which renders the
self-dismissing overlay. Entries:

  • New Window       — always; launches a fresh instance (dock-click.sh <id> new)
  • Focus: …         — one row per open instance, when more than one is open
  • Keep in Dock     — auto-pinned (running, unpinned) apps: copy the entry
                       into dock-apps.json and regenerate the dock
  • Remove from Dock — pinned apps: drop the entry from dock-apps.json (a
                       running app re-enters via an auto-slot)
  • Close            — gracefully closes every instance (niri close-window --id)
  • Force Quit       — SIGKILLs every instance's pid (for a hung app)

A second right-click on any icon replaces the menu (one menu at a time).

Run with /usr/bin/python3 so GIR typelibs are visible without env tweaks.
"""

import json
import os
import re
import signal
import subprocess
import sys

CFG = os.path.expanduser("~/.config/waybar")
APPS = os.path.join(CFG, "dock-apps.json")
AUTO = os.path.join(CFG, "dock-apps-auto.json")

# Dock layout constants (mirror dock-gen.sh / dock.css for the H=52 baseline),
# used only to estimate where a clicked icon sits on screen.
DOCK_SPACING = 6     # waybar "spacing" between modules
DOCK_MARGIN = 6      # waybar dock margin-left / margin-right
MOD_MARGIN_X = 6     # CSS "margin: 6px 3px" -> 3px each side


def _toggle_off_if_running():
    """If another dock-menu.py is already up, kill it — so a second right-click
    (on any icon) replaces the menu. Filters on /proc/PID/comm == python* so we
    don't kill the sh -c parent waybar spawned (which would drag us down)."""
    me = os.getpid()
    try:
        out = subprocess.check_output(["pgrep", "-f", "dock-menu.py"], text=True)
    except subprocess.CalledProcessError:
        return
    for tok in out.split():
        pid = int(tok)
        if pid == me:
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                if not f.read().strip().startswith("python"):
                    continue
        except (FileNotFoundError, PermissionError):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def load_all():
    """Pinned entries + temporary auto-pins (dock-autopin.py), in the same
    order dock-gen.sh merges them — icon_center_x relies on that order."""
    with open(APPS) as f:
        apps = json.load(f)
    try:
        with open(AUTO) as f:
            extra = json.load(f)
        if isinstance(extra, list):
            apps += extra
    except (OSError, ValueError):
        pass
    return apps


def load_entry(app_id):
    for e in load_all():
        if e.get("id") == app_id:
            return e
    return None


def matching_windows(match):
    """Return [{id, pid, title}] of niri windows whose app_id matches the
    entry's regex, sorted by window id for a stable order."""
    if not match:
        return []
    try:
        wins = json.loads(subprocess.check_output(
            ["niri", "msg", "--json", "windows"], text=True))
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
        return []
    pat = re.compile(match)
    res = [{"id": w.get("id"), "pid": w.get("pid"),
            "title": w.get("title") or (w.get("app_id") or "")}
           for w in wins if pat.search(w.get("app_id") or "")]
    res.sort(key=lambda w: (w["id"] is None, w["id"]))
    return res


def _read_apps():
    try:
        with open(APPS) as f:
            v = json.load(f)
        return v if isinstance(v, list) else []
    except (OSError, ValueError):
        return []


def _write_apps_and_regen(apps):
    with open(APPS, "w") as f:
        json.dump(apps, f, indent=2)
        f.write("\n")
    # dock-gen.sh regenerates dock.jsonc + pinned CSS and restarts the dock
    subprocess.Popen(["bash", os.path.join(CFG, "dock-gen.sh")],
                     start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pin_app(entry):
    """Keep in Dock: promote an auto-slot entry to a permanent pin, inserted
    before the post_taskbar tail (settings/trash) so it joins the other
    pinned icons. The auto-slot frees itself at the next autopin pass."""
    apps = _read_apps()
    ids = {e.get("id") for e in apps}
    base = re.sub(r"[^a-z0-9]+", "-",
                  (entry.get("name") or entry.get("id") or "app").lower(),
                  ).strip("-") or "app"
    new_id, n = base, 2
    while new_id in ids:
        new_id, n = f"{base}-{n}", n + 1
    e = {k: v for k, v in entry.items() if k not in ("auto", "icon_class")}
    e["id"] = new_id
    if any(a.get("post_taskbar") for a in apps):
        tail = next(i for i, a in enumerate(apps) if a.get("post_taskbar"))
    else:
        tail = max(len(apps) - 1, 0)  # legacy: last entry acts as post
    apps.insert(tail, e)
    _write_apps_and_regen(apps)


def unpin_app(app_id):
    """Remove from Dock: a running app re-enters via an auto-slot."""
    _write_apps_and_regen(
        [e for e in _read_apps() if e.get("id") != app_id])


def launch_new(app_id):
    subprocess.Popen(
        ["bash", os.path.join(CFG, "dock-click.sh"), app_id, "new"],
        start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def focus_window(win_id):
    subprocess.run(["niri", "msg", "action", "focus-window", "--id", str(win_id)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def close_windows(wins):
    for w in wins:
        if w["id"] is not None:
            subprocess.run(
                ["niri", "msg", "action", "close-window", "--id", str(w["id"])],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def force_quit(wins):
    for w in wins:
        if w["pid"]:
            try:
                os.kill(int(w["pid"]), signal.SIGKILL)
            except (ProcessLookupError, ValueError, PermissionError):
                pass


def icon_center_x(app_id):
    """Best-effort monitor-local X (px) of the clicked icon's center.

    The dock is centered in modules-center as
        [pinned icons] [occupied auto-slots] [post icons]
    Vacant auto-slots are hidden (no width) and absent from the merged list,
    so every visible module IS a merged entry — load_all()'s order matches
    the on-screen order. Approximate — waybar's exact box model isn't
    observable — but close. Returns None on any failure (ContextMenu then
    falls back to centered placement)."""
    try:
        out = json.loads(subprocess.check_output(
            ["niri", "msg", "--json", "focused-output"], text=True))
        S = out["logical"]["width"]
    except Exception:
        return None
    try:
        with open(os.path.join(CFG, "dock-config.json")) as f:
            H = int(json.load(f).get("height", 52))
    except Exception:
        H = 52
    H = max(36, min(110, H))
    fp = (H * 36 // 52) + MOD_MARGIN_X   # module footprint

    try:
        apps = load_all()
    except Exception:
        return None
    pre = [e["id"] for e in apps if not e.get("post_taskbar")]
    post = [e["id"] for e in apps if e.get("post_taskbar")]

    seq = pre + post
    if not seq:
        return None
    total = fp * len(seq) + DOCK_SPACING * (len(seq) - 1) + 2 * DOCK_MARGIN
    left = (S - total) / 2 + DOCK_MARGIN

    if app_id not in seq:
        return None
    idx = seq.index(app_id)
    return left + idx * (fp + DOCK_SPACING) + fp / 2


def main():
    app_id = sys.argv[1] if len(sys.argv) > 1 else ""
    entry = load_entry(app_id)
    if entry is None:
        sys.exit(f"unknown dock id: {app_id}")

    _toggle_off_if_running()

    name = entry.get("name", app_id)
    wins = matching_windows(entry.get("match", ""))

    from ctxmenu import ContextMenu  # imported after the toggle/exit checks
    m = ContextMenu(title=name)
    m.add_item("New Window", lambda: launch_new(app_id), icon="window-new")

    if len(wins) > 1:
        m.add_separator()
        for w in wins:
            m.add_item(w["title"],
                       (lambda wid=w["id"]: focus_window(wid)),
                       icon="go-next-symbolic")

    pinned = any(e.get("id") == app_id for e in _read_apps())
    if not (pinned and entry.get("post_taskbar")):  # settings/trash stay put
        m.add_separator()
        if pinned:
            m.add_item("Remove from Dock", lambda: unpin_app(app_id),
                       icon="list-remove")
        else:
            m.add_item("Keep in Dock", lambda: pin_app(entry),
                       icon="list-add")

    if wins:
        m.add_separator()
        n = len(wins)
        m.add_item("Close" if n == 1 else f"Close all ({n})",
                   lambda: close_windows(wins), icon="window-close")
        m.add_item("Force Quit", lambda: force_quit(wins),
                   icon="process-stop", danger=True)

    m.popup(anchor_x=icon_center_x(app_id))


if __name__ == "__main__":
    main()
