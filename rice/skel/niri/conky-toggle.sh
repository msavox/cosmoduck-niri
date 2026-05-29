#!/usr/bin/env bash
# conky-toggle.sh — turns the Conky (Cosmoduck) widget + the conky-bg.py
# bridge on/off from waybar. Does NOT modify any conky config: it uses the
# existing spawn scripts (conky-spawn.sh + conky-bg-launch.sh).
#
# Usage:
#   conky-toggle.sh status   -> JSON for waybar (eye icon + class active/inactive)
#   conky-toggle.sh toggle   -> on<->off (waybar on-click)
#   conky-toggle.sh start|stop
set -uo pipefail

NIRI_DIR="$HOME/.config/niri"
CONKY_RE='conky -c .*Regulus-MOD-Cosmoduck'
BRIDGE_RE='python3 .*conky-bg\.py'

eye_on=$(printf '')    # nf-fa-eye        (conky visible)
eye_off=$(printf '')   # nf-fa-eye-slash  (conky hidden)

conky_running() { pgrep -u "$USER" -f "$CONKY_RE" >/dev/null 2>&1; }

start() {
  setsid bash "$NIRI_DIR/conky-spawn.sh"      >/dev/null 2>&1 < /dev/null &
  disown 2>/dev/null || true
  # the bridge attaches by itself as soon as it finds the conky window (try_attach
  # polls), but give it a moment to start after conky.
  ( sleep 1; setsid bash "$NIRI_DIR/conky-bg-launch.sh" >/dev/null 2>&1 < /dev/null & ) &
  disown 2>/dev/null || true
}

stop() {
  pkill -u "$USER" -f "$BRIDGE_RE" 2>/dev/null || true
  pkill -u "$USER" -f "$CONKY_RE"  2>/dev/null || true
}

case "${1:-status}" in
  start)  start ;;
  stop)   stop ;;
  toggle) if conky_running; then stop; else start; fi ;;
  status)
    if conky_running; then
      jq -nc --arg t "$eye_on"  '{text:$t, tooltip:"Conky widget: ON (click to hide)", class:"active"}'
    else
      jq -nc --arg t "$eye_off" '{text:$t, tooltip:"Conky widget: OFF (click to show)", class:"inactive"}'
    fi
    ;;
  *) echo "Usage: $(basename "$0") {status|toggle|start|stop}" >&2; exit 2 ;;
esac
