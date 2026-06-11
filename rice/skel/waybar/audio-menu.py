#!/usr/bin/python3
"""audio-menu.py — output/input device switcher for the top-bar volume icon.

macOS-style: click the volume module → a ctxmenu with the current output and
input, each opening a flyout listing the available devices (default marked
with a check). Selecting one calls pactl set-default-sink/source; running
streams follow the default (WirePlumber), and the OSD daemon's pactl
subscribe watcher gives the visual feedback for free.

Run with /usr/bin/python3 so the GIR typelibs resolve without env tweaks.
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/.config/waybar"))
from ctxmenu import ContextMenu  # noqa: E402

PACTL = "/usr/bin/pactl"

# Monitor-local x of the pulseaudio module in the top bar (calibrated by
# measurement, same approach as tray-dropdown's CHEVRON_X; drifts slightly
# when the right-side modules change width).
VOLUME_X = 1930
TOPBAR_BOTTOM = 44   # top bar: height 30 + margin-top 8 + a small gap
WIDTH = 250


def pactl(*args):
    return subprocess.check_output([PACTL, *args], text=True, timeout=3)


def list_devices(kind):
    """[{name, desc}] from `pactl list sinks|sources` (monitors excluded)."""
    devs, cur = [], {}
    for raw in pactl("list", kind).splitlines():
        if raw.startswith(("Sink #", "Source #")):
            if cur.get("name"):
                devs.append(cur)
            cur = {}
            continue
        line = raw.strip()
        if line.startswith("Name:"):
            cur["name"] = line.split(":", 1)[1].strip()
        elif line.startswith("Description:"):
            cur["desc"] = line.split(":", 1)[1].strip()
    if cur.get("name"):
        devs.append(cur)
    return [d for d in devs if not d["name"].endswith(".monitor")]


def device_icon(name, desc, is_input):
    text = (name + " " + desc).lower()
    if "bluez" in text or "headset" in text or "headphone" in text:
        return "audio-headset" if is_input else "audio-headphones"
    if "hdmi" in text or "displayport" in text:
        return "video-display"
    return "audio-input-microphone" if is_input else "audio-speakers"


def add_device_items(submenu, devices, default_name, set_cmd, is_input):
    for d in devices:
        icon = ("object-select" if d["name"] == default_name
                else device_icon(d["name"], d.get("desc", ""), is_input))
        submenu.add_item(
            d.get("desc", d["name"]),
            lambda n=d["name"]: subprocess.run([PACTL, set_cmd, n]),
            icon=icon)


def card_for_sink(sink_name, cards):
    """The card owning a sink, matched by name: bluez_output.MAC.x belongs
    to bluez_card.MAC, alsa_output.DEV.y to alsa_card.DEV (the json sink
    object's `card` field is null under pipewire's pactl shim)."""
    probe = sink_name.replace("_output.", "_card.", 1)
    for c in cards:
        if probe.startswith(c["name"] + "."):
            return c
    return None


def add_profile_menu(m, def_sink):
    """Submenu listing the available profiles of the default sink's card
    (e.g. WH-1000XM5: A2DP high quality vs HSP/HFP headset with mic)."""
    try:
        cards = json.loads(pactl("--format=json", "list", "cards"))
    except (subprocess.SubprocessError, OSError, ValueError):
        return
    card = card_for_sink(def_sink, cards)
    if card is None:
        return
    profiles = [(k, v.get("description", k))
                for k, v in card.get("profiles", {}).items()
                if v.get("available") and k != "off"]
    if len(profiles) < 2:
        return
    active = card.get("active_profile", "")
    active_desc = dict(profiles).get(active, active).split(" (")[0]
    sub = m.add_submenu(f"Profile · {active_desc}", icon="emblem-system")
    for key, desc in profiles:
        sub.add_item(
            desc,
            lambda k=key: subprocess.run(
                [PACTL, "set-card-profile", card["name"], k]),
            icon="object-select" if key == active else "audio-card")


def main():
    sinks = list_devices("sinks")
    sources = list_devices("sources")
    def_sink = pactl("get-default-sink").strip()
    def_source = pactl("get-default-source").strip()

    def desc_of(devs, name):
        for d in devs:
            if d["name"] == name:
                return d.get("desc", name)
        return "—"

    m = ContextMenu(title="Audio", width=WIDTH)
    out = m.add_submenu(f"Output · {desc_of(sinks, def_sink)}",
                        icon="audio-speakers")
    add_device_items(out, sinks, def_sink, "set-default-sink", False)
    inp = m.add_submenu(f"Input · {desc_of(sources, def_source)}",
                        icon="audio-input-microphone")
    add_device_items(inp, sources, def_source, "set-default-source", True)
    add_profile_menu(m, def_sink)
    m.add_separator()
    m.add_item("Volume Mixer…",
               lambda: subprocess.Popen(["pavucontrol"]),
               icon="multimedia-volume-control")
    m.add_item("Sound Settings…",
               lambda: subprocess.Popen(["gnome-control-center", "sound"]),
               icon="preferences-system")
    m.popup(anchor_x=VOLUME_X - WIDTH // 2, anchor_y=TOPBAR_BOTTOM)


if __name__ == "__main__":
    main()
