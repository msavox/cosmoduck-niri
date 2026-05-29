#!/usr/bin/env bash
# 05-swaync.sh — SwayNotificationCenter ($SWAYNC_REF, GTK3 build, reports 0.9.0).
# Installs swaync + swaync-client into $PREFIX.
# NOTE: this build is GTK3 — its stylesheet must NOT use the `overflow` CSS
# property (GTK3 chokes on it and silently drops the whole sheet); the shipped
# rice/skel/swaync/style.css already accounts for that.
. "$(dirname "$0")/lib/common.sh"
need meson; need ninja; need valac

SRC="$WORKDIR/SwayNotificationCenter"
fetch_git "$SWAYNC_REPO" "$SWAYNC_REF" "$SRC"

log "configure + build"
rm -rf "$SRC/build"
meson setup "$SRC/build" "$SRC" --prefix="$PREFIX" --buildtype=release
ninja -C "$SRC/build"

log "install -> $PREFIX"
$SUDO ninja -C "$SRC/build" install
log "done"
