# common.sh — shared helpers for the build scripts. Source it, don't run it.
# Each build script does:  . "$(dirname "$0")/lib/common.sh"

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
. "$HERE/versions.env"

log()  { printf '\033[1;34m>>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1 (run build/00-deps.sh)"; }

# sudo wrapper: skip when already root
SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

# fetch_git <repo> <ref> <dest>: clone (or update) and checkout the pinned ref.
fetch_git() {
  local repo="$1" ref="$2" dest="$3"
  mkdir -p "$(dirname "$dest")"
  if [ ! -d "$dest/.git" ]; then
    log "clone $repo -> $dest"
    git clone "$repo" "$dest"
  fi
  log "checkout $ref"
  git -C "$dest" fetch --tags --force origin
  git -C "$dest" checkout -f "$ref"
  git -C "$dest" submodule update --init --recursive 2>/dev/null || true
}

mkdir -p "$WORKDIR"
