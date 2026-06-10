#!/usr/bin/python3
"""
app-grid.py — Launchpad-style application grid for the Cosmoduck niri shell.

A centered, NON-fullscreen grid of all installed apps (macOS Launchpad / GNOME
app drawer feel), bound to the Ubuntu icon in the waybar top bar. It is an
alternative to ulauncher (which keeps its own hotkeys), and deliberately wears
the same look as ulauncher's "macos" theme: dark translucent card, soft
hairline border, large rounded corners, white-on-dark items.

Behaviour:
  • type to filter, Enter launches the selection (or the first match)
  • arrows navigate, Esc or a click outside the card closes
  • running it again toggles the previous instance off (waybar on-click)

Overlay pattern as ctxmenu.py: full-output transparent layer-shell surface
catching every click; no seat grab, hard safety timeout as a last resort.

Run with /usr/bin/python3 so the GIR typelibs resolve without env tweaks.
"""

import os
import signal
import subprocess
import sys

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Gio, GLib, Pango  # noqa: E402

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell  # noqa: E402
except (ValueError, ImportError):
    sys.stderr.write("app-grid.py: gtk-layer-shell not available\n")
    sys.exit(1)

CARD_W, CARD_H = 940, 640
ICON_PX = 56
AUTOCLOSE_MS = 90000  # safety net: the keyboard is EXCLUSIVE while open

# Mirrors ulauncher's "macos" theme (user-themes/macos/theme.css).
_CSS = b"""
window { background: transparent; }
.appgrid-card {
  background: rgba(36, 36, 38, 0.94);
  /* The bezel: same ring niri draws around the focused window (focus-ring
     width 3, #8aadf4). A layer-shell surface never gets niri's own ring, so
     the card paints it itself; that is what makes it match ulauncher. */
  border: 3px solid #8aadf4;
  border-radius: 32px;
  box-shadow: 0 18px 50px 8px rgba(0, 0, 0, 0.55);
  padding: 8px;
}
.appgrid-search {
  color: #f5f5f7;
  caret-color: #7ab7ff;
  font-size: 150%;
  font-weight: 300;
  padding: 12px 16px;
  margin: 14px 18px 6px 18px;
  background: rgba(255, 255, 255, 0.07);
  border: none;
  border-radius: 14px;
  outline: none;
  box-shadow: none;
}
.appgrid-search:focus {
  border: none;
  outline: none;
  box-shadow: none;
}
.appgrid-card scrolledwindow { border: none; background: transparent; }
flowbox, flowboxchild { background: transparent; }
flowboxchild {
  border-radius: 14px;
  padding: 8px 4px;
}
flowboxchild:hover { background: rgba(255, 255, 255, 0.07); }
flowboxchild:selected { background: rgba(255, 255, 255, 0.12); }
.appgrid-label {
  color: #e8e8ea;
  font-size: 12px;
}
"""


def _instances():
    """Pids of other real app-grid pythons (comm-filtered: a shell whose
    command line merely contains the pattern must not match)."""
    me = os.getpid()
    try:
        out = subprocess.check_output(["pgrep", "-f", r"python3 .*app-grid\.py"],
                                      text=True)
    except subprocess.CalledProcessError:
        return []
    pids = []
    for tok in out.split():
        pid = int(tok)
        if pid == me:
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip().startswith("python"):
                    pids.append(pid)
        except OSError:
            continue
    return pids


def toggle_off_if_running():
    """Second invocation (waybar click) kills the first → toggle behaviour.
    SIGTERM first; SIGKILL any survivor — a grid wedged in a Wayland roundtrip
    (e.g. mapped while the session is locked) never dispatches GLib sources."""
    import time
    pids = _instances()
    if not pids:
        return False
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(0.4)
    for pid in _instances():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return True


def list_apps():
    apps = []
    for ai in Gio.AppInfo.get_all():
        if not ai.should_show():
            continue
        apps.append(ai)
    apps.sort(key=lambda a: (a.get_display_name() or "").lower())
    return apps


