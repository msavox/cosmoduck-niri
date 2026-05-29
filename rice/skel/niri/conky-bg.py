#!/usr/bin/python3
"""
conky-bg.py — X11 -> Wayland layer-shell bridge for the Conky widget on niri.

The problem: niri (26.04) has no "below tile" layer for normal windows,
so conky always ends up above the apps. Solution: we capture conky's X11
output via XComposite and blit it onto a gtk-layer-shell surface on the
BACKGROUND layer (below everything, above the wallpaper). The apps appear ABOVE the widget.

Components:
- python-xlib: find the Conky window, redirect via XComposite, listen for Damage
- gtk-layer-shell: surface anchored top-left, layer BACKGROUND, exclusive_zone=0
- Cairo: blit the X11 pixmap onto the draw area
- GLib io_add_watch on the X11 fd to integrate the two event loops

It does not touch the conky configs. It launches AFTER conky (niri's spawn-at-startup
keeps the order, conky starts 3s after init and this wrapper waits for the
window to show up before drawing).
"""

import os
import struct
import sys
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import GLib, Gtk, GtkLayerShell  # noqa: E402

from Xlib import X, display, error  # noqa: E402
from Xlib.ext import composite, damage, shape  # noqa: E402

CONKY_CLASS = "Conky"
LAYER_MARGIN_TOP = 14      # room for the top waybar
LAYER_MARGIN_LEFT = 1      # match gap_x from the .conf
POLL_INTERVAL_MS = 200     # unconditional repaint (~5 fps): see on_timer
SEARCH_INTERVAL_MS = 500   # search for conky if it isn't there yet


def find_conky_window(dpy):
    """Find the first X11 window with WM_CLASS 'Conky'. None if absent."""
    root = dpy.screen().root
    queue = [root]
    while queue:
        win = queue.pop()
        try:
            wm_class = win.get_wm_class()
            if wm_class and CONKY_CLASS in wm_class:
                return win
            tree = win.query_tree()
            queue.extend(tree.children)
        except (error.BadWindow, error.BadDrawable):
            continue
    return None


