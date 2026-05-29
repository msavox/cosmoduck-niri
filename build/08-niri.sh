#!/usr/bin/env bash
# 08-niri.sh — build the niri compositor ($NIRI_REF) with the jammy patches and
# install it (+ session/systemd/portal files) into the system.
#
# Patches applied (build/patches/):
#   niri-0001-dwtp-libinput-jammy.patch
#       jammy's libinput (< 1.27) has no libinput_device_config_dwtp_set_enabled
#       symbol; the call is patched out so niri links and runs.
#   niri-0002-hotkey-overlay-rounded-corners.patch
#       cosmetic: the hotkey overlay is drawn as a rounded window.
. "$(dirname "$0")/lib/common.sh"
need cargo

PATCHES="$HERE/patches"
SRC="$WORKDIR/niri"
fetch_git "$NIRI_REPO" "$NIRI_REF" "$SRC"

log "apply jammy patches"
for p in "$PATCHES"/niri-*.patch; do
  if git -C "$SRC" apply --check "$p" 2>/dev/null; then
    git -C "$SRC" apply "$p"
    log "  applied $(basename "$p")"
  elif git -C "$SRC" apply --reverse --check "$p" 2>/dev/null; then
    log "  already applied: $(basename "$p")"
  else
    die "patch does not apply (upstream moved?): $(basename "$p")"
  fi
done

log "cargo build --release (this takes a while)"
( cd "$SRC" && cargo build --release )

log "install niri + session files"
$SUDO install -Dm755 "$SRC/target/release/niri"            "$PREFIX/bin/niri"
$SUDO install -Dm755 "$SRC/resources/niri-session"         "$PREFIX/bin/niri-session"
$SUDO install -Dm644 "$SRC/resources/niri.desktop"         /usr/share/wayland-sessions/niri.desktop
$SUDO install -Dm644 "$SRC/resources/niri.service"         /usr/lib/systemd/user/niri.service
$SUDO install -Dm644 "$SRC/resources/niri-shutdown.target" /usr/lib/systemd/user/niri-shutdown.target
$SUDO install -Dm644 "$SRC/resources/niri-portals.conf"    /usr/share/xdg-desktop-portal/niri-portals.conf
log "done — log out and pick the 'niri' session"
