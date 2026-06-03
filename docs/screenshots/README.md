# Screenshots

These feed the gallery in the top-level `README.md`. Filenames are fixed (the
README references them); `capture.sh` writes the same names. Sensitive bits
(weather city, Wi-Fi SSID, work bookmarks, focused-window title in the bar) are
pixelated in post.

| File | Shows |
|------|-------|
| `01-desktop.png` | Hero: wallpaper, conky widget, top bar, dock. |
| `02-tiling.png` | Scrollable tiling — three columns, one scrolled off the left edge. |
| `03-dock.png` | macOS-style dock: pinned apps, running indicators, trash. |
| `04-bar.png` | Top bar: workspaces, blue close-window button, window title, tray, custom modules. |
| `05-cheatsheet.png` | The F1 keyboard cheatsheet (auto-built from the keybinds). |
| `06-calendar.png` | Calendar popup. |
| `07-swaync.png` | swaync notification banners. |
| `08-conky.png` | conky "Cosmoduck" widget close-up. |
| `09-theme-buttons.png` | The theme's macOS-style window buttons + breadcrumb. |
| `10-swaylock.png` | Lock screen (swaylock-effects): the duck composited in the ring over the blurred wallpaper. |
| `11-light.png` | The desktop / GTK apps in the light theme (`cosmoduck-Light`). |
| `12-plymouth.png` | Plymouth boot splash: duck + loading bar over the scrolling kernel/systemd log. |
| `13-dock-manager.png` | The dock manager window: pin/unpin apps + the dock-height slider. |

`10-swaylock.png` locks every output at once, so it's awkward to self-capture —
easiest is `sleep 4; grim -o <output> 10-swaylock.png &` then lock. `12-plymouth.png`
can't be grabbed live (plymouthd contends the DRM with niri); shoot the real boot
(phone photo) or compose a static mockup from the theme assets in
`/usr/share/plymouth/themes/cosmoduck/`.

> Note: `10-swaylock.png` and `12-plymouth.png` are currently **composed mockups**
> built from the real theme assets (see the geometry in `swaylock-blur.sh` and
> `cosmoduck.script`), since neither can be grabbed live. Replace them with real
> captures/photos when convenient.

## How (for your own setup)

```sh
sudo apt install grim slurp
./capture.sh          # walks you through each shot; 'f' full, 's' region
```

## ⚠️ Before committing

Public forever once pushed. Check each PNG for: conky **weather city**, **Wi-Fi
SSID**, file/window **titles**, browser tabs, tray contents, calendar events.
Pixelate (`convert in.png -region WxH+X+Y -blur 0x12 out.png`) or re-shoot.
