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

# --- 3. launch swaylock-effects ---
# Binary: swaylock-effects (jirutka fork, ext-session-lock-v1, built into
# /usr/local/bin). Adds fade-in, grace, and --effect-compose (duck in the
# center) over stock swaylock. Indicator colors = Cosmoduck palette.
SWAYLOCK=swaylock-effects
command -v "$SWAYLOCK" >/dev/null 2>&1 || SWAYLOCK=swaylock   # fall back to stock

# Duck in the center of the ring (the same "cosmofinder" Nautilus icon). Prefer
# the per-user copy installed by cosmoduck-niri-setup; fall back to the shipped
# system copy.
DUCK="$HOME/Pictures/icons/cosmofinder.png"
[[ -f "$DUCK" ]] || DUCK="/usr/share/cosmoduck-niri/cosmofinder.png"

# options supported by both stock swaylock and the fork.
# The circle fill is TRANSPARENT so the duck, composited on the background,
# shows inside the ring. The ring changes color per state.
opts=(
  -f
  --indicator-radius 175 --indicator-thickness 10 --indicator-idle-visible
  --font "Noto Sans" --font-size 26
  --ring-color 3d72abee --ring-ver-color 5dade2ee --ring-clear-color a6e3a1ee --ring-wrong-color f38ba8ee
  --inside-color 00000000 --inside-ver-color 00000000 --inside-wrong-color 00000000 --inside-clear-color 00000000
  --key-hl-color 5dade2 --bs-hl-color f38ba8
  # status text TRANSPARENT: it would sit in the center of the ring, over the duck.
  # Feedback is left to the ring color (ver/wrong/clear).
  --text-color 00000000 --text-ver-color 00000000 --text-wrong-color 00000000 --text-clear-color 00000000
  --text-caps-lock-color 00000000 -L
  --line-uses-inside --separator-color 00000000
)

# options exclusive to the swaylock-effects fork.
# No --clock: the clock would draw in the same center, OVER the duck.
if [[ "$SWAYLOCK" == swaylock-effects ]]; then
  opts+=( --fade-in 0.2 )
  # <pos>;<size>;<gravity>;<path> — screen center, 280x280 (fits in the circle).
  # For the smaller variant: ring 155 + duck 230x230.
  [[ -f "$DUCK" ]] && opts+=( --effect-compose "50%,50%;280x280;center;$DUCK" )
  # Passwordless unlock in the first N seconds after lock. Off for safety:
  # opts+=( --grace 5 --grace-no-mouse )
fi

if [[ -n "$blurred" && -f "$blurred" ]]; then
  exec "$SWAYLOCK" "${opts[@]}" -i "$blurred" --scaling fill
else
  # fallback: no image -> plain color
  exec "$SWAYLOCK" "${opts[@]}" -c 1e1e2e
fi
