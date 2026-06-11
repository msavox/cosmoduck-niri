#!/usr/bin/python3
"""
osd.py — macOS-style volume/brightness OSD for the Cosmoduck niri shell.

A small translucent card (icon + level bar) that pops bottom-center when the
volume / brightness / mute keys are pressed, then fades out after a moment —
the macOS HUD feel. Listens on a named pipe; the key binds in config.kdl run
the real pactl/brightnessctl command and then poke the pipe via
osd-notify.sh, so the OSD always re-reads the REAL current state (nothing to
keep in sync).

Pipe protocol (one word per line):
  volume | mute | mic | brightness | playpause | stop | next | prev | fwd | rwd
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
import time

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
.osd-card label {
  font-family: "Inter", "Roboto", "Ubuntu", "Noto Sans", sans-serif;
}
.osd-title {
  color: #f5f5f7;
  font-weight: 600;
  font-size: 14px;
}
.osd-artist {
  color: rgba(245, 245, 247, 0.55);
  font-size: 12px;
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

# Media-key kinds: icon-only card (the level bar stays as an invisible
# spacer so the icon sits exactly where it does on the volume card).
# "playpause" picks its icon from the REAL playerctl status after the bind
# has toggled it, same re-read-the-truth philosophy as the levels.
MEDIA_KINDS = {
    "playpause": None,
    "stop": "media-playback-stop-symbolic",
    "next": "media-skip-forward-symbolic",
    "prev": "media-skip-backward-symbolic",
    "fwd": "media-seek-forward-symbolic",
    "rwd": "media-seek-backward-symbolic",
}


def get_player_status():
    """playerctl status: Playing | Paused | Stopped | None (no player)."""
    try:
        return subprocess.check_output(
            ["/usr/bin/playerctl", "status"], text=True, timeout=3,
            stderr=subprocess.DEVNULL).strip()
    except (subprocess.SubprocessError, OSError):
        return None

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


_last_tick = 0.0


def play_tick():
    # Debounce: a keybind change reaches us twice (fifo poke + the pactl
    # subscribe echo of the same change); one tick is enough.
    global _last_tick
    now = time.monotonic()
    if now - _last_tick < 0.25:
        return
    if _streams_playing():
        return
    _last_tick = now
    try:
        subprocess.Popen(["/usr/bin/paplay", TICK],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


class Osd:
    def __init__(self):
        self._hide_id = None
        self.sink_state = None   # last (frac, muted) shown/seen for the sink
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

        # Track-info labels (now-playing card only); no_show_all so the
        # level/media kinds keep the plain icon+bar layout.
        self.title_lbl = Gtk.Label()
        self.title_lbl.get_style_context().add_class("osd-title")
        self.title_lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        self.title_lbl.set_max_width_chars(24)
        self.title_lbl.set_no_show_all(True)
        self.artist_lbl = Gtk.Label()
        self.artist_lbl.get_style_context().add_class("osd-artist")
        self.artist_lbl.set_ellipsize(3)
        self.artist_lbl.set_max_width_chars(28)
        self.artist_lbl.set_no_show_all(True)

        self.bar = Gtk.ProgressBar()
        self.bar.set_size_request(BAR_W, BAR_H)
        self.bar.set_halign(Gtk.Align.CENTER)
        self.bar.set_valign(Gtk.Align.START)
        self.bar.set_margin_bottom(26)

        card.pack_start(self.icon, True, True, 0)
        card.pack_start(self.title_lbl, False, False, 0)
        card.pack_start(self.artist_lbl, False, False, 0)
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
        if kind in MEDIA_KINDS:
            frac, muted = None, False
            icon = MEDIA_KINDS[kind]
            if icon is None:   # playpause: reflect the state we just set
                status = get_player_status()
                icon = {"Playing": "media-playback-start-symbolic",
                        "Paused": "media-playback-pause-symbolic",
                        }.get(status, "media-playback-stop-symbolic")
        else:
            getter, prefix, steps = KINDS[kind]
            try:
                frac, muted = getter()
            except (subprocess.SubprocessError, OSError):
                return
            if kind in ("volume", "mute"):
                self.sink_state = (frac, muted)
            if kind == "brightness":
                icon = "display-brightness-symbolic"
            else:
                icon = _level_icon(prefix, frac, muted, steps)
            if kind == "volume":
                play_tick()
        self.icon.set_from_icon_name(icon, Gtk.IconSize.DIALOG)
        self.icon.set_pixel_size(ICON_PX)
        self.bar.set_opacity(0.0 if frac is None else 1.0)
        if frac is not None:
            self.bar.set_fraction(max(0.0, min(frac, 1.0)))
        ctx = self.card.get_style_context()
        (ctx.add_class if muted else ctx.remove_class)("muted")
        self._present(track=False)

    def show_track(self, title, artist):
        """Now-playing card: music icon + title + artist, no level bar."""
        theme = Gtk.IconTheme.get_default()
        icon = ("emblem-music-symbolic"
                if theme.has_icon("emblem-music-symbolic")
                else "audio-x-generic-symbolic")
        self.icon.set_from_icon_name(icon, Gtk.IconSize.DIALOG)
        self.icon.set_pixel_size(64)
        self.title_lbl.set_text(title)
        self.artist_lbl.set_text(artist)
        self.bar.set_opacity(0.0)
        self.card.get_style_context().remove_class("muted")
        self._present(track=True)

    def _present(self, track):
        self.win.show_all()
        # no_show_all widgets keep their last visibility across show_all
        (self.title_lbl.show if track else self.title_lbl.hide)()
        if track and self.artist_lbl.get_text():
            self.artist_lbl.show()
        else:
            self.artist_lbl.hide()
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


def _default_sink_info():
    """(index, name) of the current default sink, ("", "") if unknown."""
    try:
        name = subprocess.check_output(
            ["/usr/bin/pactl", "get-default-sink"],
            text=True, timeout=3).strip()
        for line in subprocess.check_output(
                ["/usr/bin/pactl", "list", "short", "sinks"],
                text=True, timeout=3).splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] == name:
                return parts[0], name
        return "", name
    except (subprocess.SubprocessError, OSError):
        return "", ""


def watch_sink_changes(osd):
    """Show the OSD also for volume changes that do NOT come from our key
    binds — e.g. bluetooth headset AVRCP buttons, which talk straight to
    PipeWire and never touch the fifo. We follow `pactl subscribe` and pop
    the OSD whenever the default sink's volume/mute actually changed (the
    cache in osd.sink_state filters out the echo of our own binds, which
    already arrived via fifo, and events from non-default sinks).

    The same event stream powers auto-pause: when the sink being removed IS
    the default and is a bluetooth one (headset switched off / out of range),
    pause playback instead of letting it blast on from the speakers."""
    try:
        proc = subprocess.Popen(["/usr/bin/pactl", "subscribe"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
    except OSError as e:
        sys.stderr.write(f"osd.py: pactl subscribe failed: {e}\n")
        return
    try:
        osd.sink_state = get_volume()
    except (subprocess.SubprocessError, OSError):
        pass
    state = {"buf": b"", "default": _default_sink_info(),
             "quiet_until": 0.0}

    def respawn():
        watch_sink_changes(osd)
        return False

    def show_paused():
        osd.show("playpause")
        return False

    def on_data(fd, cond):
        if cond & (GLib.IO_HUP | GLib.IO_ERR):
            # pulse went away (e.g. pipewire restart): retry in a bit
            proc.poll()
            GLib.timeout_add_seconds(2, respawn)
            return False
        try:
            state["buf"] += os.read(fd, 4096)
        except OSError:
            return True
        lines, _, state["buf"] = state["buf"].rpartition(b"\n")
        if b" on sink" not in lines and b" on server" not in lines:
            return True

        # Auto-pause: default bluetooth sink got removed while playing.
        # Deferred check: a profile switch on the SAME headset (a2dp ↔
        # headset-head-unit) also removes the sink, but a sibling
        # bluez_output.<MAC>.* reappears right away — then keep playing.
        idx, name = state["default"]
        removed = re.findall(rb"'remove' on sink #(\d+)", lines)
        if idx and "bluez" in name and idx.encode() in removed:
            state["quiet_until"] = time.monotonic() + 2.0
            parts = name.split(".")
            mac = parts[1] if len(parts) > 1 else ""

            def pause_if_really_gone(mac=mac):
                try:
                    out = subprocess.check_output(
                        ["/usr/bin/pactl", "list", "short", "sinks"],
                        text=True, timeout=3)
                except (subprocess.SubprocessError, OSError):
                    return False
                if mac and f"bluez_output.{mac}" in out:
                    return False   # same headset, new profile: keep playing
                if get_player_status() == "Playing":
                    try:
                        subprocess.Popen(["/usr/bin/playerctl", "pause"],
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
                    except OSError:
                        return False
                    # show the pause card once the pause has taken effect
                    GLib.timeout_add(400, show_paused)
                return False

            GLib.timeout_add(800, pause_if_really_gone)

        if b"'change' on sink" in lines or b"'new' on sink" in lines:
            try:
                cur = get_volume()
            except (subprocess.SubprocessError, OSError):
                cur = None
            if cur is not None and cur != osd.sink_state:
                was_muted = osd.sink_state[1] if osd.sink_state else cur[1]
                osd.sink_state = cur
                if time.monotonic() >= state["quiet_until"]:
                    # mute toggles stay silent (like the XF86AudioMute bind)
                    osd.show("mute" if cur[1] != was_muted else "volume")

        state["default"] = _default_sink_info()
        return True

    GLib.io_add_watch(proc.stdout.fileno(), GLib.PRIORITY_DEFAULT,
                      GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, on_data)


TRACK_FMT = "{{title}}\x1e{{artist}}"


def watch_track_changes(osd):
    """Now-playing card on track change, following playerctl metadata. The
    cache is primed with the current track so a daemon (re)start does not
    pop the OSD; duplicate emissions (artUrl arriving late, status flips)
    are deduped on the formatted title+artist line."""
    try:
        proc = subprocess.Popen(
            ["/usr/bin/playerctl", "--follow", "metadata",
             "--format", TRACK_FMT],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError as e:
        sys.stderr.write(f"osd.py: playerctl --follow failed: {e}\n")
        return
    state = {"buf": b"", "last": None}
    try:
        state["last"] = subprocess.check_output(
            ["/usr/bin/playerctl", "metadata", "--format", TRACK_FMT],
            text=True, timeout=3, stderr=subprocess.DEVNULL).strip()
    except (subprocess.SubprocessError, OSError):
        pass

    def respawn():
        watch_track_changes(osd)
        return False

    def on_data(fd, cond):
        if cond & (GLib.IO_HUP | GLib.IO_ERR):
            proc.poll()
            GLib.timeout_add_seconds(5, respawn)
            return False
        try:
            state["buf"] += os.read(fd, 4096)
        except OSError:
            return True
        lines, _, state["buf"] = state["buf"].rpartition(b"\n")
        for raw in lines.splitlines():
            line = raw.decode(errors="replace").strip()
            if not line or line == state["last"]:
                continue
            state["last"] = line
            title, _, artist = line.partition("\x1e")
            if title.strip():
                osd.show_track(title.strip(), artist.strip())
        return True

    GLib.io_add_watch(proc.stdout.fileno(), GLib.PRIORITY_DEFAULT,
                      GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, on_data)


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
    watch_sink_changes(osd)
    watch_track_changes(osd)

    def on_data(_fd, _cond):
        try:
            data = os.read(fd, 1024).decode(errors="replace")
        except OSError:
            return True
        for tok in data.split():
            if tok in KINDS or tok in MEDIA_KINDS:
                osd.show(tok)
            elif tok == "track":   # show the current track on demand
                try:
                    line = subprocess.check_output(
                        ["/usr/bin/playerctl", "metadata",
                         "--format", TRACK_FMT],
                        text=True, timeout=3,
                        stderr=subprocess.DEVNULL).strip()
                except (subprocess.SubprocessError, OSError):
                    continue
                title, _, artist = line.partition("\x1e")
                if title.strip():
                    osd.show_track(title.strip(), artist.strip())
        return True

    GLib.io_add_watch(fd, GLib.PRIORITY_DEFAULT, GLib.IO_IN, on_data)
    Gtk.main()


if __name__ == "__main__":
    main()
