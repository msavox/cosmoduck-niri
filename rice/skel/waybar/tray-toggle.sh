#!/usr/bin/env bash
# Tray toggle: kill/spawn ONLY the secondary bar config-tray.jsonc.
# The main bar is never touched.
# State in ~/.config/waybar/.tray-state ("open" or "collapsed").
set -euo pipefail
state_file="$HOME/.config/waybar/.tray-state"
tray_config="$HOME/.config/waybar/config-tray.jsonc"
tray_style="$HOME/.config/waybar/style-tray.css"
state=$(cat "$state_file" 2>/dev/null || echo "open")

# Nerd Font glyphs: U+F053 chevron-left, U+F054 chevron-right
CHEV_LEFT=$(printf '\xef\x81\x93')
CHEV_RIGHT=$(printf '\xef\x81\x94')

kill_tray_bar() {
  # set -e + pipe fail tolerant: pgrep returns 1 if no match
  local pids
  pids=$(pgrep -af "config-tray\.jsonc" 2>/dev/null | grep -v 'pgrep\|grep' | awk '{print $1}' || true)
  [[ -n "$pids" ]] && kill $pids 2>/dev/null || true
  return 0
}

start_tray_bar() {
  kill_tray_bar
  sleep 0.2
  setsid sh -c "waybar -c $tray_config -s $tray_style" >/tmp/waybar-tray.log 2>&1 < /dev/null &
  disown 2>/dev/null || true
  # nm-applet and blueman-applet removed: wifi+bluetooth handled by the GNOME stack
  # via waybar's network/bluetooth modules (click -> gnome-control-center).
}

case "${1:-}" in
  toggle)
    if [[ "$state" == "open" ]]; then
      kill_tray_bar
      echo "collapsed" > "$state_file"
    else
      start_tray_bar
      echo "open" > "$state_file"
    fi
    pkill -SIGRTMIN+1 -x waybar 2>/dev/null || true
    ;;
  start-if-open)
    # callable from niri spawn-at-startup to restore the tray at login
    [[ "$state" == "open" ]] && start_tray_bar
    ;;
  *)
    if [[ "$state" == "collapsed" ]]; then
      printf '{"text":"%s","tooltip":"Show tray","class":"collapsed"}\n' "$CHEV_LEFT"
    else
      printf '{"text":"%s","tooltip":"Hide tray","class":"open"}\n' "$CHEV_RIGHT"
    fi
    ;;
esac
