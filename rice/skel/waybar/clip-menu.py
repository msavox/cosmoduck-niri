#!/usr/bin/python3
"""clip-menu.py — clipboard history menu (cliphist + ctxmenu), Mod+Ctrl+V.

History is collected by `wl-paste --watch cliphist store` (spawned at niri
startup); this menu shows the most recent entries, selecting one copies it
back to the clipboard (cliphist decode | wl-copy). One menu at a time, like
the dock menu; centered above the dock.

Run with /usr/bin/python3 so GIR typelibs are visible without env tweaks.
"""

import os
import shutil
import signal
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/.config/waybar"))

CLIPHIST = (shutil.which("cliphist")
            or os.path.expanduser("~/.local/bin/cliphist"))
MAX_ITEMS = 15

# Monitor-local x of the clipboard icon in the top bar (calibrated by
# measurement like audio-menu's VOLUME_X) and bar-bottom y, used when the
# menu is opened from the bar icon (`clip-menu.py bar`) instead of the key.
CLIP_X = 1880
TOPBAR_BOTTOM = 44
WIDTH = 300

# niri's environment carries an empty XDG_CACHE_HOME, which would send
# cliphist to /cliphist — pin the real cache dir for every call.
ENV = {**os.environ, "XDG_CACHE_HOME": os.path.expanduser("~/.cache")}


def toggle_off_if_running():
    """A second invocation (key pressed again) closes the open menu."""
    me = os.getpid()
    try:
        out = subprocess.check_output(["pgrep", "-f", "clip-menu.py"],
                                      text=True)
    except subprocess.CalledProcessError:
        return False
    found = False
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
            found = True
        except ProcessLookupError:
            pass
    return found


def history():
    """[(id, preview)] from `cliphist list` (tab-separated, newest first)."""
    try:
        out = subprocess.check_output([CLIPHIST, "list"], text=True,
                                      timeout=3, env=ENV)
    except (subprocess.SubprocessError, OSError):
        return []
    items = []
    for line in out.splitlines()[:MAX_ITEMS]:
        cid, _, preview = line.partition("\t")
        preview = " ".join(preview.split()) or "(empty)"
        items.append((line, preview))   # decode wants the whole line
    return items


def copy_item(line):
    p = subprocess.Popen([CLIPHIST, "decode"],
                         stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, env=ENV)
    data, _ = p.communicate(line.encode())
    subprocess.run(["/usr/bin/wl-copy"], input=data)


def clear_history():
    subprocess.run([CLIPHIST, "wipe"], env=ENV)


def main():
    if toggle_off_if_running():
        return

    from ctxmenu import ContextMenu
    items = history()
    m = ContextMenu(title="Clipboard", width=WIDTH)
    if not items:
        m.add_item("(history is empty)", lambda: None, icon="edit-paste")
    for line, preview in items:
        icon = ("image-x-generic" if "binary data" in preview
                and ("png" in preview or "jpg" in preview or "jpeg" in preview)
                else "edit-paste")
        m.add_item(preview, lambda ln=line: copy_item(ln), icon=icon)
    if items:
        m.add_separator()
        m.add_item("Clear History", clear_history,
                   icon="user-trash", danger=True)
    if len(sys.argv) > 1 and sys.argv[1] == "bar":
        m.popup(anchor_x=CLIP_X - WIDTH // 2, anchor_y=TOPBAR_BOTTOM)
    else:
        m.popup()


if __name__ == "__main__":
    main()
