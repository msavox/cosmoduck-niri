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

# waybar class array: "running" if the app is open + "nbK" for the notification badge.
classes=()
if [[ -n "$match" ]]; then
  if niri msg --json windows 2>/dev/null \
     | jq -e --arg m "$match" 'any(.[]; .app_id != null and (.app_id | test($m)))' >/dev/null; then
    classes+=("running")
  fi
fi

# per-app notification count (semantics "B"), maintained by notif-count.py
counts="$HOME/.config/waybar/notif-counts.json"
n=0
[[ -f "$counts" ]] && n=$(jq -r --arg id "$id" '(.[$id] // []) | length' "$counts" 2>/dev/null || echo 0)
if (( n > 0 )); then
  k=$n; (( n > 9 )) && k="9p"
  classes+=("nb${k}")
fi

cls_json=$(printf '%s\n' "${classes[@]:-}" | jq -R . | jq -sc 'map(select(length>0))')
jq -nc --arg text "$icon" --arg tt "$name" --argjson cls "$cls_json" \
  '{text:$text, tooltip:$tt, class:$cls}'