class AppGrid:
    def __init__(self):
        self._build()

    def _build(self):
        self.win = win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_decorated(False)
        win.set_app_paintable(True)
        visual = win.get_screen().get_rgba_visual()
        if visual is not None:
            win.set_visual(visual)
        win.set_title("app-grid")

        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(win, edge, True)
        GtkLayerShell.set_exclusive_zone(win, -1)

        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.get_style_context().add_class("appgrid-card")
        card.set_size_request(CARD_W, CARD_H)
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)

        self.search = Gtk.SearchEntry()
        self.search.get_style_context().add_class("appgrid-search")
        self.search.set_placeholder_text("Search apps…")
        self.search.connect("search-changed", lambda *_: self.flow.invalidate_filter())
        self.search.connect("activate", self._launch_first)
        card.pack_start(self.search, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.flow = Gtk.FlowBox()
        self.flow.set_valign(Gtk.Align.START)
        self.flow.set_max_children_per_line(6)
        self.flow.set_min_children_per_line(6)
        self.flow.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flow.set_activate_on_single_click(True)
        self.flow.set_margin_start(14)
        self.flow.set_margin_end(14)
        self.flow.set_margin_bottom(14)
        self.flow.connect("child-activated", self._on_activated)
        self.flow.set_filter_func(self._filter)
        scroller.add(self.flow)
        card.pack_start(scroller, True, True, 0)

        for ai in list_apps():
            self.flow.add(self._make_tile(ai))

        win.add(card)
        self._card = card

        win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        win.connect("button-press-event", self._on_press)
        win.connect("key-press-event", self._on_key)
        win.connect("destroy", lambda *_: Gtk.main_quit())
        GLib.timeout_add(AUTOCLOSE_MS, lambda: (self._close(), False)[1])

    def _make_tile(self, ai):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_size_request(132, -1)
        img = Gtk.Image()
        gicon = ai.get_icon()
        if gicon is not None:
            img.set_from_gicon(gicon, Gtk.IconSize.DIALOG)
        else:
            img.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
        img.set_pixel_size(ICON_PX)
        lbl = Gtk.Label(label=ai.get_display_name() or "")
        lbl.get_style_context().add_class("appgrid-label")
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_line_wrap(True)
        lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        lbl.set_lines(2)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        lbl.set_max_width_chars(16)
        box.pack_start(img, False, False, 0)
        box.pack_start(lbl, False, False, 0)
        box._appinfo = ai
        box._needle = " ".join(filter(None, [
            ai.get_display_name() or "", ai.get_name() or "",
            ai.get_executable() or "",
            " ".join(ai.get_keywords() or [])])).lower()
        return box

    # ── behaviour ──────────────────────────────────────────────────────
    def _filter(self, child):
        text = self.search.get_text().strip().lower()
        if not text:
            return True
        return text in child.get_child()._needle

    def _launch(self, ai):
        self._close()
        try:
            ai.launch([], None)
        except GLib.Error as e:
            sys.stderr.write(f"app-grid: launch failed: {e}\n")

    def _on_activated(self, flow, child):
        self._launch(child.get_child()._appinfo)

    def _launch_first(self, *_):
        sel = self.flow.get_selected_children()
        if sel:
            self._launch(sel[0].get_child()._appinfo)
            return
        for child in self.flow.get_children():
            if child.get_mapped() and self._filter(child):
                self._launch(child.get_child()._appinfo)
                return

    def _on_press(self, _w, ev):
        a = self._card.get_allocation()
        if not (a.x <= ev.x <= a.x + a.width and a.y <= ev.y <= a.y + a.height):
            self._close()
            return True
        return False

    def _on_key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self._close()
            return True
        return False

    def _close(self, *_):
        if self.win is not None:
            self.win.destroy()
            self.win = None
        Gtk.main_quit()

    def run(self):
        self.win.show_all()
        self.search.grab_focus()
        Gtk.main()


def main():
    if toggle_off_if_running():
        return
    # signal.signal() handlers don't fire while blocked in the C main loop;
    # GLib.unix_signal_add integrates with it, so SIGTERM (= toggle) works.
    # Registered BEFORE the (slow) grid construction so a toggle that lands
    # mid-build is not lost.
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM,
                         lambda *_: (Gtk.main_quit(), False)[1])
    AppGrid().run()


if __name__ == "__main__":
    main()
