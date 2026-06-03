#!/usr/bin/env bash
# setup.sh — install the Cosmoduck-niri rice for the CURRENT user, straight
# from a clone of this repo (no .deb needed).
#
# Run once, as your normal user (NOT root). Any existing config is backed up.
# If you installed the .deb instead, run `cosmoduck-niri-setup` — same logic,
# but it reads the config from /usr/share/cosmoduck-niri and the theme is
# already installed system-wide.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "Run as a normal user, NOT with sudo/root." >&2
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
SKEL="$HERE/skel"
THEMES="$HERE/themes"
CFG="$HOME/.config"
TS="$(date +%Y%m%d-%H%M%S)"

echo ">> Installing the Cosmoduck-niri config for user $USER"

# 1. config dirs (back up anything already there)
for d in niri waybar swaync conky; do
  if [ -e "$CFG/$d" ]; then
    mv "$CFG/$d" "$CFG/$d.bak-$TS"
    echo "   backup: ~/.config/$d -> $d.bak-$TS"
  fi
  install -d "$CFG/$d"
  cp -a "$SKEL/$d/." "$CFG/$d/"
done

# 2. lid keep-awake: helper script + user systemd unit
install -d "$HOME/.local/bin" "$CFG/systemd/user"
install -m755 "$SKEL/bin/lid-keep-awake"                  "$HOME/.local/bin/lid-keep-awake"
install -m644 "$SKEL/systemd-user/lid-keep-awake.service" "$CFG/systemd/user/lid-keep-awake.service"

# 3. GTK theme (only when running from a clone; the .deb installs it system-wide)
if [ -d "$THEMES" ]; then
  install -d "$HOME/.local/share/themes"
  cp -a "$THEMES/"cosmoduck-* "$HOME/.local/share/themes/"
  echo "   themes -> ~/.local/share/themes"
fi

# 4. replace the __HOME__ placeholder with the real home in every text file
TARGETS="$CFG/niri $CFG/waybar $CFG/swaync $CFG/conky $CFG/xdg-desktop-portal-wlr $HOME/.local/bin/lid-keep-awake $CFG/systemd/user/lid-keep-awake.service"
grep -rIl '__HOME__' $TARGETS 2>/dev/null | while read -r f; do
  sed -i "s#__HOME__#$HOME#g" "$f"
done

# 5. make scripts executable
find "$CFG/niri" "$CFG/waybar" -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod 755 {} + 2>/dev/null || true
find "$CFG/conky/Regulus-MOD-Cosmoduck/scripts" -type f -exec chmod 755 {} + 2>/dev/null || true

# 6. theme / cursor (best-effort; needs a running dbus/gsettings session)
if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.desktop.interface gtk-theme     'cosmoduck-Dark'         2>/dev/null || true
  gsettings set org.gnome.desktop.interface color-scheme  'prefer-dark'            2>/dev/null || true
  gsettings set org.gnome.desktop.interface cursor-theme  'Bibata-Modern-Classic'  2>/dev/null || true
fi

# 7. reload user systemd; generate the dock CSS for the local icon theme
/usr/bin/systemctl --user daemon-reload 2>/dev/null || true
bash "$CFG/waybar/dock-gen.sh" --no-reload 2>/dev/null || true

cat <<EOF

Done.
  - At the login screen, pick the 'niri' session.
  - Fonts & cursor: install the CaskaydiaCove Nerd Font and the
    Bibata-Modern-Classic cursor for full fidelity (see README "Dependencies").
  - Conky weather: put YOUR free OpenWeatherMap API key and city in
    ~/.config/conky/Regulus-MOD-Cosmoduck/scripts/weather-v2.0.sh
  - Tray icons: ☕ = lid keep-awake (stay awake with the lid closed),
    the eye = show/hide the conky widget.
  - Monitors: run nwg-displays to configure and save ~/.config/niri/monitor.kdl
EOF
