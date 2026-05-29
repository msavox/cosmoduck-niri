#!/usr/bin/env bash
chosen=$(printf "󰍁  Lock\n󰗽  Logout\n󰒲  Suspend\n󰜉  Reboot\n󰐥  Shutdown" \
  | wofi --dmenu --prompt "Power" --insensitive --width 320 --height 280 --hide-scroll)
case "$chosen" in
  *Lock)     swaylock -f -c 1e1e2e ;;
  *Logout)   niri msg action quit ;;
  *Suspend)  systemctl suspend ;;
  *Reboot)   systemctl reboot ;;
  *Shutdown) systemctl poweroff ;;
esac
