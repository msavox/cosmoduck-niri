#!/bin/bash
# Custom Waybar module: macOS-style "close window" button (round dot).
# Shows the × only when a window is focused; on the empty desktop the module
# stays empty (text="") and Waybar hides it.
w=$(niri msg --json focused-window 2>/dev/null)
if [ -z "$w" ] || [ "$w" = "null" ]; then
    printf '{"text":""}\n'
    exit 0
fi
# × = MULTIPLICATION SIGN (×). Emitted as a JSON escape so the glyph is not
# altered along the writing chain.
printf '{"text":"\\u00d7","tooltip":"Close window","class":"has-window"}\n'
