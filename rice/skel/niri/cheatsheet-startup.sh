#!/usr/bin/env bash
# Show the shortcuts cheatsheet (single GTK window with a checkbox) at login,
# UNTIL the user ticks "Don't show at startup": that checkbox creates the file
# ~/.config/niri/cheatsheet-disabled and it no longer appears on later logins.
# (Untick it in the window, or `rm` the file, to re-enable it.)

FLAG="$HOME/.config/niri/cheatsheet-disabled"

# Already disabled by the user -> show nothing.
[ -e "$FLAG" ] && exit 0

# Wait for the session/compositor to be ready.
sleep 2

exec python3 "$HOME/.config/niri/cheatsheet.py"
