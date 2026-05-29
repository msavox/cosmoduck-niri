#!/usr/bin/env bash
# dock-status.sh <id>
# Print JSON for waybar: text/tooltip from the app, class="running" if open in niri.
set -euo pipefail
id="${1:?missing app id}"
apps="$HOME/.config/waybar/dock-apps.json"

entry=$(jq -c --arg id "$id" '.[] | select(.id==$id)' "$apps")
name=$(jq -r .name  <<<"$entry")
match=$(jq -r .match <<<"$entry")
# Non-empty space: needed so waybar does not hide the module.
# The real icon comes from background-image (GTK theme) in dock-pinned.css.
icon=" "

cls=""
if [[ -n "$match" ]]; then
  if niri msg --json windows 2>/dev/null \
     | jq -e --arg m "$match" 'any(.[]; .app_id != null and (.app_id | test($m)))' >/dev/null; then
    cls="running"
  fi
fi

if [[ -n "$cls" ]]; then
  jq -nc --arg text "$icon" --arg tt "$name" --arg cls "$cls" \
    '{text:$text, tooltip:$tt, class:$cls}'
else
  jq -nc --arg text "$icon" --arg tt "$name" \
    '{text:$text, tooltip:$tt}'
fi
