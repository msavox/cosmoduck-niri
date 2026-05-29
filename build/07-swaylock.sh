#!/usr/bin/env bash
# 07-swaylock.sh — build swaylock from $SWAYLOCK_REF (reports v1.8.5).
# jammy's swaylock 1.5 is incompatible with niri (it relies on the deprecated
# input-inhibitor protocol), so we build a current swaylock into $PREFIX.
# The rice wraps it as swaylock-blur.sh (locks over a blurred wallpaper).
. "$(dirname "$0")/lib/common.sh"
need meson; need ninja

SRC="$WORKDIR/swaylock"
fetch_git "$SWAYLOCK_REPO" "$SWAYLOCK_REF" "$SRC"

log "configure + build"
rm -rf "$SRC/build"
meson setup "$SRC/build" "$SRC" --prefix="$PREFIX" --buildtype=release
ninja -C "$SRC/build"

log "install -> $PREFIX (PAM config under $PREFIX/etc/pam.d)"
$SUDO ninja -C "$SRC/build" install
log "done"
