#!/usr/bin/env bash
# Launch wrapper for conky-bg.py — exists only to give niri a single
# executable to spawn and to centralize the log redirect.

exec env DISPLAY=:0 /usr/bin/python3 \
    __HOME__/.config/niri/conky-bg.py \
    >/tmp/conky-bg.log 2>&1
