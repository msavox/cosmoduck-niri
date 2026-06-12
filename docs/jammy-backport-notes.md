# jammy → niri: backport notes & gotchas

The hard-won details behind getting niri (and a usable desktop around it) onto
Ubuntu 22.04. If you're hitting one of these, this is the page search engines
hopefully sent you to.

## Compositor & toolchain

### niri won't link: `libinput_device_config_dwtp_set_enabled`
jammy's libinput is < 1.27 and has no `dwtp` (disable-while-trackpointing) config
symbol. niri calls it unconditionally. Fix: patch the call out
(`build/patches/niri-0001-dwtp-libinput-jammy.patch`). dwtp simply becomes a
no-op; everything else works.

### Firefox aborts under niri: *"wl_pointer has no event 9"*
jammy's **libwayland-client 1.20** predates high-resolution scroll
(`wl_pointer.axis_value120`, event #9). Apps built against newer wayland send it,
the old client lib doesn't know it, and aborts. Fix: build libwayland **1.23.1**
and install just `libwayland-client.so` under `/usr/local/lib` (added to the
loader path via `ld.so.conf.d`). It's ABI-compatible (soname `.0`) and shadows
the system one machine-wide. Fully restart Firefox afterwards.

### libdisplay-info missing
Not packaged on jammy; niri needs it for EDID parsing. Plain meson build into
`/usr/local`. Bonus: ships `di-edid-decode`.

### Xwayland too old
jammy's Xwayland doesn't speak the protocol versions niri uses. Build Xwayland
from `xorg/xserver` (`xwayland-23.1.0`) against a **staged** newer wayland +
wayland-protocols (private prefix, `PKG_CONFIG_PATH`) so only Xwayland sees the
newer libs. This is the fiddliest build (`build/03-xwayland.sh`).

### xwayland-satellite display races
`xwayland-satellite` occasionally lands on `:2` with an orphaned `X0` socket,
which makes some X11 apps (e.g. SourceGit, FreeCAD) crash on launch. The dock
launcher works around it by pinning/clearing the display before exec.

## Desktop bits

### swaylock 1.5 doesn't lock
jammy's swaylock relies on the deprecated input-inhibitor protocol. Build current
swaylock (reports `v1.8.5`) from source. The rice wraps it as `swaylock-blur.sh`
(locks over a blurred snapshot of the wallpaper).

### swaync stylesheet silently breaks
swaync 0.9 is **GTK3**. GTK3's CSS engine chokes on the `overflow` property and,
crucially, **drops the entire stylesheet** rather than just that rule — a silent
fail. Keep `overflow` out of `style.css`. (Also: run it with stderr redirected
under `spawn-at-startup`, it's noisy.)

### conky under niri (no X root window)
conky draws onto the X11 root window, which doesn't exist on a Wayland
compositor. The bridge (`conky-bg.py`) grabs conky's X11 pixmap and blits it onto
a niri **layer-shell BACKGROUND** surface — above the wallpaper, below the apps.
Toggled from waybar (the 👁 icon).

### Electron apps crash on XWayland
Teams/Slack/Discord/VSCode launched with `--ozone-platform=x11` crash under the
satellite XWayland (no `XAUTHORITY`). Force Wayland ozone in their `.desktop`
overrides instead.

### IT keyboard layout: some niri binds don't fire
On an Italian layout, `Mod+Equal` / `Shift+Minus` keysyms never arrive. Use
`Mod+Plus` and `Ctrl` instead of `Shift` in `config.kdl`.

### GNOME integration
niri reuses the GNOME stack for Wi-Fi/Bluetooth/background. Notes:
- `gnome-control-center` 41 shows "no Bluetooth found" without gsd-rfkill —
  `spawn-at-startup "/usr/libexec/gsd-rfkill"`.
- Wallpaper sync reads the live value with `dconf read` (not `gsettings`, which a
  keyfile GIO backend can shadow).

### Bluetooth devices never auto-reconnect (bluez 5.64 + `Experimental`)
The bar's bt-battery module needs `Experimental = true` in
`/etc/bluetooth/main.conf` (it reads the D-Bus `org.bluez.Battery1` interface;
for headsets the percentage arrives via PipeWire's BatteryProvider, which is
gated behind that flag). But on jammy's bluez **5.64** the flag is poison: the
adv-monitor manager takes the MSFT-offload path and passive scanning is never
(re)enabled. Verified with `btmon`: on startup the kernel gets the bonded
device into the LE accept list with auto-connect action 0x02, but `LE Set
Extended Scan Enable` is never issued — the controller is deaf, so bonded
mice/headphones **never reconnect on their own** and every power cycle needs a
manual connect. With the flag off reconnection works, but headset battery
reporting is gone — a strict either/or on 5.64.

bluez **5.86** (built by `build/10-bluez.sh`, shipped in the `.deb`) fixes the
coexistence: `bluetoothd` installs under `/usr/local/libexec/bluetooth` and a
systemd drop-in (`/etc/systemd/system/bluetooth.service.d/usr-local.conf`)
points `bluetooth.service` at it. The jammy bluez package stays installed
(obexd, udev rules, D-Bus policy). Rollback: delete the drop-in,
`systemctl daemon-reload && systemctl restart bluetooth`.

## Why `/usr/local`?
Everything installs under `/usr/local` to match how it was compiled and to avoid
fighting dpkg over `/usr`. It's intentional and jammy-specific. On 24.04+ you
should just install niri from apt and use only the `rice/` half of this repo.
