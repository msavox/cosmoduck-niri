#!/usr/bin/python3
"""
osd.py — macOS-style volume/brightness OSD for the Cosmoduck niri shell.

A small translucent card (icon + level bar) that pops bottom-center when the
volume / brightness / mute keys are pressed, then fades out after a moment —
the macOS HUD feel. Listens on a named pipe; the key binds in config.kdl run
the real pactl/brightnessctl command and then poke the pipe via
osd-notify.sh, so the OSD always re-reads the REAL current state (nothing to
keep in sync).

Pipe protocol (one word per line): volume | mic | brightness
  $XDG_RUNTIME_DIR/cosmoduck-osd.fifo

Surface: layer-shell OVERLAY (shows above everything, swaylock included —
the binds are allow-when-locked), keyboard mode NONE and an EMPTY input
region, so it can never steal focus or clicks. The daemon holds the fifo
open O_RDWR: writers never block while it is alive, and osd-notify.sh
guards with a timeout for when it is not.

Run with /usr/bin/python3 so the GIR typelibs resolve without env tweaks.
"""

import os
import re
import subprocess
import sys

import cairo
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell  # noqa: E402
except (ValueError, ImportError):
    sys.stderr.write("osd.py: gtk-layer-shell not available\n")
    sys.exit(1)

FIFO = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
                    "cosmoduck-osd.fifo")
HIDE_MS = 1500          # how long the card stays after the last key press
CARD = 190              # square card side (px)
ICON_PX = 80
BAR_W, BAR_H = 130, 6
MARGIN_BOTTOM = 110     # above the dock (h<=110 + 10 margin), macOS-ish

_CSS = b"""
window { background: transparent; }
.osd-card {
  background: rgba(36, 36, 38, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 26px;
  box-shadow: 0 10px 32px 4px rgba(0, 0, 0, 0.45);
}
.osd-card image { color: #f5f5f7; }
.osd-card.muted image { color: rgba(245, 245, 247, 0.45); }
.osd-card progressbar trough {
  background: rgba(255, 255, 255, 0.18);
  border: none;
  border-radius: 3px;
  min-height: 6px;
}
.osd-card progressbar progress {
  background: #8aadf4;
  border: none;
  border-radius: 3px;
  min-height: 6px;
}
.osd-card.muted progressbar progress {
  background: rgba(138, 173, 244, 0.35);
}
"""


def _level_icon(prefix, frac, muted, steps):
    """Adwaita-style symbolic icon name for a level: prefix-{muted,low,...}"""
    if muted:
        return f"{prefix}-muted-symbolic"
    if frac <= 0.01:
        return f"{prefix}-muted-symbolic"
    idx = min(int(frac * len(steps)), len(steps) - 1)
    return f"{prefix}-{steps[idx]}-symbolic"


def _pactl_level(kind):
    """(fraction, muted) via pactl. NB: jammy's wpctl (WirePlumber 0.4) has
    no get-volume subcommand, so pactl it is.
    "Volume: front-left: 35070 /  54% / ..." + "Mute: no"."""
    out = subprocess.check_output(
        ["/usr/bin/pactl", f"get-{kind}-volume",
         "@DEFAULT_SINK@" if kind == "sink" else "@DEFAULT_SOURCE@"],
        text=True, timeout=3)
    m = re.search(r"(\d+)%", out)
    vol = (int(m.group(1)) if m else 0) / 100.0
    out = subprocess.check_output(
        ["/usr/bin/pactl", f"get-{kind}-mute",
         "@DEFAULT_SINK@" if kind == "sink" else "@DEFAULT_SOURCE@"],
        text=True, timeout=3)
    return vol, "yes" in out


def get_volume():
    return _pactl_level("sink")


def get_mic():
    return _pactl_level("source")


def get_brightness():
    out = subprocess.check_output(
        ["/usr/bin/brightnessctl", "-m"], text=True, timeout=3)
    # machine format: device,class,current,percent%,max
    parts = out.strip().split(",")
    try:
        return int(parts[3].rstrip("%")) / 100.0, False
    except (IndexError, ValueError):
        return 0.0, False


KINDS = {
    "volume": (get_volume, "audio-volume", ("low", "medium", "high")),
    "mute": (get_volume, "audio-volume", ("low", "medium", "high")),
    "mic": (get_mic, "microphone-sensitivity", ("low", "medium", "high")),
    "brightness": (get_brightness, None, None),
}

