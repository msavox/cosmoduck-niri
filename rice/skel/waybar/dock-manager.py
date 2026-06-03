#!/usr/bin/env python3
"""Dock Manager — manages dock-apps.json and regenerates the waybar dock."""
import json
import os
import re
import subprocess

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib, Pango  # noqa: E402

CFG_DIR = os.path.expanduser("~/.config/waybar")
APPS_JSON = f"{CFG_DIR}/dock-apps.json"
CONFIG_JSON = f"{CFG_DIR}/dock-config.json"
DOCK_GEN = f"{CFG_DIR}/dock-gen.sh"
DEFAULT_HEIGHT = 52
HEIGHT_MIN = 36
HEIGHT_MAX = 96
DEFAULT_COLORS = [
    "#8aadf4", "#8bd5ca", "#f5a97f", "#a6da95",
    "#f5bde6", "#eed49f", "#c6a0f6", "#ed8796",
]


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "app"


def load_apps():
    with open(APPS_JSON) as f:
        return json.load(f)


def save_apps(apps):
    with open(APPS_JSON, "w") as f:
        json.dump(apps, f, indent=2)
        f.write("\n")


def load_height():
    try:
        with open(CONFIG_JSON) as f:
            h = int(json.load(f).get("height", DEFAULT_HEIGHT))
    except Exception:
        h = DEFAULT_HEIGHT
    return max(HEIGHT_MIN, min(HEIGHT_MAX, h))


