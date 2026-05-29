#!/usr/bin/python3
"""
tray-dropdown.py — dropdown panel replacement for system tray.

Reads StatusNotifierItems registered with org.kde.StatusNotifierWatcher
and shows them in a small floating window (positioned by niri window-rule).

Click an item: triggers Activate on the SNI item.
Right-click an item: triggers ContextMenu (if the app supports it).
Click outside / Esc: closes the window.

Run with /usr/bin/python3 so GIR typelibs are visible without env tweaks.
"""

import os
import signal
import subprocess
import sys


def _toggle_off_if_running():
    """If an instance of tray-dropdown.py already exists, terminate it and exit.
    Lets the chevron work as a toggle (re-click → closes).

    Filters on /proc/PID/comm == python* so we don't kill the sh -c that waybar
    uses as parent (which, dying, would drag us down too)."""
    me = os.getpid()
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "tray-dropdown.py"], text=True
        )
    except subprocess.CalledProcessError:
        return
    others = []
    for tok in out.split():
        pid = int(tok)
        if pid == me:
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()
        except (FileNotFoundError, PermissionError):
            continue
        if comm.startswith("python"):
            others.append(pid)
    if not others:
        return
    for pid in others:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    sys.exit(0)


_toggle_off_if_running()

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("DbusmenuGtk3", "0.4")
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf, DbusmenuGtk3  # noqa: E402

# app-id used for niri's window-rule (open-floating + positioning)
GLib.set_prgname("tray-dropdown")
GLib.set_application_name("tray-dropdown")

WATCHER_BUS = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
WATCHER_IFACE = "org.kde.StatusNotifierWatcher"
ITEM_IFACE = "org.kde.StatusNotifierItem"


def parse_item_address(addr):
    """SNI registrations come as 'busname/path' or 'busname:path'."""
    if "/" in addr:
        bus, rest = addr.split("/", 1)
        return bus, "/" + rest
    return addr, "/StatusNotifierItem"


def dbus_get(bus, name, path, iface, prop):
    try:
        proxy = Gio.DBusProxy.new_sync(
            bus, Gio.DBusProxyFlags.NONE, None,
            name, path,
            "org.freedesktop.DBus.Properties", None,
        )
        return proxy.call_sync(
            "Get", GLib.Variant("(ss)", (iface, prop)),
            Gio.DBusCallFlags.NONE, 1500, None,
        ).unpack()[0]
    except GLib.Error:
        return None


def call_item(bus, name, path, method):
    try:
        proxy = Gio.DBusProxy.new_sync(
            bus, Gio.DBusProxyFlags.NONE, None,
            name, path, ITEM_IFACE, None,
        )
        proxy.call_sync(
            method, GLib.Variant("(ii)", (0, 0)),
            Gio.DBusCallFlags.NONE, 2000, None,
        )
    except GLib.Error as e:
        print(f"[tray-dropdown] {method} failed for {name}: {e.message}",
              file=sys.stderr)


def pixmap_to_pixbuf(width, height, data):
    """SNI IconPixmap is ARGB32 big-endian. Convert to RGBA for GdkPixbuf."""
    arr = bytearray(data)
    for i in range(0, len(arr), 4):
        a, r, g, b = arr[i], arr[i+1], arr[i+2], arr[i+3]
        arr[i]   = r
        arr[i+1] = g
        arr[i+2] = b
        arr[i+3] = a
    return GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(bytes(arr)),
        GdkPixbuf.Colorspace.RGB, True, 8, width, height, width * 4,
    )


def get_items(bus):
    addrs = dbus_get(bus, WATCHER_BUS, WATCHER_PATH, WATCHER_IFACE,
                     "RegisteredStatusNotifierItems") or []
    out = []
    for addr in addrs:
        item_bus, item_path = parse_item_address(addr)
        title = (dbus_get(bus, item_bus, item_path, ITEM_IFACE, "Title")
                 or dbus_get(bus, item_bus, item_path, ITEM_IFACE, "Id")
                 or item_bus)
        icon_name = dbus_get(bus, item_bus, item_path, ITEM_IFACE, "IconName") or ""
        pixmap = dbus_get(bus, item_bus, item_path, ITEM_IFACE, "IconPixmap") or []
        menu_path = dbus_get(bus, item_bus, item_path, ITEM_IFACE, "Menu") or ""
        tip_raw = dbus_get(bus, item_bus, item_path, ITEM_IFACE, "ToolTip")
        tip = ""
        if isinstance(tip_raw, tuple) and len(tip_raw) >= 3:
            tip = tip_raw[2] or (tip_raw[3] if len(tip_raw) >= 4 else "") or ""
        out.append({
            "bus": item_bus, "path": item_path, "menu_path": menu_path,
            "title": title, "icon": icon_name, "pixmap": pixmap, "tooltip": tip,
        })
    return out


def _theme_icon_pixbuf(name, size_px):
    """Load an icon from the current theme at exactly size_px (no LARGE_TOOLBAR)."""
    try:
        return Gtk.IconTheme.get_default().load_icon(
            name, size_px, Gtk.IconLookupFlags.FORCE_SIZE
        )
    except GLib.Error:
        return None


