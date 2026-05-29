#!/usr/bin/env bash
# Launches swaylock showing the CURRENT wallpaper blurred.
# Wallpaper source: the command line of the running swaybg (-i ...),
# with a fallback on dconf (org.gnome.desktop.background). The blurred version
# is cached and regenerated only if the wallpaper or its mtime change.
set -u

CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/swaylock"
mkdir -p "$CACHE_DIR"

# --- 1. find the live wallpaper ---
wall=""
# swaybg -i <path> -m fill ...  -> extract the argument after -i
if line="$(pgrep -af '[s]waybg' | head -1)"; then
  wall="$(sed -nE 's/.* -i[= ]+([^ ]+).*/\1/p' <<<"$line")"
fi
# fallback: dconf (respects prefer-dark like gnome-wallpaper-sync.sh)
if [[ -z "$wall" || ! -f "$wall" ]]; then
  key=picture-uri
  [[ "$(dconf read /org/gnome/desktop/interface/color-scheme 2>/dev/null)" == "'prefer-dark'" ]] && key=picture-uri-dark
  uri="$(dconf read "/org/gnome/desktop/background/$key" 2>/dev/null | sed -E "s/^'(.*)'\$/\1/")"
  wall="${uri#file://}"
  wall="$(printf '%b' "${wall//%/\\x}")"
fi

# --- 2. generate (or reuse) the blurred version ---
blurred=""
if [[ -f "$wall" ]]; then
  # cache key: path + mtime, so it changes with the wallpaper
  mtime="$(stat -c %Y "$wall" 2>/dev/null || echo 0)"
  hash="$(printf '%s|%s' "$wall" "$mtime" | cksum | cut -d' ' -f1)"
  blurred="$CACHE_DIR/blur-$hash.png"
  if [[ ! -f "$blurred" ]]; then
    # fast blur: downscale -> blur -> upscale, then darken a bit (-colorize)
    if convert "$wall" -scale 10% -blur 0x2.5 -resize 1000% \
               -fill black -colorize 22% "$blurred" 2>/dev/null; then
      # clean up old caches (keep only the last 5)
      ls -1t "$CACHE_DIR"/blur-*.png 2>/dev/null | tail -n +6 | xargs -r rm -f
    else
      blurred=""
    fi
  fi
fi

# --- 3. launch swaylock ---
if [[ -n "$blurred" && -f "$blurred" ]]; then
  exec swaylock -f -i "$blurred" --scaling fill
else
  # fallback: no image -> plain color
  exec swaylock -f -c 1e1e2e
fi
