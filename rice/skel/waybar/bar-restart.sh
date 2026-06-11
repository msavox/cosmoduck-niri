#!/usr/bin/env bash
# Cleanly restart the top waybar only (to apply new config/CSS).
# Launch via `niri msg action spawn` so it runs in niri's environment,
# detached from the calling shell (see dock-restart.sh).
cfg="$HOME/.config/waybar"
pkill -f 'waybar -c .*config\.jsonc'
sleep 0.6
setsid waybar -c "$cfg/config.jsonc" -s "$cfg/style.css" >/tmp/waybar-top.log 2>&1 < /dev/null &
disown 2>/dev/null || true
