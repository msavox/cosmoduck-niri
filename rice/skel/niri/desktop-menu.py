#!/usr/bin/python3
"""
desktop-menu.py — right-click context menu for the niri desktop.

A one-shot consumer of the shared ctxmenu framework (ctxmenu.py, which lives in
~/.config/waybar — the same framework the dock and tray use). desktop.py spawns
this fresh on every right-click and passes the cursor position, so the menu
appears precisely under the pointer. We run our own Gtk.main() (via
ContextMenu.popup) and execute every action inline: filesystem changes are
picked up by desktop.py's Gio.FileMonitor, and layout/sort changes by its
monitor on the state file — no call-back channel is needed.

Usage:
    desktop-menu.py <kind> [paths...] --x <px> --y <px>
      kind = file | folder | multi | empty

Run with /usr/bin/python3 so the GIR typelibs resolve without env tweaks.
"""

import json
import os
import sys

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Gio, GLib  # noqa: E402

HOME = os.path.expanduser("~")
# ctxmenu.py is the shared menu framework, installed alongside the waybar shell.
sys.path.insert(0, os.path.join(HOME, ".config", "waybar"))
from ctxmenu import ContextMenu  # noqa: E402


def desktop_monitor():
    """The monitor the desktop surface lives on (primary). The cursor coords
    passed by desktop.py are local to it, so the menu must anchor here too."""
    disp = Gdk.Display.get_default()
    return disp.get_primary_monitor() or disp.get_monitor(0)

STATE_DIR = os.path.join(HOME, ".local", "share", "cosmoduck")
STATE_FILE = os.path.join(STATE_DIR, "desktop.json")
CACHE_DIR = os.path.join(HOME, ".cache", "cosmoduck")
CLIP_FILE = os.path.join(CACHE_DIR, "desktop-clip.json")


# ── state / clipboard helpers ──────────────────────────────────────────
def load_state():
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("mode", "auto")
    s.setdefault("sort", "name")
    s.setdefault("positions", {})
    return s


def save_state(s):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, STATE_FILE)


def load_clip():
    try:
        with open(CLIP_FILE) as f:
            c = json.load(f)
        if c.get("paths"):
            return c
    except Exception:
        pass
    return None


def save_clip(mode, paths):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CLIP_FILE, "w") as f:
        json.dump({"mode": mode, "paths": paths}, f)


def clear_clip():
    try:
        os.remove(CLIP_FILE)
    except OSError:
        pass


# ── file actions ───────────────────────────────────────────────────────
def open_paths(paths):
    for p in paths:
        gf = Gio.File.new_for_path(p)
        try:
            if p.endswith(".desktop") and os.path.isfile(p):
                Gio.DesktopAppInfo.new_from_filename(p).launch([], None)
            else:
                Gio.AppInfo.launch_default_for_uri(gf.get_uri(), None)
        except Exception:
            _spawn(["xdg-open", p])


def open_with(path, appinfo):
    try:
        appinfo.launch([Gio.File.new_for_path(path)], None)
    except Exception:
        _spawn(["xdg-open", path])


def open_with_chooser(path):
    """Full 'Open With…' picker (every installed app, GNOME-style), with an
    'always use' checkbox that makes the choice the permanent default for this
    file type (writes ~/.config/mimeapps.list via Gio)."""
    ct = _content_type(path) or "application/octet-stream"
    dlg = Gtk.AppChooserDialog.new_for_content_type(
        None, Gtk.DialogFlags.MODAL, ct)
    dlg.set_heading(f"Open “{os.path.basename(path)}” with…")
    widget = dlg.get_widget()
    widget.set_show_recommended(True)
    widget.set_show_fallback(True)
    widget.set_show_other(True)

    try:
        desc = Gio.content_type_get_description(ct)
    except Exception:
        desc = ct
    always = Gtk.CheckButton(label=f"Always use for “{desc}” files")
    always.set_margin_start(12)
    always.set_margin_bottom(8)
    always.show()
    dlg.get_content_area().pack_start(always, False, False, 0)

    resp = dlg.run()
    ai = dlg.get_app_info()
    set_default = always.get_active()
    dlg.destroy()
    if resp == Gtk.ResponseType.OK and ai is not None:
        if set_default:
            try:
                ai.set_as_default_for_type(ct)
            except GLib.Error as e:
                sys.stderr.write(f"set default for {ct}: {e}\n")
        open_with(path, ai)


