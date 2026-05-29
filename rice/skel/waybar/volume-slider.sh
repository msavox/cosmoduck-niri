#!/bin/bash
# Slider popup to adjust the default sink volume.
# Launched by waybar on-click on the pulseaudio module.

# Avoid double popups if already open
pgrep -af "zenity --scale --title=Volume" >/dev/null && exit 0

cur=$(/usr/bin/pactl get-sink-volume @DEFAULT_SINK@ 2>/dev/null \
      | grep -oP '\d+(?=%)' | head -1)
[ -z "$cur" ] && cur=50

new=$(zenity --scale \
        --title="Volume" \
        --text="System volume" \
        --value="$cur" \
        --min-value=0 --max-value=100 --step=5 2>/dev/null)

[ -n "$new" ] && /usr/bin/pactl set-sink-volume @DEFAULT_SINK@ "${new}%"
