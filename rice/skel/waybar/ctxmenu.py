#!/usr/bin/python3
"""
ctxmenu.py — reusable context-menu framework for the Cosmoduck niri shell.

A context menu rendered as a full-screen, transparent gtk-layer-shell overlay on
a target monitor. EVERY click reaches our surface: a click on the menu card
activates an item, a click anywhere else dismisses the menu. No seat grab is
used — a grab that failed to release would lock the pointer/keyboard, so this
design can never get the input stuck. Esc and a hard safety timeout are extra
exits. This is the shared foundation for every right-click menu in the shell
(the dock icons today; the desktop, the panel, … tomorrow).

Usage:
    from ctxmenu import ContextMenu
    m = ContextMenu(title="Firefox")
    m.add_item("New Window", on_new, icon="window-new")
    m.add_separator()
    m.add_item("Force Quit", on_kill, icon="process-stop", danger=True)
    m.popup(anchor_x=1234)   # center the card on this monitor-local x...
    # m.popup()              # ...or, with no anchor, centered above the dock.

Run the consumer with /usr/bin/python3 so GIR typelibs resolve without env tweaks.
"""

import json
import subprocess

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell  # noqa: E402
    HAVE_LAYER_SHELL = True
except (ValueError, ImportError):
    HAVE_LAYER_SHELL = False

_CSS = b"""
window { background: transparent; }
.ctxmenu-card {
  background: rgba(30, 30, 46, 0.96);
  border: 1px solid #494d64;
  border-radius: 16px;
}
.ctxmenu-header {
  color: #8aadf4;
  font-weight: bold;
  font-size: 12px;
  padding: 6px 12px 2px 12px;
}
.ctxmenu-card button {
  padding: 7px 14px 7px 10px;
  margin: 1px 6px;
  min-height: 0;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: #cad3f5;
  font-family: "Inter", "Roboto", "Ubuntu", "Noto Sans", sans-serif;
  font-size: 13px;
}
.ctxmenu-card button label { color: #cad3f5; }
.ctxmenu-card button:hover { background: rgba(138, 173, 244, 0.18); }
.ctxmenu-card button.danger:hover { background: rgba(237, 135, 150, 0.22); }
.ctxmenu-card button.danger:hover label { color: #ed8796; }
.ctxmenu-card separator {
  background: #494d64;
  min-height: 1px;
  margin: 4px 10px;
}
"""

_css_installed = False


def _install_css():
    global _css_installed
    if _css_installed:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(_CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    _css_installed = True


def focused_monitor():
    """Return (GdkMonitor|None, x, width) for niri's focused output, so a menu
    lands on the screen the user is actually looking at."""
    try:
        out = json.loads(subprocess.check_output(
            ["niri", "msg", "--json", "focused-output"], text=True))
        mx = out["logical"]["x"]
        mw = out["logical"]["width"]
    except Exception:
        disp = Gdk.Display.get_default()
        mon = disp.get_primary_monitor() or disp.get_monitor(0)
        geo = mon.get_geometry() if mon else None
        return mon, (geo.x if geo else 0), (geo.width if geo else 1920)
    disp = Gdk.Display.get_default()
    for i in range(disp.get_n_monitors()):
        mon = disp.get_monitor(i)
        geo = mon.get_geometry()
        if geo.x == mx:
            return mon, mx, mw
    return None, mx, mw


class ContextMenu:
    """A themed, self-dismissing context menu. Build with add_*; show with popup."""

    def __init__(self, title=None, width=210, bottom_margin=72, autoclose_ms=15000):
        self.title = title
        self.width = width
        self.bottom_margin = bottom_margin
        self.autoclose_ms = autoclose_ms
        self._rows = []  # list of ("item"|"sep", payload)

    def add_item(self, label, callback, icon=None, danger=False):
        self._rows.append(("item", (label, callback, icon, danger)))
        return self

    def add_separator(self):
        self._rows.append(("sep", None))
        return self

    # ── rendering ──────────────────────────────────────────────────────
    def _build_card(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.get_style_context().add_class("ctxmenu-card")
        card.set_margin_top(4)
        card.set_margin_bottom(6)
        card.set_size_request(self.width, -1)

        if self.title:
            hdr = Gtk.Label(label=self.title, xalign=0.0)
            hdr.get_style_context().add_class("ctxmenu-header")
            card.pack_start(hdr, False, False, 0)

        for kind, payload in self._rows:
            if kind == "sep":
                card.pack_start(Gtk.Separator(), False, False, 0)
                continue
            label, callback, icon, danger = payload
            card.pack_start(self._make_button(label, callback, icon, danger),
                            False, False, 0)
        return card

    def _make_button(self, label, callback, icon, danger):
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        if danger:
            btn.get_style_context().add_class("danger")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        if icon:
            row.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU),
                           False, False, 0)
        lbl = Gtk.Label(label=label, xalign=0.0)
        lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        lbl.set_max_width_chars(28)
        row.pack_start(lbl, True, True, 0)
        btn.add(row)

        def on_clicked(_w):
            self._close()
            try:
                callback()
            except Exception as e:  # never let a handler wedge the menu open
                print(f"[ctxmenu] item '{label}' failed: {e}")
        btn.connect("clicked", on_clicked)
        return btn

    def _close(self, *_):
        if self._win is not None:
            self._win.destroy()
            self._win = None
        Gtk.main_quit()

    # ── show ───────────────────────────────────────────────────────────
    def popup(self, anchor_x=None, monitor=None):
        _install_css()
        self._win = win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_decorated(False)
        win.set_app_paintable(True)
        screen = win.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            win.set_visual(visual)
        win.set_title("dock-menu")  # app-id for any compositor rule

        card = self._build_card()

        mon, mx, mw = (monitor, 0, 1920) if monitor else focused_monitor()

        if HAVE_LAYER_SHELL:
            GtkLayerShell.init_for_window(win)
            if mon is not None:
                GtkLayerShell.set_monitor(win, mon)
            GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.ON_DEMAND)
            # Fill the whole output so every click is delivered to us.
            for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                         GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
                GtkLayerShell.set_anchor(win, edge, True)
            GtkLayerShell.set_exclusive_zone(win, -1)

        # Position the card within the full-screen overlay.
        card.set_valign(Gtk.Align.END)
        card.set_margin_bottom(self.bottom_margin)
        if anchor_x is not None:
            left = int(anchor_x - self.width / 2)
            left = max(4, min(left, int(mw) - self.width - 4))
            card.set_halign(Gtk.Align.START)
            card.set_margin_start(left)
        else:
            card.set_halign(Gtk.Align.CENTER)

        win.add(card)
        self._card = card

        # Dismiss on a click outside the card.
        win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)

        def on_press(_w, ev):
            a = card.get_allocation()
            inside = (a.x <= ev.x <= a.x + a.width and
                      a.y <= ev.y <= a.y + a.height)
            if not inside:
                self._close()
                return True
            return False
        win.connect("button-press-event", on_press)

        def on_key(_w, ev):
            if ev.keyval == Gdk.KEY_Escape:
                self._close()
                return True
            return False
        win.connect("key-press-event", on_key)
        win.connect("destroy", lambda *_: Gtk.main_quit())

        # Hard safety net: the menu can never get stuck open.
        if self.autoclose_ms:
            GLib.timeout_add(self.autoclose_ms, lambda: (self._close(), False)[1])

        win.show_all()
        Gtk.main()