def trash_paths(paths):
    for p in paths:
        try:
            Gio.File.new_for_path(p).trash(None)
        except Exception as e:
            sys.stderr.write(f"trash {p}: {e}\n")


def unique_dest(directory, name):
    """A non-colliding 'name' inside 'directory' (adds ' (copy)', ' (2)', …)."""
    dest = os.path.join(directory, name)
    if not os.path.exists(dest):
        return dest
    stem, ext = os.path.splitext(name)
    cand = os.path.join(directory, f"{stem} (copy){ext}")
    if not os.path.exists(cand):
        return cand
    i = 2
    while True:
        cand = os.path.join(directory, f"{stem} ({i}){ext}")
        if not os.path.exists(cand):
            return cand
        i += 1


def paste_into(directory):
    clip = load_clip()
    if not clip:
        return
    flags = Gio.FileCopyFlags.NONE
    for src in clip["paths"]:
        if not os.path.exists(src):
            continue
        dest = unique_dest(directory, os.path.basename(src.rstrip("/")))
        s, d = Gio.File.new_for_path(src), Gio.File.new_for_path(dest)
        try:
            if clip["mode"] == "cut":
                s.move(d, flags, None, None, None)
            else:
                _copy_recursive(s, d)
        except Exception as e:
            sys.stderr.write(f"paste {src}: {e}\n")
    if clip["mode"] == "cut":
        clear_clip()


def _copy_recursive(src, dest):
    """gio's copy is non-recursive for directories; walk them ourselves."""
    info = src.query_info(Gio.FILE_ATTRIBUTE_STANDARD_TYPE,
                          Gio.FileQueryInfoFlags.NONE, None)
    if info.get_file_type() == Gio.FileType.DIRECTORY:
        dest.make_directory_with_parents(None)
        en = src.enumerate_children(Gio.FILE_ATTRIBUTE_STANDARD_NAME,
                                    Gio.FileQueryInfoFlags.NONE, None)
        while True:
            child = en.next_file(None)
            if child is None:
                break
            _copy_recursive(src.get_child(child.get_name()),
                            dest.get_child(child.get_name()))
    else:
        src.copy(dest, Gio.FileCopyFlags.NONE, None, None, None)


def _unique_in(directory, name):
    if not os.path.exists(os.path.join(directory, name)):
        return os.path.join(directory, name)
    stem, ext = os.path.splitext(name)
    i = 2
    while os.path.exists(os.path.join(directory, f"{stem} {i}{ext}")):
        i += 1
    return os.path.join(directory, f"{stem} {i}{ext}")


def new_folder(directory):
    try:
        Gio.File.new_for_path(_unique_in(directory, "New Folder")).make_directory(None)
    except Exception as e:
        sys.stderr.write(f"new folder: {e}\n")


# "New ›" submenu: built-in common types + the user's ~/Templates files, the
# same convention Nautilus follows. (label, filename, content, executable)
# content "@docx"/"@xlsx"/"@pptx" → minimal-valid OOXML built by _make_ooxml.
GAN_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<project name="Untitled Gantt Project" company="" webLink="http://" view-index="0" gantt-divider-location="300" resource-divider-location="300" version="3.2" locale="en">
    <description/>
    <view zooming-state="default:2" id="gantt-chart"/>
    <view id="resource-table"/>
    <calendars>
        <day-types>
            <day-type id="0"/>
            <day-type id="1"/>
            <default-week id="1" name="default" sun="1" mon="0" tue="0" wed="0" thu="0" fri="0" sat="1"/>
            <only-show-weekends value="false"/>
            <overriden-day-types/>
            <days/>
        </day-types>
    </calendars>
    <tasks empty-milestones="true"/>
    <resources/>
    <allocations/>
    <vacations/>
    <previous/>
    <roles roleset-name="Default"/>
