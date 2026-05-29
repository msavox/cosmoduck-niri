#!/usr/bin/env bash
# Applies the wallpaper set in GNOME (org.gnome.desktop.background.picture-uri)
# using swaybg as the backend. Source of truth: gnome-control-center Background /
# Nautilus "Set as Wallpaper". When the color-scheme is prefer-dark it reads picture-uri-dark.
set -u

apply() {
  # Read from dconf directly: gsettings may hit the keyfile backend
  # (~/.config/glib-2.0/settings/keyfile) which can shadow the live dconf value.
  local key=picture-uri
  if [[ "$(dconf read /org/gnome/desktop/interface/color-scheme 2>/dev/null)" == "'prefer-dark'" ]]; then
    key=picture-uri-dark
  fi
  local uri
  uri="$(dconf read "/org/gnome/desktop/background/$key" 2>/dev/null | sed -E "s/^'(.*)'$/\1/")"
  [[ -z "$uri" || "$uri" == "none" ]] && return
  local path="${uri#file://}"
  # percent-decode (Nautilus saves URIs with %20 etc.)
  path="$(printf '%b' "${path//%/\\x}")"
  [[ -f "$path" ]] || return
  setsid swaybg -i "$path" -m fill -c "#000000" >/dev/null 2>&1 &
  disown
  sleep 0.4
  pgrep -x swaybg | head -n -1 | xargs -r kill 2>/dev/null || true
}

apply

dconf watch /org/gnome/desktop/background/ 2>/dev/null | while read -r line; do
  case "$line" in
    */picture-uri*) apply ;;
  esac
done &

dconf watch /org/gnome/desktop/interface/ 2>/dev/null | while read -r line; do
  case "$line" in
    */color-scheme*) apply ;;
  esac
done &

wait
