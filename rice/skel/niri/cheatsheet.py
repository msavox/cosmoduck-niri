#!/usr/bin/env python3
"""Keyboard-shortcut cheatsheet for niri: a single centered window with the
bindings laid out in two columns, plus a "don't show at startup" checkbox.

Bindings are read live from config.kdl, so the cheatsheet always matches the
real configuration. The checkbox toggles ~/.config/niri/cheatsheet-disabled,
which the startup script uses to decide whether to show it at login.

Single-instance toggle: launching while already open closes the open window
(used by the F1 keybind). Implemented with a pidfile, so it never matches its
own command line the way `pkill -f cheatsheet.py` would.
"""
import os
import re
import signal
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

# Wayland app-id (for niri's window-rule); must be set before the window.
GLib.set_prgname("niri-cheatsheet")

HOME = os.path.expanduser("~")
CONFIG = os.path.join(HOME, ".config/niri/config.kdl")
FLAG = os.path.join(HOME, ".config/niri/cheatsheet-disabled")
PIDFILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "niri-cheatsheet.pid")
NCOLS = 3  # cheatsheet columns (3 = fits on a 1080p screen too)

SECTION_RE = re.compile(r"//\s*[─-]+\s*(.+?)\s*[─-]+\s*$")
TITLE_RE = re.compile(r'hotkey-overlay-title="([^"]*)"')
ACTION_RE = re.compile(r"\{\s*(.+?)\s*;?\s*\}")

# Fallback map for section names. The shipped config uses English dividers, so
# this is mostly a no-op; kept for configs that still use Italian section comments.
SECTION_EN = {
    "Cheatsheet": "Cheatsheet",
    "Lanciatori": "Launchers",
    "Sessione": "Session",
    "Finestre": "Windows",
    "Focus finestra": "Window focus",
    "Sposta finestra": "Move window",
    "Multi-monitor": "Multi-monitor",
    "Workspaces": "Workspaces",
    "Tiling scrollable (peculiarità di niri)": "Scrollable tiling",
    "Dimensioni": "Sizing",
    "Screenshot": "Screenshots",
    "Volume / Media / Luminosità": "Volume / Media / Brightness",
    "Escape hatch per app remote-desktop": "Remote-desktop escape hatch",
}


def is_bind_line(line):
    s = line.strip()
    if not s or s.startswith("//"):
        return False
    return "{" in s and not s.startswith(("binds", "}"))


def parse_binds():
    """Return [(section, [(key, label), ...]), ...] from the config."""
    sections = []
    cur_name, cur_items = "Shortcuts", []
    in_binds = False
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return [("Shortcuts", [("F1", "Show/hide cheatsheet")])]

    for line in lines:
        s = line.strip()
        if s.startswith("binds {"):
            in_binds = True
            continue
        if not in_binds:
            continue
        if s == "}":
            break

        m = SECTION_RE.match(s)
        if m:
            if cur_items:
                sections.append((cur_name, cur_items))
            cur_name, cur_items = SECTION_EN.get(m.group(1), m.group(1)), []
            continue

        if is_bind_line(line):
            key = s.split()[0]
            tm = TITLE_RE.search(s)
            if tm:
                label, titled = tm.group(1), True
            else:
                am = ACTION_RE.search(s)
                label = re.sub(r'"', "", am.group(1)) if am else ""
                titled = False
            cur_items.append((key, label, titled))

    if cur_items:
        sections.append((cur_name, cur_items))
    return sections


# ── Condensing repetitive binds ──────────────────────────────
ARROWS = {"Left": "←", "Right": "→", "Up": "↑", "Down": "↓",
          "H": "←", "L": "→", "K": "↑", "J": "↓"}
ARROW_SORT = "←→↑↓"
XF86 = {
    "XF86AudioRaiseVolume": ("Vol +", "Volume up"),
    "XF86AudioLowerVolume": ("Vol −", "Volume down"),
    "XF86AudioMute": ("Mute", "Mute audio"),
    "XF86AudioMicMute": ("Mic", "Mute microphone"),
    "XF86AudioPlay": ("⏯", "Play / Pause"),
    "XF86AudioStop": ("⏹", "Stop"),
    "XF86AudioPrev": ("⏮", "Previous track"),
    "XF86AudioNext": ("⏭", "Next track"),
    "XF86MonBrightnessUp": ("☀ +", "Brightness up"),
    "XF86MonBrightnessDown": ("☀ −", "Brightness down"),
}


def humanize(label):
    base = label.split('"')[0].strip()
    base = base.split()[0] if base else base       # first token of the action
    base = base.replace("-", " ").strip()
    return base[:1].upper() + base[1:] if base else label


