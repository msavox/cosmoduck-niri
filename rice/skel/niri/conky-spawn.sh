#!/usr/bin/env bash
# Launch the Cosmoduck conky widget under niri via xwayland-satellite.
# Does not touch the conky configs: uses Regulus-MOD-Cosmoduck/config/Regulus.conf
# like the ubuntu-wayland branch in ~/.conky/conky-startup.sh.
#
# The positioning and the look (no decoration, no focus-ring) are handled
# by the window-rule app-id="^Conky$" in ~/.config/niri/config.kdl.

set -u

CONFIG="$HOME/.config/conky/Regulus-MOD-Cosmoduck/config/Regulus.conf"
LOG="/tmp/conky-niri.log"

# Wait for xwayland-satellite to be active (max ~5s)
for _ in $(seq 1 20); do
  XWS_DISP=$(pgrep -af '^xwayland-satellite' 2>/dev/null | head -1 | grep -oE ':[0-9]+' | head -1 || true)
  if [[ -n "${XWS_DISP:-}" ]]; then break; fi
  sleep 0.25
done

if [[ -z "${XWS_DISP:-}" ]]; then
  echo "[conky-spawn] xwayland-satellite not found, abort." >>"$LOG"
  exit 1
fi

# Conky sometimes refuses to start if it is already running (with the same config).
# Kill only the existing user instances.
pkill -u "$USER" -x conky 2>/dev/null || true
sleep 0.3

DISPLAY="$XWS_DISP" conky -c "$CONFIG" >>"$LOG" 2>&1 &
disown
echo "[conky-spawn] $(date -Iseconds) launched conky on DISPLAY=$XWS_DISP" >>"$LOG"
