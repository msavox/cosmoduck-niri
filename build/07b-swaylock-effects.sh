#!/usr/bin/env bash
# 07b-swaylock-effects.sh — build jirutka's swaylock-effects fork.
# It adds --effect-compose / --fade-in / --clock over stock swaylock and (unlike
# mortie's 1.6 fork) carries ext-session-lock-v1, so it runs under niri. The
# rice's swaylock-blur.sh prefers it and composites the Cosmoduck duck inside
# the lock ring.
#
# Installed as `swaylock-effects` ALONGSIDE the stock swaylock from 07-swaylock.sh
# (we copy the built binary instead of `ninja install`, so the two coexist).
# PAM service name stays "swaylock" (hardcoded upstream); the package's postinst
# makes sure /etc/pam.d/swaylock exists.
. "$(dirname "$0")/lib/common.sh"
need meson; need ninja

SRC="$WORKDIR/swaylock-effects"
fetch_git "$SWAYLOCK_EFFECTS_REPO" "$SWAYLOCK_EFFECTS_REF" "$SRC"

log "configure + build"
rm -rf "$SRC/build"
# gdk-pixbuf is needed for --effect-compose / image loading (see 00-deps.sh).
meson setup "$SRC/build" "$SRC" --prefix="$PREFIX" --buildtype=release \
  -Dpam=enabled -Dman-pages=disabled
ninja -C "$SRC/build"

log "install built binary as swaylock-effects (coexists with stock swaylock)"
$SUDO install -m755 "$SRC/build/swaylock" "$PREFIX/bin/swaylock-effects"
log "done"