class ConkyBridge:
    def __init__(self):
        self.dpy = display.Display()
        self.conky_win = None
        self.pixmap = None
        self.damage_id = None
        self.win_w = 0
        self.win_h = 0
        self.dirty = True

        # Check extensions
        if not self.dpy.has_extension("Composite"):
            sys.exit("[conky-bg] X server without XComposite, abort.")
        if not self.dpy.has_extension("DAMAGE"):
            sys.exit("[conky-bg] X server without XDamage, abort.")
        # init the extensions (python-xlib uses hardcoded versions)
        composite.query_version(self.dpy)
        damage.query_version(self.dpy)

        # ── GTK layer-shell window ───────────────────────────────────
        self.gtk_win = Gtk.Window()
        self.gtk_win.set_app_paintable(True)

        screen = self.gtk_win.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.gtk_win.set_visual(visual)

        GtkLayerShell.init_for_window(self.gtk_win)
        GtkLayerShell.set_namespace(self.gtk_win, "conky-bg")
        # Layer BOTTOM (not BACKGROUND): above the wallpaper, below the apps.
        # On BACKGROUND the surface shares the layer with swaybg and the order is
        # by creation: on every wallpaper change gnome-wallpaper-sync restarts
        # swaybg, whose new surface stacks ABOVE conky-bg -> conky disappears.
        # On BOTTOM conky always stays above any BACKGROUND surface (wallpaper)
        # regardless of swaybg respawns.
        GtkLayerShell.set_layer(self.gtk_win, GtkLayerShell.Layer.BOTTOM)
        GtkLayerShell.set_anchor(self.gtk_win, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self.gtk_win, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_margin(
            self.gtk_win, GtkLayerShell.Edge.TOP, LAYER_MARGIN_TOP
        )
        GtkLayerShell.set_margin(
            self.gtk_win, GtkLayerShell.Edge.LEFT, LAYER_MARGIN_LEFT
        )
        # Exclusive zone 0: does not steal space from tiled windows
        GtkLayerShell.set_exclusive_zone(self.gtk_win, 0)
        GtkLayerShell.set_keyboard_mode(
            self.gtk_win, GtkLayerShell.KeyboardMode.NONE
        )

        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect("draw", self.on_draw)
        self.gtk_win.add(self.drawing_area)

        # X11 fd -> GLib watch so X events wake the main loop
        GLib.io_add_watch(
            self.dpy.fileno(),
            GLib.IO_IN,
            self.on_x_event,
        )
        # Safety repaint timer (some XComposite drivers don't always damage-fire)
        GLib.timeout_add(POLL_INTERVAL_MS, self.on_timer)

        # Search for conky periodically until we find it (it may start later)
        GLib.timeout_add(SEARCH_INTERVAL_MS, self.try_attach)

    # ─── X11 attach / detach ─────────────────────────────────────────
    def try_attach(self):
        if self.conky_win is not None:
            return False  # already attached, stop the timer
        win = find_conky_window(self.dpy)
        if win is None:
            return True   # retry
        self._attach(win)
        return False

    def _attach(self, win):
        try:
            geom = win.get_geometry()
        except error.BadWindow:
            return
        self.conky_win = win
        self.win_w = geom.width
        self.win_h = geom.height
        print(
            f"[conky-bg] attached: xid={win.id:#x} size={self.win_w}x{self.win_h}",
            file=sys.stderr,
        )

        # No RedirectWindow: xwayland-satellite already has the redirect active
        # on all X11 toplevel windows (it is the WM). Attempting a second
        # redirect gives BadAccess. Piggyback: NameWindowPixmap works anyway
        # because the window is already redirected — we read the same pixmap that
        # xwayland-satellite hands to niri as a Wayland buffer.
        self.pixmap = composite.name_window_pixmap(win)

        # Damage: NotifyBoundingBox -> one event per redraw, enough for us
        self.damage_id = win.damage_create(damage.DamageReportBoundingBox)

        # Click-through of the invisible toplevel. In niri conky's toplevel
        # has opacity 0.0 (window-rule) but stays INTERACTIVE: the opacity is only
        # visual. Without this, the invisible X11 window (~win_w x win_h at the
        # top left of the workspace) intercepts the pointer events -> the cursor
        # changes and clicks don't reach the app below. We clear the INPUT shape
        # of the X window (empty rectangle list): Xwayland translates it into an
        # empty Wayland input-region -> niri routes the clicks to the app underneath.
        # It does not touch the rendering: the offscreen pixmap keeps updating.
        if self.dpy.has_extension("SHAPE"):
            try:
                win.shape_rectangles(
                    shape.SO.Set, shape.SK.Input, 0, 0, 0, []
                )
            except Exception as e:  # noqa: BLE001
                print(
                    f"[conky-bg] shape input clear failed: {e}", file=sys.stderr
                )

        # Events of interest
        win.change_attributes(
            event_mask=X.StructureNotifyMask | X.PropertyChangeMask
        )
        self.dpy.flush()

        # Fit the GTK window to conky's size
        self.gtk_win.set_size_request(self.win_w, self.win_h)
        self.gtk_win.show_all()
        # Click-through: on the BOTTOM layer the surface would receive pointer
        # events in its area (on BACKGROUND it wouldn't). Empty input region -> clicks
        # pass to the windows/desktop below. Requires the GdkWindow realized
        # (show_all just created it).
        gdk_win = self.gtk_win.get_window()
        if gdk_win is not None:
            gdk_win.input_shape_combine_region(cairo.Region(), 0, 0)
        self.dirty = True
        self.drawing_area.queue_draw()

    def _detach(self):
        print("[conky-bg] conky window gone, detaching", file=sys.stderr)
        if self.damage_id is not None:
            try:
                damage.destroy(self.damage_id)
            except Exception:
                pass
            self.damage_id = None
        self.pixmap = None
        self.conky_win = None
        self.gtk_win.hide()
        # retry re-attaching when conky reappears
        GLib.timeout_add(SEARCH_INTERVAL_MS, self.try_attach)

    # ─── X event pump ────────────────────────────────────────────────
    def on_x_event(self, fd, _cond):
        while self.dpy.pending_events():
            ev = self.dpy.next_event()
            et = ev.type
            # Damage event -> redraw
            if self.damage_id is not None and et == self.dpy.extension_event.DamageNotify:
                self.dirty = True
                self.drawing_area.queue_draw()
                # subtract the damage to receive the next one
                try:
                    damage.subtract(self.damage_id, X.NONE, X.NONE)
                except Exception:
                    pass
            elif et == X.ConfigureNotify and self.conky_win is not None:
                if ev.window == self.conky_win and (
                    ev.width != self.win_w or ev.height != self.win_h
                ):
                    self.win_w = ev.width
                    self.win_h = ev.height
                    self.gtk_win.set_size_request(self.win_w, self.win_h)
                    # re-name the pixmap (it changes on resize)
                    try:
                        self.pixmap = composite.name_window_pixmap(self.conky_win)
                    except Exception:
                        pass
                    self.dirty = True
                    self.drawing_area.queue_draw()
            elif et == X.DestroyNotify or et == X.UnmapNotify:
                if self.conky_win is not None and ev.window == self.conky_win:
                    self._detach()
        return True  # keep the watch

    # ─── Safety repaint timer ────────────────────────────────────────
    def on_timer(self):
        # Unconditional repaint. Conky runs with double_buffer = true: the
        # back-buffer swap does not always generate XDamage on the window, so
        # relying on damage alone "freezes" the compositing. Here we re-read the
        # pixmap on every tick, so cpu/ram/rings update regardless.
        if self.conky_win is not None and self.pixmap is not None:
            self.drawing_area.queue_draw()
        return True

    # ─── Cairo draw ──────────────────────────────────────────────────
    def on_draw(self, area, cr):
        if self.pixmap is None or self.win_w <= 0 or self.win_h <= 0:
            return False
        try:
            img = self.pixmap.get_image(
                0, 0, self.win_w, self.win_h, X.ZPixmap, 0xFFFFFFFF
            )
        except (error.BadDrawable, error.BadMatch) as e:
            print(f"[conky-bg] get_image failed: {e}", file=sys.stderr)
            return False

        raw = img.data
        if not isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw)
        stride = self.win_w * 4
        # Cairo ARGB32 on x86 little-endian = BGRA in memory, like X ZPixmap depth=32
        try:
            surface = cairo.ImageSurface.create_for_data(
                bytearray(raw), cairo.FORMAT_ARGB32,
                self.win_w, self.win_h, stride,
            )
        except (ValueError, MemoryError) as e:
            print(f"[conky-bg] cairo surface error: {e}", file=sys.stderr)
            return False
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_surface(surface, 0, 0)
        cr.paint()
        self.dirty = False
        return False

    def run(self):
        Gtk.main()


def main():
    # Force the WAYLAND backend for GTK (it might inherit X11 if DISPLAY is set)
    if "GDK_BACKEND" not in os.environ:
        os.environ["GDK_BACKEND"] = "wayland"
    # Wait a moment for xwayland-satellite and niri to be ready
    time.sleep(0.5)
    bridge = ConkyBridge()
    bridge.run()


if __name__ == "__main__":
    main()
