#!/usr/bin/env bash
# capture.sh — grab the README screenshots, named to match the gallery in the
# top-level README.md. Run it from inside a niri session.
#
# Needs grim (+ slurp for region shots):   sudo apt install grim slurp
#
# It walks you through each shot: stage the scene (open the apps / trigger the
# overlay), then press Enter and it captures. 'f' = full output, 's' = drag a
# region, 'x' = skip. Multi-monitor tip: stage everything on one screen and grab
# that output with 'f' (grim captures the focused output by default; pass
# CAP_OUTPUT=DP-1 to force one).
#
# Review every PNG for personal data (weather city, window titles, tray icons,
# calendar events) BEFORE you commit them.
set -euo pipefail
cd "$(dirname "$0")"

command -v grim >/dev/null || { echo "grim not found -> sudo apt install grim slurp"; exit 1; }
OUT_FLAG=(); [ -n "${CAP_OUTPUT:-}" ] && OUT_FLAG=(-o "$CAP_OUTPUT")

shot() { # <file> <default f|s> <instructions>
  local file="$1" def="$2"; shift 2
  echo
  echo "── $file ───────────────────────────────────────────"
  echo "   $*"
  read -rp "   stage it, then Enter to capture [f=full s=region x=skip] (default $def) > " ans
  ans="${ans:-$def}"
  case "$ans" in
    x) echo "   skipped"; return ;;
    s) command -v slurp >/dev/null || { echo "   slurp missing"; return; }
       grim -g "$(slurp)" "$file" ;;
    *) grim "${OUT_FLAG[@]}" "$file" ;;
  esac
  echo "   saved $file  — review it for personal data"
}

echo "Capturing into $(pwd)${CAP_OUTPUT:+  (output: $CAP_OUTPUT)}"
shot 01-desktop.png       f "HERO: wallpaper + conky + top bar + dock + two tiled windows. Nothing private on screen."
shot 02-tiling.png        f "Scrollable tiling: 3 columns open (niri's signature). Mid-scroll looks great."
shot 03-dock.png          s "Dock close-up: pinned apps + running indicators + an open app + trash. Drag a region over the dock."
shot 04-bar.png           s "Top bar close-up: workspaces, window title, tray, the custom modules (coffee = lid keep-awake, eye = conky, volume). Region over the bar."
shot 05-cheatsheet.png    f "Press F1 to bring up the keyboard cheatsheet (3 columns), then capture."
shot 06-calendar.png      s "Open the calendar popup (click the clock) — or the volume slider. Region around the popup. Watch for private events."
shot 07-swaync.png        f "Open the notification center (and/or trigger a notification) so swaync is visible."
shot 08-conky.png         s "Conky 'Cosmoduck' widget close-up. Region over it. Check the weather city isn't private."
shot 09-theme-buttons.png s "A GTK window (Files / Settings) showing the cosmoduck theme + blue window buttons. Region over the window."
shot 10-swaylock.png      f "Lock screen. Tricky to self-capture: easiest is 'sleep 4; grim -o <output> 10-swaylock.png' then lock; or skip and shoot later."
shot 11-light.png         f "Switch to the light theme (cosmoduck-Light) and grab the desktop again."

echo
echo "Done. Review every PNG, then they render in README.md."
