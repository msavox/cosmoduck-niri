#!/usr/bin/env bash
# desktop-toggle.sh — turn the desktop-icons surface (desktop.py) on/off.
#
# Usage:
#   desktop-toggle.sh status   -> JSON for waybar (eye icon + active/inactive)
#   desktop-toggle.sh toggle   -> on<->off
#   desktop-toggle.sh start|stop
#
# Note: this hides the whole surface (process up/down). To merely hide the icons
# while keeping the desktop's right-click menu, use "Hide Desktop Icons" in the
# context menu instead (state.show_icons).
set -uo pipefail

NIRI_DIR="$HOME/.config/niri"
# Hardened so test commands containing the string don't match (cf. conky-toggle).
RE='python3 .*/desktop\.py'

eye_on=$(printf '\U0000f06e')    # nf-fa-eye
eye_off=$(printf '\U0000f070')   # nf-fa-eye-slash

running() { pgrep -u "$USER" -f "$RE" >/dev/null 2>&1; }

start() {
  setsid bash "$NIRI_DIR/desktop-launch.sh" >/dev/null 2>&1 < /dev/null &
  disown 2>/dev/null || true
}

stop() {
  pkill -u "$USER" -f "$RE" 2>/dev/null || true
}

case "${1:-status}" in
  start)  start ;;
  stop)   stop ;;
  toggle) if running; then stop; else start; fi ;;
  status)
    if running; then
      jq -nc --arg t "$eye_on"  '{text:$t, tooltip:"Desktop icons: ON (click to hide)", class:"active"}'
    else
      jq -nc --arg t "$eye_off" '{text:$t, tooltip:"Desktop icons: OFF (click to show)", class:"inactive"}'
    fi
    ;;
  *) echo "Usage: $(basename "$0") {status|toggle|start|stop}" >&2; exit 2 ;;
esac
