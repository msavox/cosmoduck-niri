#!/usr/bin/env bash
# 10-bluez.sh — build bluez 5.86 (jammy ships 5.64, which has a fatal bug:
# with Experimental=true — needed for battery reporting via the D-Bus Battery1
# interface, used by the bar's bt-battery module — the adv-monitor manager
# takes the MSFT-offload path and passive scanning is never (re)enabled. Net
# effect: bonded mice/headphones NEVER auto-reconnect, you have to connect by
# hand after every power cycle. Verified with btmon: the kernel gets the
# device in the LE accept list but `LE Set Extended Scan Enable` is never
# issued. bluez 5.86 fixes the coexistence.)
#
# Installs bluetoothd under $PREFIX/libexec/bluetooth and the clients
# (bluetoothctl, btmon, btmgmt, ...) under $PREFIX/bin, then points the system
# bluetooth.service at the new daemon via a systemd drop-in. The jammy bluez
# package stays installed: obexd, udev rules and the D-Bus policy still come
# from it (--disable-datafiles keeps `make install` away from /etc).
. "$(dirname "$0")/lib/common.sh"
need autoconf; need automake; need libtoolize

SRC="$WORKDIR/bluez"
fetch_git "$BLUEZ_REPO" "$BLUEZ_REF" "$SRC"

cd "$SRC"
log "bootstrap + configure"
./bootstrap
./configure --prefix="$PREFIX" --sysconfdir=/etc --localstatedir=/var \
  --enable-experimental --disable-mesh --disable-obex \
  --disable-manpages --disable-datafiles

log "build"
make -j"$(nproc)"

log "install"
$SUDO make install
$SUDO ldconfig

log "point bluetooth.service at the new daemon (systemd drop-in)"
$SUDO mkdir -p /etc/systemd/system/bluetooth.service.d
printf '[Service]\nExecStart=\nExecStart=%s/libexec/bluetooth/bluetoothd\n' "$PREFIX" \
  | $SUDO tee /etc/systemd/system/bluetooth.service.d/usr-local.conf >/dev/null

log "enable Experimental in /etc/bluetooth/main.conf (battery reporting)"
if grep -q '^Experimental' /etc/bluetooth/main.conf 2>/dev/null; then
  $SUDO sed -i 's/^Experimental.*/Experimental = true/' /etc/bluetooth/main.conf
elif grep -q '^\[General\]' /etc/bluetooth/main.conf 2>/dev/null; then
  $SUDO sed -i '/^\[General\]/a Experimental = true' /etc/bluetooth/main.conf
else
  printf '[General]\nExperimental = true\n' | $SUDO tee -a /etc/bluetooth/main.conf >/dev/null
fi

log "restart bluetooth"
$SUDO systemctl daemon-reload
$SUDO systemctl restart bluetooth

log "done — bluetoothd $("$PREFIX/libexec/bluetooth/bluetoothd" --version) active"
log "rollback: sudo rm /etc/systemd/system/bluetooth.service.d/usr-local.conf && sudo systemctl daemon-reload && sudo systemctl restart bluetooth"
