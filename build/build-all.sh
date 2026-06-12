#!/usr/bin/env bash
# build-all.sh — build & install the whole stack from source, in order.
# Run build/00-deps.sh first (once) to get the toolchain and -dev packages.
#
#   ./build/00-deps.sh        # build dependencies (uses sudo)
#   ./build/build-all.sh      # everything else
#
# You can also run any single step on its own, e.g. ./build/01-libwayland.sh.
# Override WORKDIR or PREFIX via env if you don't want the defaults
# (~/.cache/cosmoduck-niri-build and /usr/local).
. "$(dirname "$0")/lib/common.sh"

STEPS=(
  01-libwayland.sh
  02-libdisplay-info.sh
  03-xwayland.sh
  04-xwayland-satellite.sh
  05-swaync.sh
  06-nwg-dock.sh
  07-swaylock.sh
  07b-swaylock-effects.sh
  08-niri.sh
  09-cliphist.sh
  10-bluez.sh
)

for s in "${STEPS[@]}"; do
  log "=== $s ==="
  bash "$HERE/$s"
done

log "all components built and installed into $PREFIX"
log "next: install the rice with  ../rice/setup.sh  (as your normal user)"