def condense_section(items):
    """Merge repetitive families (directions, numbers, ±, media) into single rows."""
    order, groups = [], {}

    def grp(gid):
        if gid not in groups:
            groups[gid] = {"arrows": [], "chip": None, "label": None, "kind": None}
            order.append(gid)
        return groups[gid]

    single = 0
    for key, label, titled in items:
        parts = key.split("+")
        mods, last = "+".join(parts[:-1]), parts[-1]
        pre = (mods + "+") if mods else ""

        if not titled and last in ARROWS:                  # directional (+ hjkl)
            base = re.sub(r"[ -](left|right|up|down)$", "", label, flags=re.I)
            g = grp(("dir", mods, base))
            if ARROWS[last] not in g["arrows"]:
                g["arrows"].append(ARROWS[last])
            g.update(kind="dir", label=humanize(base), pre=pre)
        elif not titled and last.isdigit():                # Mod+1…9 (numbers)
            base = re.sub(r"\s*\d+$", "", label).strip()
            g = grp(("num", mods, base))
            g.update(kind="single", chip=pre + "1…9", label=humanize(base) + " 1–9")
        elif not titled and last in ("Minus", "Equal", "Plus"):  # ± sizing
            verb = label.split('"')[0].split()[0] if label else ""
            g = grp(("size", mods, verb))
            sym = "−" if last == "Minus" else "+"
            if sym not in g["arrows"]:
                g["arrows"].append(sym)
            lbl = ("Column width" if "column-width" in verb
                   else "Window height" if "window-height" in verb else humanize(verb))
            g.update(kind="size", label=lbl, pre=pre)
        elif not titled and "WheelScroll" in last:         # Mod+scroll
            base = re.sub(r"[ -](up|down)$", "", label, flags=re.I)
            g = grp(("wheel", mods, base))
            g.update(kind="single", chip=pre + "scroll", label=humanize(base))
        elif key in XF86:                                  # media keys
            chip, lbl = XF86[key]
            g = grp(("xf86", key))
            g.update(kind="single", chip=chip, label=lbl)
        else:                                              # passthrough
            g = grp(("s", single)); single += 1
            text = label if titled else humanize(label) if label else key
            g.update(kind="single", chip=key, label=text)

    rows = []
    for gid in order:
        g = groups[gid]
        if g["kind"] == "dir":
            arr = "".join(sorted(g["arrows"], key=ARROW_SORT.index))
            rows.append((g["pre"] + arr, g["label"]))
        elif g["kind"] == "size":
            rows.append((g["pre"] + "/".join(g["arrows"]), g["label"]))
        else:
            rows.append((g["chip"], g["label"]))

    # Merge rows with the same description (alternative keybinds).
    merged, seen = [], {}
    for chip, label in rows:
        if label in seen:
            i = seen[label]
            if chip not in merged[i][0]:
                merged[i] = (merged[i][0] + " / " + chip, label)
        else:
            seen[label] = len(merged)
            merged.append((chip, label))
    return merged


def split_columns(sections, n):
    """Contiguous partition of the sections into n columns that minimizes the
    height of the tallest column (so the columns are as balanced as possible
    while preserving reading order)."""
    from itertools import combinations

    w = [len(items) + 1 for _, items in sections]   # +1 = header
    n = min(n, len(sections))
    best = None
    for cuts in combinations(range(1, len(sections)), n - 1):
        bounds = (0, *cuts, len(sections))
        sums = [sum(w[bounds[j]:bounds[j + 1]]) for j in range(n)]
        # priority: smallest possible height (no scroll); on a tie, more even
        # columns (minimal spread).
        score = (max(sums), max(sums) - min(sums))
        if best is None or score < best[0]:
            best = (score, bounds)
    bounds = best[1]
    return [sections[bounds[j]:bounds[j + 1]] for j in range(n)]


CSS = b"""
* {
    font-family: "Inter", "SF Pro Text", "Roboto", sans-serif;
    font-size: 14px;
}
window { background-color: #1e1e2e; }
.title { font-size: 25px; font-weight: 700; color: #89b4fa; }
.section { font-size: 13px; font-weight: 700; color: #f9e2af; }
.key {
    font-family: "CaskaydiaCove Nerd Font", "Cascadia Code", monospace;
    font-size: 13px; font-weight: 600;
    color: #1e1e2e; background-color: #89b4fa;
    border-radius: 8px; padding: 2px 9px;
}
.desc { color: #cdd6f4; font-size: 14px; }
.hint { color: #9399b2; font-size: 13px; }
checkbutton, checkbutton label { color: #cdd6f4; }
button {
    color: #cdd6f4; background: #313244;
    border: none; border-radius: 8px; padding: 5px 16px;
}
button:hover { background: #45475a; }
"""


