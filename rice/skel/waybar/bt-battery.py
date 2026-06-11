#!/usr/bin/python3
"""bt-battery.py — waybar module: battery of connected bluetooth devices.

Reads org.bluez.Battery1 from the system bus (bluez exposes it for devices
that report battery over AVRCP/HFP — the WH-1000XM5 need Experimental=true
in main.conf). Prints waybar custom-module JSON; empty text when nothing
connected reports a battery, which makes the module disappear entirely.

With --watch it stays alive and re-emits a line whenever bluez signals a
change (device connected/disconnected, percentage moved), so waybar updates
instantly instead of on a polling interval.
"""

import json
import sys

from gi.repository import Gio, GLib

# nf-md glyphs by bluez Device1.Icon (PUA chars, hence the escapes)
GLYPHS = {
    "audio-headset":   "\U000F02CE",   # headset
    "audio-headphones": "\U000F02CB",  # headphones
    "input-mouse":     "\U000F037D",   # mouse
    "input-keyboard":  "\U000F030C",   # keyboard
}
FALLBACK = "\U000F00AF"               # bluetooth


def emit(bus):
    try:
        res = bus.call_sync(
            "org.bluez", "/", "org.freedesktop.DBus.ObjectManager",
            "GetManagedObjects", None,
            GLib.VariantType("(a{oa{sa{sv}}})"),
            Gio.DBusCallFlags.NONE, 3000, None)
        objects = res.unpack()[0]
    except GLib.Error:
        print(json.dumps({"text": ""}), flush=True)
        return

    devs = []
    for path, ifaces in objects.items():
        bat = ifaces.get("org.bluez.Battery1")
        dev = ifaces.get("org.bluez.Device1")
        if bat is None or dev is None or not dev.get("Connected"):
            continue
        name = dev.get("Alias") or dev.get("Name") or path.rsplit("/", 1)[-1]
        glyph = GLYPHS.get(dev.get("Icon", ""), FALLBACK)
        devs.append((name, glyph, int(bat.get("Percentage", 0))))

    if not devs:
        print(json.dumps({"text": ""}), flush=True)
        return

    devs.sort(key=lambda d: d[2])   # worst battery drives text and class
    pct = devs[0][2]
    cls = "critical" if pct <= 10 else "warning" if pct <= 25 else ""
    print(json.dumps({
        "text": "  ".join(f"{g} {p}%" for _, g, p in devs),
        "tooltip": "\n".join(f"{n}: {p}%" for n, _, p in devs),
        "class": cls,
    }), flush=True)


def watch():
    """Persistent mode: re-emit on every relevant bluez DBus signal
    (Battery1 added/removed on connect/disconnect, Percentage changes),
    debounced — connect storms collapse into one refresh."""
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    pending = [0]

    def fire():
        pending[0] = 0
        emit(bus)
        return False

    def refresh(*_args):
        if pending[0]:
            GLib.source_remove(pending[0])
        pending[0] = GLib.timeout_add(400, fire)

    for iface, sig in (
            ("org.freedesktop.DBus.ObjectManager", "InterfacesAdded"),
            ("org.freedesktop.DBus.ObjectManager", "InterfacesRemoved"),
            ("org.freedesktop.DBus.Properties", "PropertiesChanged")):
        bus.signal_subscribe("org.bluez", iface, sig, None, None,
                             Gio.DBusSignalFlags.NONE, refresh)
    emit(bus)
    GLib.MainLoop().run()


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch()
    else:
        emit(Gio.bus_get_sync(Gio.BusType.SYSTEM, None))
