#!/usr/bin/python3
"""
desktop.py — Cosmoduck niri desktop icons.

niri has no desktop concept: no "below tile" layer for toplevels and no X11 root
window (xwayland-satellite is rootless), so xfdesktop/nemo-desktop/pcmanfm can't
paint anything. This draws the desktop ourselves on a gtk-layer-shell surface on
the BOTTOM layer — above the wallpaper (swaybg) and below the app tiles, exactly
where conky-bg.py already lives. Unlike conky-bg, this surface is INTERACTIVE:
its input region is left intact, so clicks on the empty desktop (the area no
window covers) are delivered to us, while clicks on a window go to the window.

Contents of ~/Desktop are rendered as an icon grid. Single click selects,
double click opens, right click spawns desktop-menu.py (a one-shot ctxmenu
consumer) anchored under the cursor. Two layouts, switchable from the menu:
  • auto  — column-major grid, sorted by name or type (re-laid on every refresh)
  • free  — icons dragged anywhere; positions persisted per filename

State lives in ~/.local/share/cosmoduck/desktop.json and is file-monitored, so a
mode/sort change written by the menu reloads here without any PID signalling.

Run with /usr/bin/python3 so the GIR typelibs resolve without env tweaks.
"""

import json
import os
import signal
import subprocess
import sys

import cairo

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Gio, GLib, Pango  # noqa: E402

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell  # noqa: E402
except (ValueError, ImportError):
    sys.stderr.write("desktop.py: gtk-layer-shell not available\n")
    sys.exit(1)

HOME = os.path.expanduser("~")
NIRI_DIR = os.path.join(HOME, ".config", "niri")
WAYBAR_DIR = os.path.join(HOME, ".config", "waybar")
STATE_DIR = os.path.join(HOME, ".local", "share", "cosmoduck")
STATE_FILE = os.path.join(STATE_DIR, "desktop.json")

# Dock layout constants, mirrored from dock-gen.sh / dock-menu.py, used to map
# a drop position on the dock strip back to the icon under it.
DOCK_SPACING = 6
DOCK_MARGIN = 6
MOD_MARGIN_X = 6

# Popular icon-size presets: name -> (icon_px, cell_w, cell_h). Chosen from the
# desktop context menu; persisted as state["icon_size"].
SIZES = {
    "small":  (32, 80, 76),
    "medium": (48, 96, 92),
    "large":  (64, 118, 112),
    "xlarge": (96, 152, 146),
}
DEFAULT_SIZE = "medium"

# Keep icons clear of the top waybar and the bottom dock (both ignore us since
# we set exclusive_zone -1 and span the whole output).
TOP_INSET = 44
BOTTOM_INSET = 78
SIDE_INSET = 16

_CSS = b"""
window, eventbox { background: transparent; }
.desktop-cell {
  border-radius: 10px;
  padding: 4px;
}
.desktop-cell label {
  color: #ffffff;
  font-family: "Inter", "Roboto", "Ubuntu", "Noto Sans", sans-serif;
  font-size: 12.5px;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.95), 0 0 2px rgba(0, 0, 0, 0.9);
}
.desktop-cell.selected {
  background: rgba(138, 173, 244, 0.30);
  border: 1px solid rgba(138, 173, 244, 0.55);
}
.desktop-cell.selected label {
  text-shadow: none;
}
.marquee {
  background: rgba(138, 173, 244, 0.16);
  border: 1px solid rgba(138, 173, 244, 0.65);
  border-radius: 2px;
}
"""


