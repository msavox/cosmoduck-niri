#!/usr/bin/env bash
# 04-xwayland-satellite.sh — rootless Xwayland integration for niri.
# Built with cargo; installed into $PREFIX/bin.
. "$(dirname "$0")/lib/common.sh"
need cargo

SRC="$WORKDIR/xwayland-satellite"
fetch_git "$XWAYLAND_SATELLITE_REPO" "$XWAYLAND_SATELLITE_REF" "$SRC"

log "cargo build --release"
( cd "$SRC" && cargo build --release )

log "install -> $PREFIX/bin"
$SUDO install -m755 "$SRC/target/release/xwayland-satellite" "$PREFIX/bin/xwayland-satellite"
log "done"
