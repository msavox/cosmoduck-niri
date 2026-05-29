#!/usr/bin/env bash
# 06-nwg-dock.sh — macOS-style dock ($NWG_DOCK_REF). Go build -> $PREFIX/bin.
# (The Cosmoduck rice drives a waybar-based dock; nwg-dock is shipped as an
# optional alternative the .deb also bundles.)
. "$(dirname "$0")/lib/common.sh"
need go

SRC="$WORKDIR/nwg-dock"
fetch_git "$NWG_DOCK_REPO" "$NWG_DOCK_REF" "$SRC"

log "go build"
( cd "$SRC" && go build -o nwg-dock . )

log "install -> $PREFIX/bin"
$SUDO install -m755 "$SRC/nwg-dock" "$PREFIX/bin/nwg-dock"
log "done"
