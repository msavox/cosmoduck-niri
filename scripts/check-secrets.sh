#!/usr/bin/env bash
# check-secrets.sh — fail if anything that looks personal/secret is about to be
# committed. Run from anywhere; scans the whole repo (tracked text files), minus
# the binary .deb. Run this before every push.
#
#   ./scripts/check-secrets.sh
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

# exclude the binary package and the themes (lots of generated CSS, no secrets)
EXCLUDES=(--binary-files=without-match
  --exclude-dir=.git --exclude='*.deb'
  --exclude-dir=themes)

fail=0
flag() { echo "  ⚠️  $1"; fail=1; }

scan() { # <label> <regex>
  local label="$1" re="$2" hits
  hits="$(grep -rInE "${EXCLUDES[@]}" "$re" . 2>/dev/null || true)"
  if [ -n "$hits" ]; then
    flag "$label:"
    echo "$hits" | sed 's/^/      /'
  fi
}

echo ">> scanning $REPO for leaked personal data / secrets"

# the author's real home must never appear — configs use the __HOME__ placeholder
scan "real home path (use __HOME__ instead)" '/home/[a-z][a-z0-9_-]+'

# OpenWeatherMap key: 32 hex chars assigned to api_key= (placeholder is allowed)
hits="$(grep -rInE "${EXCLUDES[@]}" 'api_key=[0-9a-f]{32}' . 2>/dev/null || true)"
[ -n "$hits" ] && { flag "live OpenWeatherMap api_key:"; echo "$hits" | sed 's/^/      /'; }

# generic secret shapes
scan "private key block"        'BEGIN (RSA|OPENSSH|EC|DSA|PGP) PRIVATE KEY'
scan "AWS access key id"        'AKIA[0-9A-Z]{16}'
scan "bearer / generic token"   '(token|secret|passwd|password)[[:space:]]*[=:][[:space:]]*[A-Za-z0-9/_+-]{16,}'
scan "bitbucket/app password"   'bitbucket.*[A-Za-z0-9]{20,}'
scan "ssh private path leak"    'id_(rsa|ed25519)([^.]|$)'

echo
if [ "$fail" -eq 0 ]; then
  echo "✅ clean — nothing suspicious found."
else
  echo "❌ review the lines above before committing."
  exit 1
fi
