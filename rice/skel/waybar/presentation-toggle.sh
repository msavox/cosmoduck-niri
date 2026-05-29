#!/bin/sh
# Presentation / fullscreen mode for apps:
# hides (or re-shows) the top bar AND the dock together.
#
# Uses waybar's SIGUSR1 signal = toggle bar visibility.
# Does NOT kill the process: waybar stays alive (with its dock-status.sh),
# the bar disappears/reappears instantly. The tray dropdown (config-tray.jsonc)
# is intentionally left out (it is handled separately by the chevron).
#
# Top bar and dock are always signaled together, so they stay
# in sync (one toggle hides both, the next re-shows them).

pkill -USR1 -f 'waybar -c __HOME__/.config/waybar/config.jsonc'
pkill -USR1 -f 'waybar -c __HOME__/.config/waybar/dock.jsonc'
