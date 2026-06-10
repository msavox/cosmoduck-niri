#!/usr/bin/python3
"""
ctxmenu.py — reusable context-menu framework for the Cosmoduck niri shell.

A context menu rendered as a full-screen, transparent gtk-layer-shell overlay on
a target monitor. EVERY click reaches our surface: a click on a card activates an
item, a click anywhere else dismisses the menu. No seat grab is used — a grab that
failed to release would lock the pointer/keyboard, so this design can never get the
input stuck. Esc and a hard safety timeout are extra exits. This is the shared
foundation for every right-click menu in the shell (dock, tray, desktop, …).

Icons are drawn from the icon theme's *symbolic* variants and recolored by the CSS
below, so every menu looks monochrome and on-theme regardless of the icon a caller
passes. Second-level submenus are supported via add_submenu().

Usage:
    from ctxmenu import ContextMenu
    m = ContextMenu(title="Firefox")
    m.add_item("New Window", on_new, icon="window-new")
    sub = m.add_submenu("Icon Size", icon="zoom-in")
    sub.add_item("Small", on_small)
    m.add_separator()
    m.add_item("Force Quit", on_kill, icon="process-stop", danger=True)
    m.popup(anchor_x=1234)             # centered above the dock, x-anchored...
    # m.popup(anchor_x=x, anchor_y=y)  # ...or top-left at the cursor (desktop).

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
/* Monochrome, on-theme symbolic icons; recolored to this single accent. */
.ctxmenu-card button image {
  -gtk-icon-style: symbolic;
  color: #a5adce;
}
.ctxmenu-card button:hover { background: rgba(138, 173, 244, 0.18); }
.ctxmenu-card button:hover image { color: #8aadf4; }
.ctxmenu-card button.danger:hover { background: rgba(237, 135, 150, 0.22); }
.ctxmenu-card button.danger:hover label { color: #ed8796; }
.ctxmenu-card button.danger:hover image { color: #ed8796; }
.ctxmenu-chevron { color: #6e738d; }
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


def _symbolic_image(name):
    """A menu image using the symbolic variant of `name` when the theme has one,
    so the CSS above can recolor it to a single monochrome accent."""
    if not name:
        return None
    theme = Gtk.IconTheme.get_default()
    sym = name if name.endswith("-symbolic") else name + "-symbolic"
    use = sym if theme.has_icon(sym) else name
    return Gtk.Image.new_from_icon_name(use, Gtk.IconSize.MENU)


def _translate(src, dest):
    """src-widget origin in dest-widget coords, tolerating either PyGObject
    return shape ((x, y) or (ok, x, y))."""
    res = src.translate_coordinates(dest, 0, 0)
    if not res:
        return (0, 0)
    return (res[1], res[2]) if len(res) == 3 else (res[0], res[1])


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
        self._rows = []  # ("item"|"sep"|"submenu", payload)
        self._win = None
        self._fixed = None
        self._cards = []          # open cards, for click-outside hit-testing
        self._open_sub = None     # the child ContextMenu currently flown out
        self._flyout = None

    def add_item(self, label, callback, icon=None, danger=False):
        self._rows.append(("item", (label, callback, icon, danger)))
        return self

    def add_separator(self):
        self._rows.append(("sep", None))
        return self

    def add_submenu(self, label, icon=None):
        """Add a second-level submenu; returns a ContextMenu to populate."""
        child = ContextMenu(width=self.width, autoclose_ms=0)
        self._rows.append(("submenu", (label, icon, child)))
        return child

    def _estimate_height(self):
        """Rough card height (px) before allocation, to keep a menu on screen."""
        n_items = sum(1 for k, _ in self._rows if k in ("item", "submenu"))
        n_sep = sum(1 for k, _ in self._rows if k == "sep")
        h = n_items * 34 + n_sep * 9 + 12
        if self.title:
            h += 26
        return h

    # ── rendering ──────────────────────────────────────────────────────
    def _build_card(self, rows=None, title=None):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.get_style_context().add_class("ctxmenu-card")
        card.set_margin_top(4)
        card.set_margin_bottom(6)
        card.set_size_request(self.width, -1)

        if title:
            hdr = Gtk.Label(label=title, xalign=0.0)
            hdr.get_style_context().add_class("ctxmenu-header")
            card.pack_start(hdr, False, False, 0)

        for kind, payload in (rows if rows is not None else self._rows):
            if kind == "sep":
                card.pack_start(Gtk.Separator(), False, False, 0)
            elif kind == "submenu":
                label, icon, child = payload
                card.pack_start(self._make_submenu_button(label, icon, child),
                                False, False, 0)
            else:
                label, callback, icon, danger = payload
                card.pack_start(self._make_button(label, callback, icon, danger),
                                False, False, 0)
        return card

    def _row(self, icon, label, danger=False, chevron=False):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        img = _symbolic_image(icon)
        if img is not None:
            row.pack_start(img, False, False, 0)
        lbl = Gtk.Label(label=label, xalign=0.0)
        lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        lbl.set_max_width_chars(28)
        row.pack_start(lbl, True, True, 0)
        if chevron:
            ch = Gtk.Label(label="›")  # ›
            ch.get_style_context().add_class("ctxmenu-chevron")
            row.pack_start(ch, False, False, 0)
        return row

    def _make_button(self, label, callback, icon, danger):
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        if danger:
            btn.get_style_context().add_class("danger")
        btn.add(self._row(icon, label, danger))

        def on_clicked(_w):
            self._close()
            try:
                callback()
            except Exception as e:  # never let a handler wedge the menu open
                print(f"[ctxmenu] item '{label}' failed: {e}")
        btn.connect("clicked", on_clicked)
        return btn

    def _make_submenu_button(self, label, icon, child):
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.add(self._row(icon, label, chevron=True))
        btn.connect("clicked", lambda _w: self._toggle_submenu(btn, child))
        return btn

    def _toggle_submenu(self, parent_btn, child):
        if self._open_sub is child:
            self._close_flyout()
            return
        self._close_flyout()
        flyout = self._build_card(rows=child._rows, title=child.title)
        # Position to the right of the parent row, or to the left if no room.
        px, py = _translate(parent_btn, self._fixed)
        cw = self.width
        ch = child._estimate_height()
        left = px + cw - 8
        if left + cw > self._mw - 4:
            left = px - cw + 8
        left = max(4, min(left, self._mw - cw - 4))
        top = max(4, min(py - 4, self._mh - ch - 4))
        self._fixed.put(flyout, left, top)
        flyout.show_all()
        self._flyout = flyout
        self._open_sub = child
        self._cards = [self._card, flyout]

    def _close_flyout(self):
        if self._flyout is not None:
            self._flyout.destroy()
            self._flyout = None
        self._open_sub = None
        self._cards = [self._card] if self._card is not None else []

    def _close(self, *_):
        if self._win is not None:
            self._win.destroy()
            self._win = None
        Gtk.main_quit()

    # ── show ───────────────────────────────────────────────────────────
    def popup(self, anchor_x=None, monitor=None, anchor_y=None):
        _install_css()
        self._win = win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_decorated(False)
        win.set_app_paintable(True)
        screen = win.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            win.set_visual(visual)
        win.set_title("ctxmenu")  # app-id for any compositor rule

        self._card = card = self._build_card()

        if monitor is not None:
            mon = monitor
            geo = mon.get_geometry()
            mx, mw, mh = geo.x, geo.width, geo.height
        else:
            mon, mx, mw = focused_monitor()
            try:
                mh = mon.get_geometry().height if mon is not None else 1080
            except Exception:
                mh = 1080
        self._mw, self._mh = int(mw), int(mh)

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

        # Compute the main card's absolute top-left, then lay it in a Fixed so a
        # submenu flyout can be positioned beside it within the same overlay.
        est_h = self._estimate_height()
        if anchor_y is not None:
            left = int(anchor_x if anchor_x is not None else 0)
            top = int(anchor_y)
        elif anchor_x is not None:
            left = int(anchor_x - self.width / 2)
            top = self._mh - self.bottom_margin - est_h
        else:
            left = int((self._mw - self.width) / 2)
            top = self._mh - self.bottom_margin - est_h
        left = max(4, min(left, self._mw - self.width - 4))
        top = max(4, min(top, self._mh - est_h - 4))

        self._fixed = Gtk.Fixed()
        self._fixed.put(card, left, top)
        win.add(self._fixed)
        self._cards = [card]

        # Dismiss on a click outside every open card.
        win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)

        def on_press(_w, ev):
            for c in self._cards:
                a = c.get_allocation()
                if a.x <= ev.x <= a.x + a.width and a.y <= ev.y <= a.y + a.height:
                    return False
            self._close()
            return True
        win.connect("button-press-event", on_press)

        def on_key(_w, ev):
            if ev.keyval == Gdk.KEY_Escape:
                if self._open_sub is not None:
                    self._close_flyout()
                else:
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
