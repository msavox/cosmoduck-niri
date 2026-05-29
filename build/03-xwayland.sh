#!/usr/bin/env bash
# 03-xwayland.sh — build a standalone Xwayland ($XWAYLAND_REF) from xserver.
#
# THE INVOLVED ONE. jammy's Xwayland is too old for the protocol versions niri
# speaks, so we build Xwayland from the xorg/xserver tree against the newer
# wayland from step 01. We stage wayland + wayland-protocols into a private
# prefix and point pkg-config at it, so only Xwayland sees the newer wayland —
# the system isn't touched beyond installing the Xwayland binary into $PREFIX.
#
# This is the least "push-button" script; if a -dev package is missing, meson
# will name it — apt it and re-run. The .deb ships a prebuilt Xwayland, so this
# is only for people who want to rebuild it themselves.
. "$(dirname "$0")/lib/common.sh"
need meson; need ninja

STAGE="$WORKDIR/stage"            # private prefix for the build-time wayland
export PKG_CONFIG_PATH="$STAGE/lib/x86_64-linux-gnu/pkgconfig:$STAGE/share/pkgconfig:${PKG_CONFIG_PATH:-}"

# 1. stage a full wayland (client+server+scanner) into $STAGE
WSRC="$WORKDIR/wayland"
fetch_git "$WAYLAND_REPO" "$WAYLAND_REF" "$WSRC"
log "stage wayland -> $STAGE"
rm -rf "$WSRC/build-stage"
meson setup "$WSRC/build-stage" "$WSRC" --prefix="$STAGE" \
  --libdir=lib/x86_64-linux-gnu --buildtype=release \
  -Ddocumentation=false -Dtests=false -Ddtd_validation=false
ninja -C "$WSRC/build-stage" install

# 2. stage wayland-protocols into $STAGE
PSRC="$WORKDIR/wayland-protocols"
fetch_git "https://gitlab.freedesktop.org/wayland/wayland-protocols.git" "1.32" "$PSRC"
log "stage wayland-protocols -> $STAGE"
rm -rf "$PSRC/build"
meson setup "$PSRC/build" "$PSRC" --prefix="$STAGE" \
  --libdir=lib/x86_64-linux-gnu --buildtype=release -Dtests=false
ninja -C "$PSRC/build" install

# 3. build Xwayland only, against the staged wayland
XSRC="$WORKDIR/xserver"
fetch_git "$XWAYLAND_REPO" "$XWAYLAND_REF" "$XSRC"
log "configure Xwayland (all other DDXes off)"
rm -rf "$XSRC/build"
meson setup "$XSRC/build" "$XSRC" \
  --prefix="$PREFIX" --buildtype=release \
  -Dxwayland=true -Dxorg=false -Dxvfb=false -Dxnest=false \
  -Ddmx=false -Dxephyr=false -Ddocs=false -Ddevel-docs=false \
  -Dwerror=false
ninja -C "$XSRC/build"

log "install Xwayland -> $PREFIX/bin"
$SUDO ninja -C "$XSRC/build" install
"$PREFIX/bin/Xwayland" -version 2>&1 | head -1 || true
log "done"
