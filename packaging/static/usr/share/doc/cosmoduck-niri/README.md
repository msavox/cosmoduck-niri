# cosmoduck-niri

A complete [niri](https://github.com/YaLTeR/niri) Wayland desktop for **Ubuntu 22.04 (jammy)**, where niri isn't packaged. Bundles the compositor and tools compiled from source, the Cosmoduck GTK theme, a waybar top bar + macOS-style dock, swaync notifications, and the conky Cosmoduck widget running under niri via a custom X11→layer-shell bridge.

## Install

```bash
sudo apt install ./cosmoduck-niri_1.0.1_amd64.deb   # pulls all dependencies
cosmoduck-niri-setup                                 # run as your normal user (NOT sudo)
```

Then log out and pick the **niri** session in your display manager.

`cosmoduck-niri-setup` copies the config into `~/.config` (backing up anything already there as `*.bak-<timestamp>`), installs the lid keep-awake user service, sets the GTK theme/cursor, and generates the dock for your local icon theme.

## What's inside

- **Compositor & tools** in `/usr/local`: niri, Xwayland, xwayland-satellite, swaylock 1.8.5, swaync, libdisplay-info (all built from source for jammy).
- **Theme** `cosmoduck-*` in `/usr/share/themes`; **Bibata-Modern-Classic** cursor; **CaskaydiaCove Nerd Font** (Regular/Bold) for the bar glyphs.
- **Per-user config**: niri (`config.kdl`), waybar (top bar + dock + tray), swaync, the conky Cosmoduck widget + its bridge.
- **Waybar toggles**: ☕ lid keep-awake (anti-suspend on lid close) and 👁 conky widget show/hide.
- **Dock**: generic preset (Files, Firefox, Terminal, Text Editor, Settings, Software, Calculator, Dock Setup, Trash). Edit it from the **Dock Setup** icon or `~/.config/waybar/dock-apps.json` + `dock-gen.sh`.

## After install — things to personalize

- **conky weather**: put your free OpenWeatherMap API key and city id in
  `~/.config/conky/Regulus-MOD-Cosmoduck/scripts/weather-v2.0.sh`
  (shipped with placeholders — get a key at <https://openweathermap.org/api>).
- **monitors**: run `nwg-displays` to lay out your screens; it saves to
  `~/.config/niri/monitor.kdl` (ships empty = auto-detect).

## Notes

- Binaries install under `/usr/local` to match how they were built; this is
  intentional (not Debian-policy `/usr`). jammy-only — on Ubuntu 24.04+ install
  niri from its PPA/apt instead.
- The GNOME stack (control-center, settings-daemon, NetworkManager, bluez,
  gnome-bluetooth) is a dependency: niri reuses it for Wi-Fi, Bluetooth and the
  desktop background (synced to niri by `gnome-wallpaper-sync.sh`).

## Uninstall

```bash
sudo apt remove cosmoduck-niri
```

Per-user config in `~/.config/{niri,waybar,swaync,conky}` is left in place; remove it by hand if you want.