def _rm_recursive(gfile):
    """Permanent delete; gio's delete is non-recursive, so walk directories."""
    info = gfile.query_info(Gio.FILE_ATTRIBUTE_STANDARD_TYPE,
                            Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
    if info.get_file_type() == Gio.FileType.DIRECTORY:
        en = gfile.enumerate_children(Gio.FILE_ATTRIBUTE_STANDARD_NAME,
                                      Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
        while True:
            child = en.next_file(None)
            if child is None:
                break
            _rm_recursive(gfile.get_child(child.get_name()))
        en.close(None)
    gfile.delete(None)


def translate(src, dest, x, y):
    """Widget-to-widget coordinate translation that tolerates either PyGObject
    return shape — (dest_x, dest_y) or (ok, dest_x, dest_y). Returns (x, y) or
    None when the widgets share no ancestor."""
    res = src.translate_coordinates(dest, int(x), int(y))
    if not res:
        return None
    if len(res) == 3:
        return (res[1], res[2]) if res[0] else None
    return (res[0], res[1])


def desktop_dir():
    try:
        d = subprocess.check_output(["xdg-user-dir", "DESKTOP"], text=True).strip()
        if d and os.path.isdir(d):
            return d
    except Exception:
        pass
    return os.path.join(HOME, "Desktop")


def primary_monitor():
    disp = Gdk.Display.get_default()
    mon = disp.get_primary_monitor() or disp.get_monitor(0)
    return mon


def load_state():
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("mode", "auto")          # "auto" | "free"
    s.setdefault("sort", "name")          # "name" | "type"
    s.setdefault("icon_size", DEFAULT_SIZE)  # key into SIZES
    s.setdefault("show_icons", True)      # False -> clean wallpaper, no icons
    s.setdefault("tidy", 0)               # bump = one-shot snap-to-grid request
    s.setdefault("positions", {})         # filename -> [x, y]
    return s


class DesktopIcon:
    """One ~/Desktop entry plus its widget."""

    def __init__(self, gfile, info):
        self.gfile = gfile
        self.name = info.get_name()
        self.display_name = info.get_display_name() or self.name
        self.content_type = info.get_content_type() or ""
        self.is_dir = info.get_file_type() == Gio.FileType.DIRECTORY
        self.path = gfile.get_path()
        self.is_desktop = self.name.endswith(".desktop") and not self.is_dir

        self.appinfo = None
        self.gicon = info.get_icon()
        if self.is_desktop:
            try:
                ai = Gio.DesktopAppInfo.new_from_filename(self.path)
            except Exception:
                ai = None
            if ai is not None:
                self.appinfo = ai
                self.display_name = ai.get_display_name() or self.display_name
                if ai.get_icon() is not None:
                    self.gicon = ai.get_icon()

        self.widget = None  # the EventBox cell

    def sort_key(self, mode):
        # Folders first, then files; tie-break by name (case-insensitive).
        primary = (not self.is_dir) if mode == "name" else self.content_type
        return (not self.is_dir, primary if mode == "type" else "",
                self.display_name.lower())

    def open(self):
        uri = self.gfile.get_uri()
        try:
            if self.appinfo is not None:
                self.appinfo.launch([], None)
                return
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except Exception:
            subprocess.Popen(["xdg-open", self.path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Desktop:
    def __init__(self):
        self.dir = desktop_dir()
        self.state = load_state()
        self.icons = []            # list[DesktopIcon]
        self.selected = set()      # set of filenames
        self._refresh_id = 0
        self._dragging = set()     # filenames of an in-flight icon drag
        self._marquee = None       # {"start": (x,y), "base": set, "box": widget|None}

        self._build_window()
        self._install_css()
        self.reload_icons()
        self._watch_desktop()
        self._watch_state()

    # ── window / layer-shell ───────────────────────────────────────────
    def _build_window(self):
        self.win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.win.set_decorated(False)
        self.win.set_app_paintable(True)
        self.win.set_title("cosmoduck-desktop")  # app-id for compositor rules
        screen = self.win.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.win.set_visual(visual)

        mon = primary_monitor()
        geo = mon.get_geometry() if mon else None
        self.mon_w = geo.width if geo else 1920
        self.mon_h = geo.height if geo else 1080

        GtkLayerShell.init_for_window(self.win)
        if mon is not None:
            GtkLayerShell.set_monitor(self.win, mon)
        GtkLayerShell.set_layer(self.win, GtkLayerShell.Layer.BOTTOM)
        # ON_DEMAND: the desktop takes keyboard focus when clicked (so Delete /
        # Shift+Delete act on the selection) and releases it to apps otherwise.
        GtkLayerShell.set_keyboard_mode(self.win, GtkLayerShell.KeyboardMode.ON_DEMAND)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self.win, edge, True)
        GtkLayerShell.set_exclusive_zone(self.win, -1)

        # Background event box catches clicks on the empty desktop; the Fixed
        # holds the absolutely-positioned icon cells on top of it.
        self.bg = Gtk.EventBox()
        self.fixed = Gtk.Fixed()
        for w in (self.bg, self.fixed):
            w.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                         Gdk.EventMask.BUTTON_RELEASE_MASK |
                         Gdk.EventMask.POINTER_MOTION_MASK |
                         Gdk.EventMask.BUTTON1_MOTION_MASK)
            w.connect("button-press-event", self.on_empty_press)
            w.connect("motion-notify-event", self.on_marquee_motion)
            w.connect("button-release-event", self.on_marquee_release)
        self.bg.add(self.fixed)
        self.win.add(self.bg)
        self.win.connect("key-press-event", self.on_key)
        self.win.connect("destroy", lambda *_: Gtk.main_quit())

        # The desktop is a drop target: dragging files here from another app (or
        # repositioning our own icons in free mode) lands in on_drag_data_received.
        for w in (self.bg, self.fixed):
            w.drag_dest_set(Gtk.DestDefaults.ALL, [],
                            Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
            w.drag_dest_add_uri_targets()
            w.connect("drag-data-received", self.on_drag_data_received)

    def _install_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ── icon model ─────────────────────────────────────────────────────
    def reload_icons(self):
        self.state = load_state()
        self.icon_size, self.cell_w, self.cell_h = SIZES.get(
            self.state["icon_size"], SIZES[DEFAULT_SIZE])
        for ic in self.icons:
            if ic.widget is not None:
                ic.widget.destroy()
        self.icons = []

        gdir = Gio.File.new_for_path(self.dir)
        attrs = ",".join([
            Gio.FILE_ATTRIBUTE_STANDARD_NAME,
            Gio.FILE_ATTRIBUTE_STANDARD_DISPLAY_NAME,
            Gio.FILE_ATTRIBUTE_STANDARD_ICON,
            Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE,
            Gio.FILE_ATTRIBUTE_STANDARD_TYPE,
            Gio.FILE_ATTRIBUTE_STANDARD_IS_HIDDEN,
        ])
        try:
            en = gdir.enumerate_children(attrs, Gio.FileQueryInfoFlags.NONE, None)
        except GLib.Error:
            en = None
        if en is not None:
            while True:
                info = en.next_file(None)
                if info is None:
                    break
                if info.get_is_hidden():
                    continue
                child = gdir.get_child(info.get_name())
                self.icons.append(DesktopIcon(child, info))

        self.icons.sort(key=lambda ic: ic.sort_key(self.state["sort"]))
        self.selected &= {ic.name for ic in self.icons}
        for ic in self.icons:
            ic.widget = self._make_cell(ic)
            self.fixed.put(ic.widget, 0, 0)
        self.layout()
        self.win.show_all()
        self._apply_visibility()

    def _apply_visibility(self):
        """Honor state['show_icons']: hide every cell for a clean wallpaper while
        the surface still catches right-clicks on the empty desktop."""
        show = self.state.get("show_icons", True)
        for ic in self.icons:
            if ic.widget is not None:
                ic.widget.set_visible(show)

    def _make_cell(self, ic):
        box = Gtk.EventBox()
        box.get_style_context().add_class("desktop-cell")
        box.set_size_request(self.cell_w, self.cell_h)
        box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        img = Gtk.Image()
        if ic.gicon is not None:
            img.set_from_gicon(ic.gicon, Gtk.IconSize.DIALOG)
        else:
            img.set_from_icon_name("text-x-generic", Gtk.IconSize.DIALOG)
        img.set_pixel_size(self.icon_size)
        lbl = Gtk.Label(label=ic.display_name)
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_line_wrap(True)
        lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)  # break long unspaced names
        lbl.set_lines(2)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        # A fixed pixel width is what actually bounds the label (size_request is a
        # minimum, so it would otherwise let a long name grow the cell off-screen).
        lbl.set_size_request(self.cell_w - 6, -1)
        lbl.set_max_width_chars(max(8, self.cell_w // 7))
        col.pack_start(img, False, False, 0)
        col.pack_start(lbl, False, False, 0)
        box.add(col)

        box.connect("button-press-event", self.on_cell_press, ic)
        # Drag source: one gesture serves both repositioning (drop on our own
        # desktop in free mode) and dragging the file onto another app, which
        # receives it as text/uri-list.
        box.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [],
                            Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        box.drag_source_add_uri_targets()
        box.connect("drag-begin", self.on_drag_begin, ic)
        box.connect("drag-data-get", self.on_drag_data_get, ic)
        box.connect("drag-end", self.on_drag_end, ic)
        if ic.name in self.selected:
            box.get_style_context().add_class("selected")
        return box

    # ── layout ─────────────────────────────────────────────────────────
    def _grid_slot(self, index):
        """Column-major position, macOS-style: start at the top-RIGHT corner,
        fill top→bottom, then add columns leftward."""
        rows = max(1, (self.mon_h - TOP_INSET - BOTTOM_INSET) // self.cell_h)
        col, row = divmod(index, rows)
        x = self.mon_w - SIDE_INSET - (col + 1) * self.cell_w
        y = TOP_INSET + row * self.cell_h
        return x, y

    def layout(self):
        if self.state["mode"] == "free":
            pos = self.state.get("positions", {})
            used = set()
            free_idx = 0
            for ic in self.icons:
                p = pos.get(ic.name)
                if p and isinstance(p, list) and len(p) == 2:
                    x, y = int(p[0]), int(p[1])
                else:
                    # New file with no saved spot: drop on the next grid slot.
                    while True:
                        x, y = self._grid_slot(free_idx)
                        free_idx += 1
                        if (x, y) not in used:
                            break
                used.add((x, y))
                self.fixed.move(ic.widget, x, y)
        else:
            for i, ic in enumerate(self.icons):
                x, y = self._grid_slot(i)
                self.fixed.move(ic.widget, x, y)

    def snap_to_grid(self):
        """One-shot Clean Up: move every icon to the NEAREST free grid cell,
        keeping the user's spatial arrangement (no re-sorting), and persist."""
        rows = max(1, (self.mon_h - TOP_INSET - BOTTOM_INSET) // self.cell_h)
        cols = max(1, (self.mon_w - 2 * SIDE_INSET) // self.cell_w)
        slots = [self._grid_slot(i) for i in range(rows * cols)]
        taken = set()
        pos = self.state.setdefault("positions", {})
        for ic in self.icons:
            cur = pos.get(ic.name)
            if not (cur and isinstance(cur, list) and len(cur) == 2):
                alloc = self.fixed.child_get_property(ic.widget, "x"), \
                        self.fixed.child_get_property(ic.widget, "y")
                cur = [int(alloc[0]), int(alloc[1])]
            best = min((s for s in slots if s not in taken),
                       key=lambda s: (s[0] - cur[0]) ** 2 + (s[1] - cur[1]) ** 2,
                       default=None)
            if best is None:
                break
            taken.add(best)
            pos[ic.name] = [best[0], best[1]]
            self.fixed.move(ic.widget, best[0], best[1])
        self._save_state()

    # ── selection ──────────────────────────────────────────────────────
    def _set_selected(self, names):
        self.selected = set(names)
        for ic in self.icons:
            ctx = ic.widget.get_style_context()
            if ic.name in self.selected:
                ctx.add_class("selected")
            else:
                ctx.remove_class("selected")

    # ── keyboard ───────────────────────────────────────────────────────
    def _selected_icons(self):
        return [i for i in self.icons if i.name in self.selected]

    def on_key(self, widget, event):
        kv = event.keyval
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if kv in (Gdk.KEY_Delete, Gdk.KEY_KP_Delete) and self.selected:
            if shift:
                self._delete_selected()
            else:
                self._trash_selected()
            return True
        if kv == Gdk.KEY_a and ctrl:
            self._set_selected({i.name for i in self.icons})
            return True
        if kv == Gdk.KEY_Escape:
            self._set_selected(set())
            return True
        if kv in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.selected:
            for ic in self._selected_icons():
                ic.open()
            return True
        return False

    def _trash_selected(self):
        for ic in self._selected_icons():
            try:
                ic.gfile.trash(None)
            except GLib.Error as e:
                sys.stderr.write(f"desktop.py: trash {ic.name}: {e}\n")
        self.selected = set()

    def _delete_selected(self):
        icons = self._selected_icons()
        if not icons:
            return
        n = len(icons)
        msg = (f"Permanently delete “{icons[0].display_name}”?" if n == 1
               else f"Permanently delete {n} items?")
        dlg = Gtk.MessageDialog(
            transient_for=None, modal=True, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE, text=msg,
            secondary_text="This can’t be undone.")
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dlg.add_button("Delete", Gtk.ResponseType.OK).get_style_context() \
            .add_class("destructive-action")
        dlg.set_default_response(Gtk.ResponseType.CANCEL)
        resp = dlg.run()
        dlg.destroy()
        if resp != Gtk.ResponseType.OK:
            return
        for ic in icons:
            try:
                _rm_recursive(ic.gfile)
            except GLib.Error as e:
                sys.stderr.write(f"desktop.py: delete {ic.name}: {e}\n")
        self.selected = set()

    # ── events ─────────────────────────────────────────────────────────
    def on_cell_press(self, widget, event, ic):
        if event.type == Gdk.EventType._2BUTTON_PRESS and event.button == 1:
            ic.open()
            return True
        if event.button == 1:
            ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
            shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
            if ctrl or shift:
                sel = set(self.selected)
                sel.symmetric_difference_update({ic.name})
                self._set_selected(sel)
            elif ic.name not in self.selected:
                self._set_selected({ic.name})
            # Return False so GTK's drag controller can still arm a drag on motion.
            return False
        if event.button == 3:
            if ic.name not in self.selected:
                self._set_selected({ic.name})
            self._popup_menu_for_selection(ic, event, widget)
            return True
        return False

    # ── drag and drop ──────────────────────────────────────────────────
    def _icon_by_name(self, name):
        return next((i for i in self.icons if i.name == name), None)

    def on_drag_begin(self, widget, ctx, ic):
        names = self.selected if ic.name in self.selected else {ic.name}
        self._dragging = set(names)
        if ic.gicon is not None:
            Gtk.drag_set_icon_gicon(ctx, ic.gicon, 0, 0)
        self._show_dock_strip()

    def on_drag_data_get(self, widget, ctx, data, info, time, ic):
        names = self._dragging or {ic.name}
        uris = [i.gfile.get_uri() for i in self.icons if i.name in names]
        data.set_uris(uris)

    def on_drag_end(self, widget, ctx, ic):
        self._dragging = set()
        self._hide_dock_strip()

    def on_drag_data_received(self, widget, ctx, x, y, data, info, time):
        internal = set(self._dragging)
        coords = translate(widget, self.fixed, x, y)
        fx, fy = coords if coords is not None else (int(x), int(y))
        if internal:
            # Our own icons: reposition them at the drop point (free mode only).
            if self.state["mode"] == "free":
                pos = self.state.setdefault("positions", {})
                for n, name in enumerate(sorted(internal)):
                    ic = self._icon_by_name(name)
                    if ic is None:
                        continue
                    nx = max(0, min(int(fx) + n * 18, self.mon_w - self.cell_w))
                    ny = max(0, min(int(fy) + n * 18, self.mon_h - self.cell_h))
                    self.fixed.move(ic.widget, nx, ny)
                    pos[name] = [nx, ny]
                self._save_state()
            return
        # Files dragged in from another app → copy them onto the desktop.
        self._import_external(list(data.get_uris()))

    def _import_external(self, uris):
        here = os.path.normpath(self.dir)
        for uri in uris:
            src = Gio.File.new_for_uri(uri)
            p = src.get_path()
            if not p or os.path.dirname(os.path.normpath(p)) == here:
                continue
            dest = Gio.File.new_for_path(self._unique_name(os.path.basename(p)))
            try:
                src.copy(dest, Gio.FileCopyFlags.NONE, None, None, None)
            except GLib.Error as e:
                sys.stderr.write(f"desktop.py: import {p}: {e}\n")

    def _unique_name(self, name):
        dest = os.path.join(self.dir, name)
        if not os.path.exists(dest):
            return dest
        stem, ext = os.path.splitext(name)
        i = 2
        while os.path.exists(os.path.join(self.dir, f"{stem} ({i}){ext}")):
            i += 1
        return os.path.join(self.dir, f"{stem} ({i}){ext}")

    # ── dock drop strip (drag desktop icons onto dock apps / trash) ─────
    def _dock_layout(self):
        """[(center_x, entry), …] for the pinned dock modules, mirroring the
        estimation in dock-menu.py (exact before the taskbar, approx after)."""
        try:
            with open(os.path.join(WAYBAR_DIR, "dock-apps.json")) as f:
                apps = json.load(f)
        except Exception:
            return []
        try:
            with open(os.path.join(WAYBAR_DIR, "dock-config.json")) as f:
                H = int(json.load(f).get("height", 52))
        except Exception:
            H = 52
        H = max(36, min(110, H))
        fp = (H * 36 // 52) + MOD_MARGIN_X
        tfp = (H * 32 // 52) + MOD_MARGIN_X
        pre = [e for e in apps if not e.get("post_taskbar")]
        post = [e for e in apps if e.get("post_taskbar")]
        pinned = {a for e in apps for a in (e.get("app_ids") or [])}
        ntask = 0
        try:
            wins = json.loads(subprocess.check_output(
                ["niri", "msg", "--json", "windows"], text=True))
            ntask = sum(1 for w in wins if (w.get("app_id") or "") not in pinned)
        except Exception:
            pass
        seq = [(e, fp) for e in pre] + [(None, tfp)] * ntask + [(e, fp) for e in post]
        if not seq:
            return []
        total = sum(w for _, w in seq) + DOCK_SPACING * (len(seq) - 1) + 2 * DOCK_MARGIN
        x = (self.mon_w - total) / 2 + DOCK_MARGIN
        out = []
        for e, w in seq:
            if e is not None:
                out.append((x + w / 2, e))
            x += w + DOCK_SPACING
        return out

    def _show_dock_strip(self):
        if getattr(self, "_strip", None) is not None:
            return
        strip = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        strip.set_decorated(False)
        strip.set_app_paintable(True)
        visual = strip.get_screen().get_rgba_visual()
        if visual is not None:
            strip.set_visual(visual)
        GtkLayerShell.init_for_window(strip)
        mon = primary_monitor()
        if mon is not None:
            GtkLayerShell.set_monitor(strip, mon)
        GtkLayerShell.set_layer(strip, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(strip, GtkLayerShell.KeyboardMode.NONE)
        for edge in (GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT,
                     GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(strip, edge, True)
        GtkLayerShell.set_exclusive_zone(strip, -1)
        box = Gtk.EventBox()
        box.set_size_request(self.mon_w, 80)  # dock height + margins
        box.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        box.drag_dest_add_uri_targets()
        box.connect("drag-data-received", self.on_dock_drop)
        strip.add(box)
        strip.show_all()
        self._strip = strip

    def _hide_dock_strip(self):
        strip = getattr(self, "_strip", None)
        if strip is not None:
            # Destroy after the dnd handshake settles, or the drop is lost.
            GLib.timeout_add(150, lambda: (strip.destroy(), False)[1])
            self._strip = None

    def on_dock_drop(self, widget, ctx, x, y, data, info, time):
        uris = list(data.get_uris())
        layout = self._dock_layout()
        if not uris or not layout:
            return
        cx, entry = min(layout, key=lambda t: abs(t[0] - x))
        if abs(cx - x) > 60:   # dropped on dock dead-space: do nothing
            return
        cmd = entry.get("command", "")
        if entry.get("id") == "trash" or "trash://" in cmd:
            # macOS-style: batch-trash everything dropped on the bin.
            for uri in uris:
                try:
                    Gio.File.new_for_uri(uri).trash(None)
                except GLib.Error as e:
                    sys.stderr.write(f"desktop.py: trash {uri}: {e}\n")
            return
        self._open_with_entry(entry, uris)

    def _open_with_entry(self, entry, uris):
        """Open the dropped files with the dock entry's app (macOS-style)."""
        for app_id in entry.get("app_ids") or []:
            for did in (f"{app_id}.desktop", f"{app_id.lower()}.desktop"):
                ai = Gio.DesktopAppInfo.new(did)
                if ai is not None:
                    try:
                        ai.launch_uris(uris, None)
                        return
                    except GLib.Error:
                        pass
        cmd = entry.get("command")
        if cmd:
            paths = [Gio.File.new_for_uri(u).get_path() or u for u in uris]
            subprocess.Popen(["bash", "-lc",
                              cmd + " " + " ".join(f"'{p}'" for p in paths)],
                             start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def on_empty_press(self, widget, event):
        # Cells return False on left press (GTK's drag controller needs the
        # event), so it bubbles up here: ignore anything that didn't start on
        # our own GdkWindow or a click would instantly clear the selection.
        if event.window != widget.get_window():
            return False
        if event.button == 1:
            self._clear_marquee()  # tear down any leftover rubber-band first
            ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
            base = set(self.selected) if ctrl else set()
            if not ctrl:
                self._set_selected(set())
            coords = translate(widget, self.fixed, event.x, event.y)
            start = coords if coords is not None else (int(event.x), int(event.y))
            self._marquee = {"start": start, "base": base, "box": None}
            return True
        if event.button == 3:
            self._spawn_menu(["empty"], event)
            return True
        return False

    def on_marquee_motion(self, widget, event):
        mq = self._marquee
        if mq is None:
            return False
        coords = translate(widget, self.fixed, event.x, event.y)
        if coords is None:
            return False
        sx, sy = mq["start"]
        x0, y0 = min(sx, coords[0]), min(sy, coords[1])
        w, h = abs(coords[0] - sx), abs(coords[1] - sy)
        if mq["box"] is None:
            if w < 4 and h < 4:
                return True
            box = Gtk.EventBox()
            box.get_style_context().add_class("marquee")
            self.fixed.put(box, x0, y0)
            box.show()
            # The rubber-band sits under the cursor, so without this the
            # button-release would land on IT (no handler) and the box would
            # never be torn down — leaving a dead rectangle that eats clicks.
            # An empty input region makes it click-through; release reaches us.
            gw = box.get_window()
            if gw is not None:
                gw.input_shape_combine_region(cairo.Region(), 0, 0)
            mq["box"] = box
        self.fixed.move(mq["box"], int(x0), int(y0))
        mq["box"].set_size_request(max(1, int(w)), max(1, int(h)))

        hits = set()
        for ic in self.icons:
            if not ic.widget.get_visible():
                continue
            cx = self.fixed.child_get_property(ic.widget, "x")
            cy = self.fixed.child_get_property(ic.widget, "y")
            if (cx < x0 + w and cx + self.cell_w > x0 and
                    cy < y0 + h and cy + self.cell_h > y0):
                hits.add(ic.name)
        self._set_selected(mq["base"] | hits)
        return True

    def on_marquee_release(self, widget, event):
        if self._marquee is None:
            return False
        self._clear_marquee()
        return True

    def _clear_marquee(self):
        if self._marquee is not None:
            box = self._marquee.get("box")
            if box is not None:
                box.destroy()
            self._marquee = None

    # ── context menu spawning ──────────────────────────────────────────
    def _popup_menu_for_selection(self, ic, event, widget):
        paths = [i.path for i in self.icons if i.name in self.selected]
        if not paths:
            paths = [ic.path]
        if len(paths) > 1:
            kind = "multi"
        else:
            kind = "folder" if ic.is_dir else "file"
        self._spawn_menu([kind] + paths, event, src_widget=widget)

    def _spawn_menu(self, args, event, src_widget=None):
        # Translate the click to monitor-local coords. The surface fills the
        # output, so surface-local == monitor-local, and the menu (also a
        # full-output overlay) lands precisely under the cursor.
        w = src_widget if src_widget is not None else self.bg
        coords = translate(w, self.win, event.x, event.y)
        x, y = coords if coords is not None else (int(event.x), int(event.y))
        cmd = ["/usr/bin/python3", os.path.join(NIRI_DIR, "desktop-menu.py"),
               "--x", str(int(x)), "--y", str(int(y))] + args
        subprocess.Popen(cmd, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ── persistence ────────────────────────────────────────────────────
    def _save_state(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.state, f, indent=2)
            os.replace(tmp, STATE_FILE)
        except Exception as e:
            sys.stderr.write(f"desktop.py: state save failed: {e}\n")

    # ── file monitors ──────────────────────────────────────────────────
    def _watch_desktop(self):
        self._mon = Gio.File.new_for_path(self.dir).monitor_directory(
            Gio.FileMonitorFlags.WATCH_MOVES, None)
        self._mon.connect("changed", self._on_dir_changed)

    def _on_dir_changed(self, *_):
        # Debounce a burst of fs events into one rebuild.
        if self._refresh_id:
            GLib.source_remove(self._refresh_id)
        self._refresh_id = GLib.timeout_add(200, self._do_refresh)

    def _do_refresh(self):
        self._refresh_id = 0
        self.reload_icons()
        return False

    def _watch_state(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
        except Exception:
            pass
        sf = Gio.File.new_for_path(STATE_FILE)
        self._smon = sf.monitor_file(Gio.FileMonitorFlags.NONE, None)
        self._smon.connect("changed", self._on_state_changed)

    def _on_state_changed(self, mon, f, other, ev):
        if ev not in (Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                      Gio.FileMonitorEvent.CREATED):
            return
        new = load_state()
        # icon size and sort order change the cells themselves → full rebuild;
        # a tidy request snaps to grid; mode/position/visibility only touch
        # existing cells → relayout / re-show.
        rebuild = (new["icon_size"] != self.state["icon_size"] or
                   new["sort"] != self.state["sort"])
        tidy = new.get("tidy", 0) != self.state.get("tidy", 0)
        self.state = new
        if rebuild:
            self.reload_icons()
        elif tidy:
            self.snap_to_grid()
        else:
            self.layout()
        self._apply_visibility()

    def run(self):
        self.win.show_all()
        Gtk.main()


def main():
    # GLib-integrated handlers: plain signal.signal() ones don't fire while
    # blocked inside the C main loop.
    for sig in (signal.SIGTERM, signal.SIGINT):
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig,
                             lambda *_: (Gtk.main_quit(), False)[1])
    Desktop().run()


if __name__ == "__main__":
    main()
