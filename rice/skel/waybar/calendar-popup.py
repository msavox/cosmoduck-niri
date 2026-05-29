#!/usr/bin/env python3
"""Calendar popup — current month under the clock. Double-click a day → gnome-calendar."""
import subprocess
import sys

import gi
gi.require_version("Gtk", "3.0")
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False
from gi.repository import Gtk, Gio, Gdk  # noqa: E402

WAYBAR_HEIGHT = 30

CSS = b"""
window.calendar-popup,
.calendar-popup decoration {
  background: transparent;
}
.calendar-popup-inner {
  background: rgba(30, 30, 46, 0.96);
  border: 1px solid rgba(73, 77, 100, 0.6);
  border-radius: 14px;
  padding: 4px 10px 8px 10px;
  color: #cad3f5;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
}
.calendar-popup-inner calendar {
  background: transparent;
  color: #cad3f5;
  border: none;
  padding: 4px;
  font-size: 13px;
}
.calendar-popup-inner calendar:selected {
  background-color: #8aadf4;
  color: #1e1e2e;
  border-radius: 8px;
}
.calendar-popup-inner calendar.button {
  color: #cad3f5;
  background: transparent;
  border: none;
}
.calendar-popup-inner calendar.button:hover {
  background-color: rgba(138, 173, 244, 0.25);
  border-radius: 6px;
}
.calendar-popup-inner calendar.header {
  color: #cad3f5;
  font-weight: 600;
}
.calendar-popup-inner calendar.day-name {
  color: #a5adcb;
  font-weight: 500;
}
.calendar-popup-inner calendar.highlight {
  color: #8aadf4;
  font-weight: 600;
}
"""


class CalendarPopup(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_resizable(False)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.get_style_context().add_class("calendar-popup")

        if HAS_LAYER_SHELL:
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_namespace(self, "calendar-popup")
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, WAYBAR_HEIGHT - 8)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        inner.get_style_context().add_class("calendar-popup-inner")
        self.cal = Gtk.Calendar()
        self.cal.set_display_options(
            Gtk.CalendarDisplayOptions.SHOW_HEADING
            | Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES
        )
        self.cal.connect("day-selected-double-click", self._on_day_dblclick)
        inner.pack_start(self.cal, True, True, 0)
        self.add(inner)

        self.connect("key-press-event", self._on_key)

        self.show_all()

    def _on_day_dblclick(self, cal):
        try:
            subprocess.Popen(["gnome-calendar"])
        except FileNotFoundError:
            pass
        self.close()

    def _on_key(self, win, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False


class CalApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="dev.cosmoduck.calendarpopup",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

    def do_startup(self):
        Gtk.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def do_activate(self):
        win = self.props.active_window
        if win:
            win.close()
            return
        win = CalendarPopup(self)
        win.present()


if __name__ == "__main__":
    sys.exit(CalApp().run(sys.argv))
