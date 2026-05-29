#!/usr/bin/env bash
# 01-libwayland.sh — build libwayland $WAYLAND_REF and install ONLY the client
# library into $PREFIX/lib. jammy ships 1.20, whose libwayland-client lacks the
# axis_value120 (high-resolution scroll) event handling; under niri that makes
# Firefox abort with "wl_pointer has no event 9". We deliberately install just
# libwayland-client (ABI-compatible, soname .0) and leave the rest of jammy's
# wayland in place.
. "$(dirname "$0")/lib/common.sh"
need meson; need ninja

SRC="$WORKDIR/wayland"
fetch_git "$WAYLAND_REPO" "$WAYLAND_REF" "$SRC"

log "configure (client only, no docs/tests)"
rm -rf "$SRC/build"
meson setup "$SRC/build" "$SRC" \
  --prefix="$PREFIX" --buildtype=release \
  -Ddocumentation=false -Dtests=false -Ddtd_validation=false \
  -Dlibraries=true -Dscanner=false
ninja -C "$SRC/build" src/libwayland-client.so

LIB="$SRC/build/src/libwayland-client.so.0.23.1"
[ -f "$LIB" ] || die "built library not found: $LIB"

log "sanity: the high-res scroll event must be present"
strings "$LIB" | grep -q axis_value120 || die "axis_value120 missing — wrong version built"

DEST="$PREFIX/lib/x86_64-linux-gnu"
log "install -> $DEST"
$SUDO install -d "$DEST"
$SUDO install -m644 "$LIB" "$DEST/"
$SUDO ln -sf libwayland-client.so.0.23.1 "$DEST/libwayland-client.so.0"
$SUDO ldconfig

RESOLVED="$(ldconfig -p | awk '/libwayland-client.so.0 .*x86-64/{print $NF; exit}')"
case "$RESOLVED" in
  "$PREFIX"/*) log "active: $RESOLVED" ;;
  *) die "linker still resolves $RESOLVED (not $PREFIX) — check /etc/ld.so.conf.d" ;;
esac
log "done — fully restart Firefox to pick it up"
