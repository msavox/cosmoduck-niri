#!/usr/bin/env bash
# dock-click.sh <id> [new]
# Default: if the app is already open, focus it; otherwise launch it.
# With "new" as the 2nd argument: always launch a fresh instance (used by the
# right-click context menu's "New Window" entry, see dock-menu.py).
set -euo pipefail
id="${1:?missing app id}"
mode="${2:-}"
apps="$HOME/.config/waybar/dock-apps.json"
# Temporary auto-pins (dock-autopin.py) live in a second file; /dev/null
# slurps to nothing, so a missing file degrades to the pinned list alone.
auto="$HOME/.config/waybar/dock-apps-auto.json"
[[ -f "$auto" ]] || auto=/dev/null

entry=$(jq -sc --arg id "$id" 'add | map(select(.id==$id)) | first // empty' "$apps" "$auto")
cmd=$(jq -r .command <<<"$entry")
match=$(jq -r .match <<<"$entry")

# Clear this app's notification badge on click (semantics "B").
"$HOME/.config/waybar/notif-count.py" clear "$id" 2>/dev/null || true

win_id=""
if [[ -n "$match" && "$mode" != "new" ]]; then
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
