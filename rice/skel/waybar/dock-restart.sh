#!/usr/bin/env bash
# Cleanly restart only the waybar dock (to apply new CSS/SVGs, bypassing the
# pixbuf cache). Launch it via `niri msg action spawn` so it runs in niri's
# environment, detached from the calling shell.
cfg="$HOME/.config/waybar"
pkill -f 'waybar -c .*dock\.jsonc'
sleep 0.6
setsid waybar -c "$cfg/dock.jsonc" -s "$cfg/dock.css" >/tmp/waybar-dock.log 2>&1 < /dev/null &
disown 2>/dev/null || true