def build_icon_image(item, size_px=22):
    """Resolve an icon: file-path > theme name > pixmap > generic fallback.
    All paths return an image forced to size_px×size_px, so that
    the tray icons have uniform dimensions."""
    name = item.get("icon") or ""
    # 1) Path on disk (e.g. fortitray: /opt/forticlient/images/Forticlient.png)
    if name.startswith("/") and os.path.isfile(name):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(name, size_px, size_px)
            return Gtk.Image.new_from_pixbuf(pb)
        except GLib.Error:
            pass
    # 2) Valid name in the current theme — force the size
    if name and Gtk.IconTheme.get_default().has_icon(name):
        pb = _theme_icon_pixbuf(name, size_px)
        if pb is not None:
            return Gtk.Image.new_from_pixbuf(pb)
    # 3) Pixmap raw (Teams e simili)
    pixmap = item.get("pixmap") or []
    if pixmap:
        # pick the size closest to 32 px (LARGE_TOOLBAR ~ 24-32)
        w, h, data = sorted(pixmap, key=lambda p: abs(p[0] - 32))[0]
        try:
            pb = pixmap_to_pixbuf(w, h, data)
            if w != size_px:
                pb = pb.scale_simple(size_px, size_px, GdkPixbuf.InterpType.BILINEAR)
            return Gtk.Image.new_from_pixbuf(pb)
        except Exception as e:
            print(f"[tray-dropdown] pixmap decode failed: {e}", file=sys.stderr)
    # 4) Generic fallback — force the size
    pb = _theme_icon_pixbuf("application-x-executable", size_px)
    if pb is not None:
        return Gtk.Image.new_from_pixbuf(pb)
    return Gtk.Image.new_from_icon_name("application-x-executable", Gtk.IconSize.LARGE_TOOLBAR)


def make_row(bus, item, on_action):
    """Create a dropdown cell (icon only, tooltip on hover).
    If the item has a DBusMenu, open it as a popup on click."""
    inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    inner.set_margin_start(1); inner.set_margin_end(1)
    inner.set_margin_top(0); inner.set_margin_bottom(0)
    inner.pack_start(build_icon_image(item, size_px=18), False, False, 0)

    menu_path = item.get("menu_path") or ""
    if menu_path:
        # Item exposes a DBusMenu → normal button that does popup_at_widget
        # using the click event (Wayland requires a trigger event)
        try:
            submenu = DbusmenuGtk3.Menu.new(item["bus"], menu_path)
        except Exception as e:
            print(f"[tray-dropdown] dbusmenu creation failed for {item['title']}: {e}", file=sys.stderr)
            submenu = None

        if submenu is not None:
            btn = Gtk.Button()
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.add(inner)
            if item["tooltip"]:
                btn.set_tooltip_text(item["tooltip"])

            def on_clicked(widget, _menu=submenu, _title=item["title"]):
                ev = Gtk.get_current_event()
                n = len(_menu.get_children())
                print(f"[tray-dropdown] '{_title}' clicked, submenu has {n} items, ev={ev}",
                      file=sys.stderr)
                _menu.show_all()
                _menu.popup_at_widget(
                    widget,
                    Gdk.Gravity.SOUTH_EAST, Gdk.Gravity.NORTH_EAST, ev,
                )
                _menu.connect("selection-done", lambda *_: on_action())

            btn.connect("clicked", on_clicked)
            return btn

    # Fallback: Button that calls Activate
    btn = Gtk.Button()
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.add(inner)
    if item["tooltip"]:
        btn.set_tooltip_text(item["tooltip"])

    def on_clicked(_w):
        call_item(bus, item["bus"], item["path"], "Activate")
        on_action()
    btn.connect("clicked", on_clicked)
    return btn


def main():
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    items = get_items(bus)

    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_decorated(False)
    win.set_resizable(False)
    # CSS aligned with the waybar look (Catppuccin Macchiato)
    css = b"""
    window {
      background: rgba(30, 30, 46, 0.95);
      border: 1px solid #494d64;
      border-radius: 16px;
    }
    button {
      padding: 5px 6px;
      margin: 1px 0;
      min-height: 0;
      min-width: 0;
      border: none;
      border-radius: 12px;
      background: transparent;
      color: #cad3f5;
      font-family: "Inter", "Roboto", "Ubuntu", "Noto Sans", sans-serif;
      font-size: 13px;
    }
    button:hover {
      background: rgba(138, 173, 244, 0.18);
    }
    tooltip {
      background: rgba(30, 30, 46, 0.95);
      border: 1px solid #494d64;
      border-radius: 8px;
    }
    tooltip label {
      font-size: 12px;
      color: #cad3f5;
      padding: 4px 6px;
    }
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    win.set_skip_taskbar_hint(True)
    win.set_skip_pager_hint(True)
    win.set_keep_above(True)
    win.set_title("tray-dropdown")
    win.set_role("tray-dropdown")
    win.set_name("tray-dropdown")
    # app-id on Wayland comes from Gdk.set_program_class / set_prgname

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    hbox.set_margin_start(2); hbox.set_margin_end(2)
    hbox.set_margin_top(0); hbox.set_margin_bottom(0)
    on_action = lambda: GLib.idle_add(Gtk.main_quit)
    if not items:
        lbl = Gtk.Label(label="  (no active tray icons)  ")
        lbl.set_margin_top(8); lbl.set_margin_bottom(8); lbl.set_margin_start(12); lbl.set_margin_end(12)
        hbox.pack_start(lbl, False, False, 0)
    else:
        for it in items:
            hbox.pack_start(make_row(bus, it, on_action), False, False, 0)
    win.add(hbox)

    # close on focus-out (with 300ms grace period) and Esc
    focus_out_armed = [False]

    def on_focus_out(*_):
        if focus_out_armed[0]:
            Gtk.main_quit()
        return False

    win.connect("focus-out-event", on_focus_out)
    win.connect("destroy", lambda *_: Gtk.main_quit())

    def arm_focus_out():
        focus_out_armed[0] = True
        return False
    GLib.timeout_add(350, arm_focus_out)

    def on_key(_w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        return False
    win.connect("key-press-event", on_key)

    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