# macOS-style feedback tick on volume keys ("volume" only: mute stays silent,
# and when the sink IS muted the tick is inaudible by construction). The tick
# is also skipped while OTHER audio is actually playing (music, call, video):
# there it would be useless on top of the audible volume change, and annoying.
TICK = "/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga"


def _streams_playing():
    """True if any sink-input is uncorked (= actually playing), ignoring our
    own paplay ticks (otherwise fast key repeats would self-silence)."""
    try:
        out = subprocess.check_output(["/usr/bin/pactl", "list", "sink-inputs"],
                                      text=True, timeout=3)
    except (subprocess.SubprocessError, OSError):
        return False
    for block in out.split("Sink Input #"):
        if "Corked: no" in block and "paplay" not in block:
            return True
    return False


def play_tick():
    if _streams_playing():
        return
    try:
        subprocess.Popen(["/usr/bin/paplay", TICK],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


class Osd:
    def __init__(self):
        self._hide_id = None
        self._build()

    def _build(self):
        self.win = win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_decorated(False)
        win.set_app_paintable(True)
        visual = win.get_screen().get_rgba_visual()
        if visual is not None:
            win.set_visual(visual)
        win.set_title("cosmoduck-osd")

        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_namespace(win, "cosmoduck-osd")
        GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
        GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.BOTTOM, True)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.BOTTOM, MARGIN_BOTTOM)
        GtkLayerShell.set_exclusive_zone(win, -1)

        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.card = card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                   spacing=18)
        card.get_style_context().add_class("osd-card")
        card.set_size_request(CARD, CARD)

        self.icon = Gtk.Image()
        self.icon.set_pixel_size(ICON_PX)
        self.icon.set_valign(Gtk.Align.END)
        self.icon.set_vexpand(True)

        self.bar = Gtk.ProgressBar()
        self.bar.set_size_request(BAR_W, BAR_H)
        self.bar.set_halign(Gtk.Align.CENTER)
        self.bar.set_valign(Gtk.Align.START)
        self.bar.set_margin_bottom(26)

        card.pack_start(self.icon, True, True, 0)
        card.pack_start(self.bar, False, False, 0)
        win.add(card)

        # Clicks must fall through to whatever is underneath.
        win.connect("map-event", self._clear_input_region)

    @staticmethod
    def _clear_input_region(widget, _ev):
        gdk_win = widget.get_window()
        if gdk_win is not None:
            gdk_win.input_shape_combine_region(cairo.Region(), 0, 0)
        return False

    def show(self, kind):
        getter, prefix, steps = KINDS[kind]
        try:
            frac, muted = getter()
        except (subprocess.SubprocessError, OSError):
            return
        if kind == "brightness":
            icon = "display-brightness-symbolic"
        else:
            icon = _level_icon(prefix, frac, muted, steps)
        if kind == "volume":
            play_tick()
        self.icon.set_from_icon_name(icon, Gtk.IconSize.DIALOG)
        self.icon.set_pixel_size(ICON_PX)
        self.bar.set_fraction(max(0.0, min(frac, 1.0)))
        ctx = self.card.get_style_context()
        (ctx.add_class if muted else ctx.remove_class)("muted")

        self.win.show_all()
        if self._hide_id is not None:
            GLib.source_remove(self._hide_id)
        self._hide_id = GLib.timeout_add(HIDE_MS, self._hide)

    def _hide(self):
        self._hide_id = None
        self.win.hide()
        return False


def single_instance_or_exit():
    me = os.getpid()
    try:
        out = subprocess.check_output(["pgrep", "-f", r"osd\.py"], text=True)
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


def main():
    single_instance_or_exit()

    import stat
    if os.path.exists(FIFO) and not stat.S_ISFIFO(os.stat(FIFO).st_mode):
        os.unlink(FIFO)          # stale non-fifo leftover
    if not os.path.exists(FIFO):
        os.mkfifo(FIFO, 0o600)
    # O_RDWR: the daemon itself keeps a writer open, so reads never see EOF
    # and clients' opens never block while we are alive.
    fd = os.open(FIFO, os.O_RDWR | os.O_NONBLOCK)

    osd = Osd()

    def on_data(_fd, _cond):
        try:
            data = os.read(fd, 1024).decode(errors="replace")
        except OSError:
            return True
        for tok in data.split():
            if tok in KINDS:
                osd.show(tok)
        return True

    GLib.io_add_watch(fd, GLib.PRIORITY_DEFAULT, GLib.IO_IN, on_data)
    Gtk.main()


if __name__ == "__main__":
    main()
