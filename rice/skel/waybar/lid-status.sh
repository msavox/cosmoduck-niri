#!/usr/bin/env bash
# lid-status.sh — waybar "coffee cup" module for lid-keep-awake.
# Port of a GNOME extension (lid-keep-awake) to niri/waybar.
# Prints JSON {text,tooltip,class} for waybar:
#   text  = coffee-cup glyph (Nerd Font fa-coffee, U+F0F4)
#   class = "active" when the lid-switch inhibitor is on, otherwise "inactive"
set -euo pipefail

LKA="$HOME/.local/bin/lid-keep-awake"
coffee=$(printf '')   # nf-fa-coffee  (CaskaydiaCove NF / Symbols Nerd Font)

if [[ -x "$LKA" ]] && "$LKA" status 2>/dev/null | grep -q '^RUNNING'; then
  jq -nc --arg t "$coffee" \
    '{text:$t, tooltip:"Lid keep-awake: ON — closing the lid does NOT suspend", class:"active"}'
else
  jq -nc --arg t "$coffee" \
    '{text:$t, tooltip:"Lid keep-awake: OFF — closing the lid suspends", class:"inactive"}'
fi