def build_column(sections):
    """A single grid per column: the chips and descriptions of every section
    stay aligned on the same two columns."""
    grid = Gtk.Grid(column_spacing=12, row_spacing=5)
    grid.set_halign(Gtk.Align.START)
    grid.set_valign(Gtk.Align.START)
    row = 0
    for i, (name, items) in enumerate(sections):
        sec = Gtk.Label(label=name)
        sec.get_style_context().add_class("section")
        sec.set_halign(Gtk.Align.START)
        sec.set_margin_top(12 if i else 0)
        grid.attach(sec, 0, row, 2, 1)          # header spans both columns
        row += 1
        for key, label in items:
            k = Gtk.Label(label=key)
            k.get_style_context().add_class("key")
            kbox = Gtk.Box()                     # wrapper: the chip doesn't stretch
            kbox.pack_start(k, False, False, 0)
            kbox.set_halign(Gtk.Align.START)
            kbox.set_valign(Gtk.Align.CENTER)
            d = Gtk.Label(label=label)
            d.get_style_context().add_class("desc")
            d.set_xalign(0)
            d.set_valign(Gtk.Align.CENTER)
            grid.attach(kbox, 0, row, 1, 1)
            grid.attach(d, 1, row, 1, 1)
            row += 1
    return grid


class Cheatsheet(Gtk.Window):
    def __init__(self):
        super().__init__(title="Keyboard Shortcuts — niri")
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.connect("destroy", self.on_destroy)
        self.connect("key-press-event", self.on_key)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for m in ("top", "bottom"):
            getattr(outer, f"set_margin_{m}")(16)
        outer.set_margin_start(20)
        outer.set_margin_end(20)
        self.add(outer)

        title = Gtk.Label(label="Keyboard Shortcuts")
        title.get_style_context().add_class("title")
        title.set_halign(Gtk.Align.START)
        outer.pack_start(title, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer.pack_start(scrolled, True, True, 0)

        sections = [(name, condense_section(items)) for name, items in parse_binds()]
        cols = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=40)
        cols.set_halign(Gtk.Align.START)
        for column in split_columns(sections, NCOLS):
            cols.pack_start(build_column(column), False, False, 0)
        scrolled.add(cols)
        self._content = cols

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        outer.pack_start(bottom, False, False, 0)

        self.check = Gtk.CheckButton(label="Don't show this cheatsheet at startup")
        self.check.set_active(os.path.exists(FLAG))
        bottom.pack_start(self.check, True, True, 0)

        hint = Gtk.Label(label="Press F1 to toggle  ·  Esc to close")
        hint.get_style_context().add_class("hint")
        bottom.pack_start(hint, False, False, 0)

        close = Gtk.Button(label="Close")
        close.connect("clicked", lambda *_: self.close())
        bottom.pack_start(close, False, False, 0)

    def fit_to_content(self):
        """Size the window to the content's real width/height, capped to the
        screen: no scroll if the content fits."""
        _, nat_w = self._content.get_preferred_width()
        _, nat_h = self._content.get_preferred_height()
        screen = self.get_screen()
        sw = screen.get_width() if screen else 1920
        sh = screen.get_height() if screen else 1080
        w = min(nat_w + 60, int(sw * 0.95))      # + side margins
        h = min(nat_h + 150, int(sh * 0.90))     # + title, checkbox, margins
        self.resize(w, h)

    def on_key(self, _w, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close()
        return False

    def on_destroy(self, *_):
        if self.check.get_active():
            open(FLAG, "a").close()
        elif os.path.exists(FLAG):
            os.remove(FLAG)
        Gtk.main_quit()


def running_pid():
    """PID of the open instance, or None."""
    try:
        with open(PIDFILE) as fh:
            pid = int(fh.read().strip())
        os.kill(pid, 0)  # alive?
        return pid
    except (OSError, ValueError):
        return None


def main():
    # Toggle: if already open, close it and exit.
    pid = running_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            os.remove(PIDFILE)
        except OSError:
            pass
        return

    with open(PIDFILE, "w") as fh:
        fh.write(str(os.getpid()))

    prov = Gtk.CssProvider()
    prov.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    # SIGTERM (toggle-close from another invocation) -> clean shutdown.
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, Gtk.main_quit)

    win = Cheatsheet()
    win.show_all()
    win.fit_to_content()
    try:
        Gtk.main()
    finally:
        if running_pid() == os.getpid():
            try:
                os.remove(PIDFILE)
            except OSError:
                pass


if __name__ == "__main__":
    main()
