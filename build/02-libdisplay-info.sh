#!/usr/bin/env bash
# 02-libdisplay-info.sh — build libdisplay-info $LIBDISPLAY_INFO_REF and install
# into $PREFIX. niri links it at runtime and jammy doesn't package it. This also
# produces di-edid-decode, which we ship for EDID debugging.
. "$(dirname "$0")/lib/common.sh"
need meson; need ninja

SRC="$WORKDIR/libdisplay-info"
fetch_git "$LIBDISPLAY_INFO_REPO" "$LIBDISPLAY_INFO_REF" "$SRC"

log "configure + build"
rm -rf "$SRC/build"
meson setup "$SRC/build" "$SRC" --prefix="$PREFIX" --buildtype=release
ninja -C "$SRC/build"

log "install -> $PREFIX"
$SUDO ninja -C "$SRC/build" install
$SUDO ldconfig
log "done"
