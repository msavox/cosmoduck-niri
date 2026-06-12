#!/usr/bin/env bash
# 00-deps.sh — install the build dependencies on Ubuntu 22.04 (jammy).
#
# Best-effort: this is the set used to backport the stack. A fresh machine may
# still surface a missing -dev package — meson/cargo will name it, just apt it.
. "$(dirname "$0")/lib/common.sh"

log "apt build dependencies (jammy)"
$SUDO apt-get update
$SUDO apt-get install -y \
  build-essential meson ninja-build pkg-config git curl wget ca-certificates \
  cmake clang \
  libffi-dev libexpat1-dev libxml2-dev \
  hwdata \
  libwayland-dev wayland-protocols libwayland-egl-backend-dev \
  libxkbcommon-dev libxkbcommon-x11-dev \
  libudev-dev libinput-dev libseat-dev libgbm-dev libdrm-dev \
  libegl1-mesa-dev libgles2-mesa-dev libgl1-mesa-dev libgbm1 \
  libpixman-1-dev libcairo2-dev libpango1.0-dev libgdk-pixbuf2.0-dev \
  libpam0g-dev scdoc \
  libxfont2-dev libxkbfile-dev libxshmfence-dev libxcvt-dev libtirpc-dev \
  nettle-dev libpciaccess-dev x11proto-dev xtrans-dev \
  libxcb1-dev libxcb-composite0-dev libxcb-res0-dev libxcb-xfixes0-dev \
  libxcb-cursor-dev libxcb-render-util0-dev libxcb-shape0-dev \
  valac libgtk-3-dev libgtk-layer-shell-dev libgirepository1.0-dev \
  libhandy-1-dev libdbusmenu-gtk3-dev \
  golang-go \
  libtool libdbus-1-dev libglib2.0-dev libreadline-dev \
  || die "apt install failed — see the package name above"

log "rust toolchain"
if ! command -v cargo >/dev/null 2>&1; then
  log "cargo not found — installing rustup (niri needs a recent Rust, newer than jammy's)"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  # shellcheck disable=SC1091
  . "$HOME/.cargo/env"
fi
cargo --version || die "cargo still unavailable; install rustup manually"

log "dependencies done"