</project>
"""

NEW_FILE_TYPES = [
    ("Text File", "Text File.txt", "", False),
    ("Markdown File", "Markdown File.md", "", False),
    ("Shell Script", "Shell Script.sh", "#!/usr/bin/env bash\n\n", True),
    ("Python Script", "Python Script.py", "#!/usr/bin/env python3\n\n", True),
    ("Word Document", "Document.docx", "@docx", False),
    ("Excel Workbook", "Workbook.xlsx", "@xlsx", False),
    ("PowerPoint Presentation", "Presentation.pptx", "@pptx", False),
    ("Gantt Project", "Project.gan", GAN_TEMPLATE, False),
]


def new_file(directory, name, content, executable):
    dest = _unique_in(directory, name)
    try:
        if content in ("@docx", "@xlsx", "@pptx"):
            _make_ooxml(dest, content[1:])
            return
        with open(dest, "w") as f:
            f.write(content)
        if executable:
            os.chmod(dest, 0o755)
    except Exception as e:
        sys.stderr.write(f"new file {name}: {e}\n")


def _make_ooxml(dest, kind):
    """Write a minimal-valid empty OOXML package (no external deps — Word,
    Excel, PowerPoint and LibreOffice all accept these skeleton parts)."""
    import zipfile
    X = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    CT = "http://schemas.openxmlformats.org/package/2006/content-types"
    PR = "http://schemas.openxmlformats.org/package/2006/relationships"
    OR = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    def rels(*pairs):
        rows = "".join(
            f'<Relationship Id="rId{i}" Type="{t}" Target="{g}"/>'
            for i, (t, g) in enumerate(pairs, 1))
        return f'{X}<Relationships xmlns="{PR}">{rows}</Relationships>'

    parts = {}
    if kind == "docx":
        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        parts["[Content_Types].xml"] = (
            f'{X}<Types xmlns="{CT}">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>")
        parts["_rels/.rels"] = rels((f"{OR}/officeDocument", "word/document.xml"))
        parts["word/document.xml"] = (
            f'{X}<w:document xmlns:w="{W}"><w:body><w:p/>'
            '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
            "</w:body></w:document>")
    elif kind == "xlsx":
        S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        parts["[Content_Types].xml"] = (
            f'{X}<Types xmlns="{CT}">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>")
        parts["_rels/.rels"] = rels((f"{OR}/officeDocument", "xl/workbook.xml"))
        parts["xl/_rels/workbook.xml.rels"] = rels(
            (f"{OR}/worksheet", "worksheets/sheet1.xml"))
        parts["xl/workbook.xml"] = (
            f'{X}<workbook xmlns="{S}" xmlns:r="{OR}">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>")
        parts["xl/worksheets/sheet1.xml"] = (
            f'{X}<worksheet xmlns="{S}"><sheetData/></worksheet>')
    else:  # pptx
        P = "http://schemas.openxmlformats.org/presentationml/2006/main"
        A = "http://schemas.openxmlformats.org/drawingml/2006/main"
        common = (
            '<p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr/></p:spTree></p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping xmlns:a="%s"/></p:clrMapOvr>' % A)
        theme = (
            f'{X}<a:theme xmlns:a="{A}" name="T"><a:themeElements>'
            '<a:clrScheme name="C"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
            '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
            '<a:dk2><a:srgbClr val="44546A"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>'
            '<a:accent1><a:srgbClr val="4472C4"/></a:accent1><a:accent2><a:srgbClr val="ED7D31"/></a:accent2>'
            '<a:accent3><a:srgbClr val="A5A5A5"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4>'
            '<a:accent5><a:srgbClr val="5B9BD5"/></a:accent5><a:accent6><a:srgbClr val="70AD47"/></a:accent6>'
            '<a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>'
            '<a:fontScheme name="F"><a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
            '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
            '<a:fmtScheme name="S"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
            '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
            '<a:lnStyleLst><a:ln><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
            '<a:ln><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
            '<a:ln><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
            '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle>'
            '<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
            '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
            '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
            '</a:fmtScheme></a:themeElements></a:theme>')
        parts["[Content_Types].xml"] = (
            f'{X}<Types xmlns="{CT}">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
            '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
            '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
            "</Types>")
        parts["_rels/.rels"] = rels((f"{OR}/officeDocument", "ppt/presentation.xml"))
        parts["ppt/presentation.xml"] = (
            f'{X}<p:presentation xmlns:p="{P}" xmlns:r="{OR}">'
            '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
            '<p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>'
            '<p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/>'
            "</p:presentation>")
        parts["ppt/_rels/presentation.xml.rels"] = rels(
            (f"{OR}/slideMaster", "slideMasters/slideMaster1.xml"),
            (f"{OR}/slide", "slides/slide1.xml"))
        parts["ppt/slideMasters/slideMaster1.xml"] = (
            f'{X}<p:sldMaster xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{OR}"><p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr/></p:spTree></p:cSld>'
            '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
            "</p:sldMaster>")
        parts["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = rels(
            (f"{OR}/slideLayout", "../slideLayouts/slideLayout1.xml"),
            (f"{OR}/theme", "../theme/theme1.xml"))
        parts["ppt/slideLayouts/slideLayout1.xml"] = (
            f'{X}<p:sldLayout xmlns:p="{P}">{common}</p:sldLayout>')
        parts["ppt/slideLayouts/_rels/slideLayout1.xml.rels"] = rels(
            (f"{OR}/slideMaster", "../slideMasters/slideMaster1.xml"))
        parts["ppt/slides/slide1.xml"] = (
            f'{X}<p:sld xmlns:p="{P}">{common}</p:sld>')
        parts["ppt/slides/_rels/slide1.xml.rels"] = rels(
            (f"{OR}/slideLayout", "../slideLayouts/slideLayout1.xml"))
        parts["ppt/theme/theme1.xml"] = theme

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)


def templates_dir():
    import subprocess
    try:
        d = subprocess.check_output(["xdg-user-dir", "TEMPLATES"], text=True).strip()
        if d and d != HOME and os.path.isdir(d):
            return d
    except Exception:
        pass
    return None


def new_from_template(directory, tpl_path):
    dest = _unique_in(directory, os.path.basename(tpl_path))
    try:
        Gio.File.new_for_path(tpl_path).copy(
            Gio.File.new_for_path(dest), Gio.FileCopyFlags.NONE, None, None, None)
    except Exception as e:
        sys.stderr.write(f"new from template: {e}\n")


def rename(path):
    old = os.path.basename(path)
    dlg = Gtk.Dialog(title="Rename", flags=Gtk.DialogFlags.MODAL)
    dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dlg.add_button("Rename", Gtk.ResponseType.OK)
    dlg.set_default_response(Gtk.ResponseType.OK)
    box = dlg.get_content_area()
    box.set_spacing(8)
    box.set_border_width(12)
    entry = Gtk.Entry()
    entry.set_text(old)
    entry.set_activates_default(True)
    stem, _ext = os.path.splitext(old)
    entry.select_region(0, len(stem) if stem else len(old))
    box.add(Gtk.Label(label="New name:", xalign=0.0))
    box.add(entry)
    dlg.show_all()
    resp = dlg.run()
    new = entry.get_text().strip()
    dlg.destroy()
    if resp == Gtk.ResponseType.OK and new and new != old:
        try:
            Gio.File.new_for_path(path).set_display_name(new, None)
        except Exception as e:
            sys.stderr.write(f"rename: {e}\n")


def properties(path):
    """Self-contained properties dialog (no file-manager dependency)."""
    gf = Gio.File.new_for_path(path)
    try:
        info = gf.query_info(
            ",".join([Gio.FILE_ATTRIBUTE_STANDARD_DISPLAY_NAME,
                      Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE,
                      Gio.FILE_ATTRIBUTE_STANDARD_SIZE,
                      Gio.FILE_ATTRIBUTE_STANDARD_ICON,
                      Gio.FILE_ATTRIBUTE_TIME_MODIFIED]),
            Gio.FileQueryInfoFlags.NONE, None)
    except Exception as e:
        sys.stderr.write(f"properties: {e}\n")
        return
    size = info.get_size()
    mtime = GLib.DateTime.new_from_unix_local(
        info.get_attribute_uint64(Gio.FILE_ATTRIBUTE_TIME_MODIFIED))
    rows = [
        ("Name", info.get_display_name()),
        ("Type", info.get_content_type() or "—"),
        ("Size", GLib.format_size(size) if os.path.isfile(path) else "—"),
        ("Location", os.path.dirname(path)),
        ("Modified", mtime.format("%Y-%m-%d %H:%M") if mtime else "—"),
    ]
    dlg = Gtk.Dialog(title="Properties", flags=Gtk.DialogFlags.MODAL)
    dlg.add_button("Close", Gtk.ResponseType.CLOSE)
    grid = Gtk.Grid(row_spacing=6, column_spacing=14)
    grid.set_border_width(14)
    img = Gtk.Image.new_from_gicon(info.get_icon(), Gtk.IconSize.DIALOG)
    img.set_pixel_size(48)
    grid.attach(img, 0, 0, 1, len(rows))
    for r, (k, v) in enumerate(rows):
        kl = Gtk.Label(label=k, xalign=1.0)
        kl.get_style_context().add_class("dim-label")
        vl = Gtk.Label(label=str(v), xalign=0.0)
        vl.set_selectable(True)
        vl.set_ellipsize(3)
        vl.set_max_width_chars(40)
        grid.attach(kl, 1, r, 1, 1)
        grid.attach(vl, 2, r, 1, 1)
    dlg.get_content_area().add(grid)
    dlg.show_all()
    dlg.run()
    dlg.destroy()


def change_wallpaper():
    # Source of truth for the wallpaper is GNOME's background setting, which
    # gnome-wallpaper-sync.sh mirrors to swaybg.
    _spawn(["gnome-control-center", "background"])


def display_settings():
    if _which("nwg-displays"):
        _spawn(["nwg-displays"])
    else:
        _spawn(["gnome-control-center", "display"])


def set_sort(key):
    s = load_state()
    s["sort"] = key
    save_state(s)


def set_mode(mode):
    s = load_state()
    s["mode"] = mode
    save_state(s)


def set_icon_size(name):
    s = load_state()
    s["icon_size"] = name
    save_state(s)


def set_show_icons(value):
    s = load_state()
    s["show_icons"] = bool(value)
    save_state(s)


def request_tidy():
    """Bump a counter desktop.py watches to snap free icons to the grid once."""
    s = load_state()
    s["tidy"] = int(s.get("tidy", 0)) + 1
    save_state(s)


# Popular icon sizes, mirrored from desktop.py's SIZES keys.
ICON_SIZES = [("small", "Small"), ("medium", "Medium"),
              ("large", "Large"), ("xlarge", "Extra Large")]


# ── small utils ────────────────────────────────────────────────────────
def _spawn(cmd):
    import subprocess
    subprocess.Popen(cmd, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _which(name):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if os.access(os.path.join(d, name), os.X_OK):
            return True
    return False


def _content_type(path):
    try:
        return Gio.File.new_for_path(path).query_info(
            Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE,
            Gio.FileQueryInfoFlags.NONE, None).get_content_type()
    except Exception:
        return None


# ── menu builders ──────────────────────────────────────────────────────
def build_file_menu(kind, paths):
    n = len(paths)
    single = paths[0] if n == 1 else None
    title = os.path.basename(single) if single else f"{n} items"
    m = ContextMenu(title=title, width=230)
    m.add_item("Open", lambda: open_paths(paths), icon="document-open")

    if single is not None:
        ct = _content_type(single)
        if ct:
            apps = Gio.AppInfo.get_recommended_for_type(ct)
            default = Gio.AppInfo.get_default_for_type(ct, False)
            shown = 0
            for ai in apps:
                if default and ai.equal(default):
                    continue
                m.add_item(f"Open with {ai.get_display_name()}",
                           (lambda a=ai: open_with(single, a)),
                           icon="application-x-executable")
                shown += 1
                if shown >= 3:
                    break
        m.add_item("Open With…", lambda: open_with_chooser(single),
                   icon="view-more")

    m.add_separator()
    m.add_item("Cut", lambda: save_clip("cut", paths), icon="edit-cut")
    m.add_item("Copy", lambda: save_clip("copy", paths), icon="edit-copy")
    if single is not None:
        m.add_item("Rename", lambda: rename(single), icon="document-edit")
    m.add_item("Move to Trash", lambda: trash_paths(paths),
               icon="user-trash", danger=True)
    if single is not None:
        m.add_separator()
        m.add_item("Properties", lambda: properties(single),
                   icon="document-properties")
    return m


def build_empty_menu():
    desktop = _desktop_dir()
    s = load_state()
    m = ContextMenu(title="Desktop", width=230)
    m.add_item("New Folder", lambda: new_folder(desktop),
               icon="folder-new")
    new_sub = m.add_submenu("New", icon="document-new")
    for label, fname, content, exe in NEW_FILE_TYPES:
        new_sub.add_item(label,
                         (lambda n=fname, c=content, e=exe:
                          new_file(desktop, n, c, e)))
    tdir = templates_dir()
    if tdir:
        tpls = sorted(t for t in os.listdir(tdir)
                      if not t.startswith(".")
                      and os.path.isfile(os.path.join(tdir, t)))
        if tpls:
            new_sub.add_separator()
            for t in tpls[:8]:
                new_sub.add_item(os.path.splitext(t)[0],
                                 (lambda p=os.path.join(tdir, t):
                                  new_from_template(desktop, p)))
    if load_clip():
        m.add_item("Paste", lambda: paste_into(desktop), icon="edit-paste")
    m.add_separator()
    name_mark = " ✓" if s["sort"] == "name" else ""
    type_mark = " ✓" if s["sort"] == "type" else ""
    m.add_item(f"Sort by Name{name_mark}", lambda: set_sort("name"),
               icon="view-sort-ascending")
    m.add_item(f"Sort by Type{type_mark}", lambda: set_sort("type"),
               icon="view-sort-ascending")
    m.add_separator()
    if s["mode"] == "auto":
        m.add_item("Free Arrangement", lambda: set_mode("free"),
                   icon="view-grid")
    else:
        # In free mode, Snap to Grid is a one-shot clean-up (stays free); the
        # mode toggle back to the always-aligned grid is a separate item.
        m.add_item("Snap to Grid", lambda: request_tidy(), icon="view-grid")
        m.add_item("Auto Arrange", lambda: set_mode("auto"),
                   icon="view-sort-ascending")
    cur_size = s.get("icon_size", "medium")
    sub = m.add_submenu("Icon Size", icon="zoom-in")
    for key, label in ICON_SIZES:
        mark = " ✓" if cur_size == key else ""
        sub.add_item(label + mark, (lambda k=key: set_icon_size(k)))
    m.add_separator()
    if s.get("show_icons", True):
        m.add_item("Hide Desktop Icons", lambda: set_show_icons(False),
                   icon="view-conceal")
    else:
        m.add_item("Show Desktop Icons", lambda: set_show_icons(True),
                   icon="view-reveal")
    m.add_separator()
    m.add_item("Change Wallpaper", change_wallpaper, icon="preferences-desktop-wallpaper")
    m.add_item("Display Settings", display_settings, icon="video-display")
    return m


def _desktop_dir():
    import subprocess
    try:
        d = subprocess.check_output(["xdg-user-dir", "DESKTOP"], text=True).strip()
        if d and os.path.isdir(d):
            return d
    except Exception:
        pass
    return os.path.join(HOME, "Desktop")


def parse_args(argv):
    x = y = None
    kind = None
    paths = []
    it = iter(argv)
    for tok in it:
        if tok == "--x":
            x = int(next(it))
        elif tok == "--y":
            y = int(next(it))
        elif kind is None:
            kind = tok
        else:
            paths.append(tok)
    return kind, paths, x, y


def main():
    kind, paths, x, y = parse_args(sys.argv[1:])
    if kind == "empty":
        m = build_empty_menu()
    elif kind in ("file", "folder", "multi") and paths:
        m = build_file_menu(kind, paths)
    else:
        sys.exit(f"desktop-menu: bad args {sys.argv[1:]}")
    m.popup(anchor_x=x, anchor_y=y, monitor=desktop_monitor())


if __name__ == "__main__":
    main()
