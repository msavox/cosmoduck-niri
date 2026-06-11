#!/usr/bin/env bash
# 09-cliphist.sh — wayland clipboard history ($CLIPHIST_REF). Go build -> $PREFIX/bin.
# The rice collects history with `wl-paste --watch cliphist store` (spawned by
# niri at startup) and shows it with clip-menu.py on Mod+Ctrl+V.
. "$(dirname "$0")/lib/common.sh"
need go

SRC="$WORKDIR/cliphist"
fetch_git "$CLIPHIST_REPO" "$CLIPHIST_REF" "$SRC"

log "go build"
( cd "$SRC" && go build -o cliphist . )

log "install -> $PREFIX/bin"
$SUDO install -m755 "$SRC/cliphist" "$PREFIX/bin/cliphist"
log "done"
