#!/usr/bin/env bash
# build-deb.sh — assemble the cosmoduck-niri .deb from this repo.
#
# Reproducible from a clone: binaries/libraries come from $PREFIX (install them
# first with ../build/build-all.sh), all per-user config comes from ../rice
# (already de-personalized — no $HOME scraping, no secrets to sanitize here),
# themes from ../rice/themes. Only the third-party Bibata cursor and the
# CaskaydiaCove Nerd Font are still pulled from the system (see notes below).
#
# Re-run any time: it rebuilds build/pkgroot from scratch.
set -euo pipefail

# ── paths ────────────────────────────────────────────────────────────
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
STATIC="$HERE/static"
RICE="$REPO/rice"
ROOT="$HERE/build/pkgroot"
PREFIX="${PREFIX:-/usr/local}"
PKG="cosmoduck-niri"
VER="1.5.0"
ARCH="amd64"

echo ">> reset staging"
rm -rf "$HERE/build"
mkdir -p "$ROOT"

# Authored static tree: DEBIAN/, usr/bin/cosmoduck-niri-setup, the generic
# dock preset, .desktop, README placeholders.
cp -a "$STATIC/." "$ROOT/"

# ── 1. compiled binaries -> /usr/local (stripped copies) ─────────────
echo ">> binaries (from $PREFIX, built by ../build/build-all.sh)"
install -d "$ROOT/usr/local/bin" "$ROOT/usr/local/lib/x86_64-linux-gnu"
BINS="niri niri-session Xwayland swaylock swaylock-effects swaync swaync-client di-edid-decode xwayland-satellite nwg-dock cliphist"
for b in $BINS; do
  [ -f "$PREFIX/bin/$b" ] || { echo "MISSING: $PREFIX/bin/$b — run ../build/build-all.sh first" >&2; exit 1; }
  install -m755 "$PREFIX/bin/$b" "$ROOT/usr/local/bin/$b"
done
# strip to shrink (~158MB -> ~40MB); shell scripts (niri-session) are left alone
for f in "$ROOT/usr/local/bin/"*; do strip --strip-unneeded "$f" 2>/dev/null || true; done

# libdisplay-info (niri runtime dep, not packaged on jammy)
cp -a "$PREFIX/lib/x86_64-linux-gnu/libdisplay-info.so"* "$ROOT/usr/local/lib/x86_64-linux-gnu/"
if [ -d "$PREFIX/lib/x86_64-linux-gnu/pkgconfig" ]; then
  install -d "$ROOT/usr/local/lib/x86_64-linux-gnu/pkgconfig"
  cp -a "$PREFIX/lib/x86_64-linux-gnu/pkgconfig/." "$ROOT/usr/local/lib/x86_64-linux-gnu/pkgconfig/"
fi

# libwayland-client 1.23.1: fixes the Firefox scroll crash under niri. Postinst's
# ld.so.conf.d entry makes it shadow jammy's 1.20 (ABI-compatible, soname .0).
cp -a "$PREFIX/lib/x86_64-linux-gnu/libwayland-client.so"* "$ROOT/usr/local/lib/x86_64-linux-gnu/"

# ── 2. session / systemd / portal files ──────────────────────────────
echo ">> session files"
install -d "$ROOT/usr/share/wayland-sessions" "$ROOT/usr/lib/systemd/user" "$ROOT/usr/share/xdg-desktop-portal"
install -m644 /usr/share/wayland-sessions/niri.desktop "$ROOT/usr/share/wayland-sessions/niri.desktop"
install -m644 /usr/lib/systemd/user/niri.service          "$ROOT/usr/lib/systemd/user/niri.service"
install -m644 /usr/lib/systemd/user/niri-shutdown.target  "$ROOT/usr/lib/systemd/user/niri-shutdown.target"
install -m644 /usr/share/xdg-desktop-portal/niri-portals.conf "$ROOT/usr/share/xdg-desktop-portal/niri-portals.conf"

# ── 3. themes (system-wide, from the repo) ───────────────────────────
echo ">> cosmoduck themes -> /usr/share/themes"
install -d "$ROOT/usr/share/themes"
cp -a "$RICE/themes/"cosmoduck-* "$ROOT/usr/share/themes/"

# ── 4. cursor (Bibata) — third-party, pulled from the system ─────────
echo ">> Bibata cursor"
if [ -d /usr/share/icons/Bibata-Modern-Classic ]; then
  install -d "$ROOT/usr/share/icons"
  cp -a /usr/share/icons/Bibata-Modern-Classic "$ROOT/usr/share/icons/"
else
  echo "   note: Bibata-Modern-Classic not installed system-wide — skipping (see README)"
fi

# ── 5. Nerd Font — third-party, pulled from the system ───────────────
echo ">> CaskaydiaCove Nerd Font (used weights)"
install -d "$ROOT/usr/share/fonts/truetype/caskaydia-nerd"
for f in CaskaydiaCoveNerdFont-Regular CaskaydiaCoveNerdFont-Bold \
         CaskaydiaCoveNerdFontMono-Regular CaskaydiaCoveNerdFontMono-Bold; do
  if [ -f "$HOME/.fonts/$f.ttf" ]; then
    install -m644 "$HOME/.fonts/$f.ttf" "$ROOT/usr/share/fonts/truetype/caskaydia-nerd/$f.ttf"
  else
    echo "   note: $f.ttf not found in ~/.fonts — skipping (see README)"
  fi
done

# ── 6. per-user skel (straight from the repo, already de-personalized) ─
echo ">> skel (from ../rice/skel)"
SKEL="$ROOT/usr/share/$PKG/skel"
rm -rf "$SKEL"
install -d "$SKEL"
cp -a "$RICE/skel/." "$SKEL/"
find "$SKEL" -type d -name '__pycache__' -prune -exec rm -rf {} +

# ── 7. permissions ───────────────────────────────────────────────────
setfacl -bR "$ROOT" 2>/dev/null || true
find "$ROOT" -type d -exec chmod 0755 {} +
find "$ROOT" -type f -exec chmod 0644 {} +
find "$ROOT/usr/local/bin" -type f -exec chmod 0755 {} +
chmod 0755 "$ROOT/usr/bin/cosmoduck-niri-setup"
# Plymouth kernel-log feeders (systemd-phase binary + initramfs hook) are executable
[ -f "$ROOT/usr/bin/cosmoduck-bootlog" ] && chmod 0755 "$ROOT/usr/bin/cosmoduck-bootlog"
[ -f "$ROOT/etc/initramfs-tools/scripts/init-premount/cosmoduck-bootlog" ] && \
  chmod 0755 "$ROOT/etc/initramfs-tools/scripts/init-premount/cosmoduck-bootlog"
chmod 0755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/prerm" "$ROOT/DEBIAN/postrm"
find "$SKEL" -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod 0755 {} +
chmod 0755 "$SKEL/bin/lid-keep-awake"
find "$SKEL/conky/Regulus-MOD-Cosmoduck/scripts" -type f -exec chmod 0755 {} + 2>/dev/null || true

# ── 8. control: fill Installed-Size ──────────────────────────────────
SIZE_KB=$(du -sk "$ROOT" | cut -f1)
sed -i "s/^Installed-Size:.*/Installed-Size: $SIZE_KB/" "$ROOT/DEBIAN/control"

# ── 9. build ─────────────────────────────────────────────────────────
echo ">> dpkg-deb build"
mkdir -p "$REPO/dist"
OUT="$REPO/dist/${PKG}_${VER}_${ARCH}.deb"
dpkg-deb --root-owner-group --build "$ROOT" "$OUT"
echo ">> built: $OUT"
ls -lh "$OUT"
