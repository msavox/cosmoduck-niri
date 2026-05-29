#!/usr/bin/env bash
# dock-click.sh <id>
# If the app is already open, focus it. Otherwise launch it.
set -euo pipefail
id="${1:?missing app id}"
apps="$HOME/.config/waybar/dock-apps.json"

entry=$(jq -c --arg id "$id" '.[] | select(.id==$id)' "$apps")
cmd=$(jq -r .command <<<"$entry")
match=$(jq -r .match <<<"$entry")

win_id=""
if [[ -n "$match" ]]; then
  win_id=$(niri msg --json windows 2>/dev/null \
    | jq -r --arg m "$match" '[.[] | select(.app_id != null and (.app_id | test($m)))][0].id // empty')
fi

if [[ -n "$win_id" ]]; then
  niri msg action focus-window --id "$win_id"
else
  # Workaround: niri config exports DISPLAY=:0 but xwayland-satellite runs on :2
  # (the X0 socket was held by a leftover at boot). X11 apps (Avalonia,
  # non-wayland Qt) crash with XOpenDisplay failed without this override.
  # Check the real display by querying xwayland-satellite.
  xws_disp=$(pgrep -af '^xwayland-satellite' | head -1 | grep -oE ':[0-9]+' | head -1)
  setsid sh -c "${xws_disp:+DISPLAY=$xws_disp }$cmd" >/dev/null 2>&1 < /dev/null &
fi