def save_height(height):
    cfg = {}
    try:
        with open(CONFIG_JSON) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg["height"] = int(height)
    with open(CONFIG_JSON, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def regen_dock():
    subprocess.run(["bash", DOCK_GEN], check=False)


class AppPickerDialog(Gtk.Dialog):
    """Dialog with search bar + list of installed apps (Gio.AppInfo.get_all)."""

    def __init__(self, parent):
        super().__init__(title="Add app to dock", transient_for=parent, modal=True)
        self.set_default_size(420, 520)
        self.add_buttons(
            "Cancel", Gtk.ResponseType.CANCEL,
            "Add", Gtk.ResponseType.OK,
        )
        self.selected = None

        box = self.get_content_area()
        box.set_spacing(6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        self.search = Gtk.SearchEntry(placeholder_text="Search…")
        self.search.connect("search-changed", lambda e: self.listbox.invalidate_filter())
        box.pack_start(self.search, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_filter_func(self._filter)
        self.listbox.connect("row-activated", self._on_row_activated)
        scroll.add(self.listbox)
        box.pack_start(scroll, True, True, 0)

        self.apps = [a for a in Gio.AppInfo.get_all() if a.should_show()]
        self.apps.sort(key=lambda a: (a.get_name() or "").lower())
        for app_info in self.apps:
            self.listbox.add(self._row(app_info))
        self.show_all()

    def _row(self, app_info):
        row = Gtk.ListBoxRow()
        row.app_info = app_info
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hbox.set_margin_start(6); hbox.set_margin_end(6)
        hbox.set_margin_top(4); hbox.set_margin_bottom(4)
        icon = app_info.get_icon()
        img = Gtk.Image()
        if icon:
            img.set_from_gicon(icon, Gtk.IconSize.DND)
        else:
            img.set_from_icon_name("application-x-executable", Gtk.IconSize.DND)
        hbox.pack_start(img, False, False, 0)
        lbl = Gtk.Label(xalign=0)
        lbl.set_text(app_info.get_name() or app_info.get_id() or "?")
        hbox.pack_start(lbl, True, True, 0)
        row.add(hbox)
        return row

    def _filter(self, row):
        q = self.search.get_text().strip().lower()
        if not q:
            return True
        name = (row.app_info.get_name() or "").lower()
        return q in name

    def _on_row_activated(self, listbox, row):
        self.selected = row.app_info
        self.response(Gtk.ResponseType.OK)

    def get_selected(self):
        if self.selected:
            return self.selected
        row = self.listbox.get_selected_row()
        return row.app_info if row else None


class DockManager(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Dock Manager")
        self.set_default_size(520, 640)
        self.set_position(Gtk.WindowPosition.CENTER)

        try:
            self.apps = load_apps()
        except Exception as e:
            self._error(f"Failed to load {APPS_JSON}:\n{e}")
            self.apps = []

        header = Gtk.HeaderBar(title="Dock Manager")
        header.set_show_close_button(True)
        self.set_titlebar(header)

        add_btn = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON)
        add_btn.set_tooltip_text("Add app")
        add_btn.connect("clicked", self.on_add)
        header.pack_start(add_btn)

        save_btn = Gtk.Button.new_with_label("Save")
        save_btn.get_style_context().add_class("suggested-action")
        save_btn.connect("clicked", self.on_save)
        header.pack_end(save_btn)

        self.height_val = load_height()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        vbox.pack_start(self._make_height_row(), False, False, 0)
        vbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
                        False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.add(self.listbox)
        vbox.pack_start(scroll, True, True, 0)
        self.add(vbox)

        self._refresh()
        self.show_all()

    def _make_height_row(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_start(12); box.set_margin_end(12)
        box.set_margin_top(10); box.set_margin_bottom(10)

        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<b>Dock height</b>")
        box.pack_start(lbl, False, False, 0)

        self.height_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, HEIGHT_MIN, HEIGHT_MAX, 2)
        self.height_scale.set_value(self.height_val)
        self.height_scale.set_draw_value(False)
        self.height_scale.set_hexpand(True)
        for mark in (HEIGHT_MIN, DEFAULT_HEIGHT, HEIGHT_MAX):
            self.height_scale.add_mark(mark, Gtk.PositionType.BOTTOM, None)
        self.height_scale.connect("value-changed", self._on_height_changed)
        box.pack_start(self.height_scale, True, True, 0)

        self.height_lbl = Gtk.Label()
        self.height_lbl.set_width_chars(5)
        self._update_height_label()
        box.pack_start(self.height_lbl, False, False, 0)
        return box

    def _on_height_changed(self, scale):
        self.height_val = int(round(scale.get_value()))
        self._update_height_label()

    def _update_height_label(self):
        self.height_lbl.set_markup(
            f"<span foreground='#8087a2'>{self.height_val} px</span>")

    def _refresh(self):
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        first_post = next((i for i, a in enumerate(self.apps) if a.get("post_taskbar")), None)
        for i, app in enumerate(self.apps):
            if i == first_post:
                sep = Gtk.ListBoxRow(selectable=False, activatable=False)
                lbl = Gtk.Label()
                lbl.set_markup("<small><i>──── after taskbar ────</i></small>")
                lbl.set_margin_top(8); lbl.set_margin_bottom(4)
                sep.add(lbl)
                self.listbox.add(sep)
            self.listbox.add(self._make_row(app, i))
        self.listbox.show_all()

    def _make_row(self, app, idx):
        row = Gtk.ListBoxRow(selectable=False, activatable=False)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_start(10); box.set_margin_end(10)
        box.set_margin_top(6); box.set_margin_bottom(6)

        icon_name = app.get("icon_name") or "application-x-executable"
        img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DND)
        box.pack_start(img, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name_lbl = Gtk.Label(xalign=0)
        name_lbl.set_markup(f"<b>{GLib.markup_escape_text(app.get('name', app['id']))}</b>")
        cmd_lbl = Gtk.Label(xalign=0)
        cmd_lbl.set_markup(
            f"<small><span foreground='#8087a2'>"
            f"{GLib.markup_escape_text(app.get('command', ''))}"
            f"</span></small>"
        )
        cmd_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        cmd_lbl.set_max_width_chars(40)
        text_box.pack_start(name_lbl, False, False, 0)
        text_box.pack_start(cmd_lbl, False, False, 0)
        box.pack_start(text_box, True, True, 0)

        up = Gtk.Button.new_from_icon_name("go-up-symbolic", Gtk.IconSize.BUTTON)
        up.set_tooltip_text("Move up")
        up.set_sensitive(idx > 0)
        up.connect("clicked", lambda b, i=idx: self._move(i, -1))
        box.pack_start(up, False, False, 0)

        down = Gtk.Button.new_from_icon_name("go-down-symbolic", Gtk.IconSize.BUTTON)
        down.set_tooltip_text("Move down")
        down.set_sensitive(idx < len(self.apps) - 1)
        down.connect("clicked", lambda b, i=idx: self._move(i, 1))
        box.pack_start(down, False, False, 0)

        rm = Gtk.Button.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
        rm.set_tooltip_text("Remove from dock")
        rm.connect("clicked", lambda b, i=idx: self._remove(i))
        box.pack_start(rm, False, False, 0)

        row.add(box)
        return row

    def _move(self, idx, delta):
        new = idx + delta
        if 0 <= new < len(self.apps):
            self.apps[idx], self.apps[new] = self.apps[new], self.apps[idx]
            self._refresh()

    def _remove(self, idx):
        name = self.apps[idx].get("name", self.apps[idx]["id"])
        dlg = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO,
            text=f"Remove '{name}' from the dock?",
        )
        ans = dlg.run()
        dlg.destroy()
        if ans == Gtk.ResponseType.YES:
            self.apps.pop(idx)
            self._refresh()

    def on_add(self, btn):
        dlg = AppPickerDialog(self)
        ans = dlg.run()
        app_info = dlg.get_selected()
        dlg.destroy()
        if ans != Gtk.ResponseType.OK or not app_info:
            return
        self._add_from_appinfo(app_info)

    def _add_from_appinfo(self, app_info):
        name = app_info.get_name() or "App"
        cmd = app_info.get_commandline() or ""
        cmd = re.sub(r"\s*%[FfUud]\s*", " ", cmd).strip()

        icon_name = ""
        icon = app_info.get_icon()
        if isinstance(icon, Gio.ThemedIcon):
            names = icon.get_names()
            if names:
                icon_name = names[0]

        wm_class = ""
        try:
            wm_class = app_info.get_string("StartupWMClass") or ""
        except Exception:
            pass

        # Edge PWA quirk: Microsoft Edge writes StartupWMClass=crx__<id> (old
        # X11 WM_CLASS), but on Wayland the real app_id is "msedge-_<id>-<profile>":
        # i.e. the .desktop basename ("msedge-<id>-<profile>") with one extra
        # underscore after "msedge-". Neither crx__ nor the basename match the
        # live app_id, so we derive it from the basename. (Chrome uses a single
        # crx_<id>, already correct in StartupWMClass, so we leave it alone.)
        desktop_id = app_info.get_id() or ""
        base = desktop_id[:-len(".desktop")] if desktop_id.endswith(".desktop") else desktop_id
        if base.startswith("msedge-") and not base.startswith("msedge-_"):
            wm_class = "msedge-_" + base[len("msedge-"):]

        existing = {a["id"] for a in self.apps}
        base = slugify(name)
        new_id = base
        n = 2
        while new_id in existing:
            new_id = f"{base}-{n}"; n += 1

        color = DEFAULT_COLORS[len(self.apps) % len(DEFAULT_COLORS)]
        entry = {
            "id": new_id,
            "icon": "",
            "name": name,
            "command": cmd,
            "color": color,
            "match": f"(?i){re.escape(wm_class) if wm_class else new_id}",
            "app_ids": [wm_class] if wm_class else [new_id],
            "icon_name": icon_name,
        }
        insert_idx = next(
            (i for i, a in enumerate(self.apps) if a.get("post_taskbar")),
            len(self.apps),
        )
        self.apps.insert(insert_idx, entry)
        self._refresh()

    def on_save(self, btn):
        try:
            save_apps(self.apps)
            save_height(self.height_val)
            regen_dock()
        except Exception as e:
            self._error(f"Save failed:\n{e}")

    def _info(self, msg):
        dlg = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text=msg,
        )
        dlg.run(); dlg.destroy()

    def _error(self, msg):
        dlg = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, text=msg,
        )
        dlg.run(); dlg.destroy()


class DockManagerApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="dev.cosmoduck.dockmanager",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = DockManager(self)
        win.present()


if __name__ == "__main__":
    import sys
    sys.exit(DockManagerApp().run(sys.argv))
