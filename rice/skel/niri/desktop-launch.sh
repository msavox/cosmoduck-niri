#!/usr/bin/env bash
# Launch wrapper for desktop.py — gives niri a single executable to spawn and
# centralizes the log redirect. The desktop is a gtk-layer-shell surface on the
# BOTTOM layer (above the wallpaper, below app tiles) showing ~/Desktop icons.

exec /usr/bin/python3 __HOME__/.config/niri/desktop.py >/tmp/desktop.log 2>&1
