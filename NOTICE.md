# Third-party components & licenses

This project assembles, patches and themes a number of upstream projects. They
remain under their own licenses. The list below is provided in good faith —
**verify each upstream's `LICENSE` file**, as licenses can change between
versions.

## Compiled / bundled software

| Component | Upstream | License (verify upstream) |
|-----------|----------|---------------------------|
| niri | https://github.com/YaLTeR/niri | GPL-3.0-or-later |
| libwayland | https://gitlab.freedesktop.org/wayland/wayland | MIT |
| libdisplay-info | https://gitlab.freedesktop.org/emersion/libdisplay-info | MIT |
| Xwayland (xserver) | https://gitlab.freedesktop.org/xorg/xserver | MIT/X11 |
| xwayland-satellite | https://github.com/Supreeeme/xwayland-satellite | MPL-2.0 |
| SwayNotificationCenter | https://github.com/ErikReider/SwayNotificationCenter | GPL-3.0 |
| nwg-dock | https://github.com/nwg-piotr/nwg-dock | MIT |
| swaylock | https://github.com/swaywm/swaylock | MIT |

The niri patches in `build/patches/` are modifications of niri and are therefore
covered by niri's GPL-3.0-or-later license.

## Theme & widget (derivative works — NOT MIT)

| Asset | Based on | License |
|-------|----------|---------|
| `cosmoduck-*` GTK theme (`rice/themes/`) | [WhiteSur-gtk-theme](https://github.com/vinceliuice/WhiteSur-gtk-theme) by vinceliuice | GPL-3.0 (as a WhiteSur derivative) |
| conky "Regulus-MOD-Cosmoduck" widget (`rice/skel/conky/`) | "Regulus" conky theme by Closebox73 | inherits the original theme's license — see upstream |

## Third-party assets the `.deb` bundles but this repo does NOT redistribute

These are pulled from the system at package-build time (and are deps you install
yourself on the clone path), not committed here:

| Asset | Upstream | License |
|-------|----------|---------|
| Bibata-Modern-Classic cursor | https://github.com/ful1e5/Bibata_Cursor | GPL-3.0 |
| CaskaydiaCove Nerd Font | https://github.com/ryanoasis/nerd-fonts (Cascadia Code) | SIL OFL 1.1 |

If you redistribute the prebuilt `.deb`, make sure you are comfortable
redistributing these bundled assets under their licenses.
