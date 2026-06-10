#!/usr/bin/env bash
# show-desktop.sh — toggle "Show Desktop" on niri.
#
# niri has no window minimize and no scratchpad, but it keeps an empty workspace
# at the end of every output, and the Cosmoduck desktop surface (desktop.py) is a
# layer-shell visible on ALL workspaces. So "Show Desktop" = focus that empty
# workspace to reveal the desktop, and toggling again returns to where you were.
# niri animates the workspace switch natively (animations { workspace-switch }).
#
# Stateful + stale-guarded: we remember the *stable* id of the workspace we left
# (its index drifts as workspaces come and go) and re-resolve it on the way back.
set -uo pipefail

STATE="$HOME/.cache/cosmoduck/show-desktop.state"
mkdir -p "$(dirname "$STATE")"

WS_JSON="$(niri msg --json workspaces 2>/dev/null)" || exit 0

# Focused workspace id + whether it is empty, and the trailing empty workspace
# (idx + id) on the focused output. Printed as: FOC_ID|FOC_EMPTY|TGT_IDX|TGT_ID
read -r FOC_ID FOC_EMPTY TGT_IDX TGT_ID < <(python3 - "$WS_JSON" <<'PY'
import json, sys
ws = json.loads(sys.argv[1])
foc = next((w for w in ws if w.get("is_focused")), None)
if not foc:
    print(" 1  ")
    sys.exit()
out = foc.get("output")
empty = sorted((w for w in ws if w.get("output") == out
                and w.get("active_window_id") is None),
               key=lambda w: w.get("idx", 0))
tgt = empty[-1] if empty else None
print(foc.get("id"),
      1 if foc.get("active_window_id") is None else 0,
      tgt.get("idx") if tgt else "",
      tgt.get("id") if tgt else "")
PY
)

idx_of_id() {  # current index of a stable workspace id, "" if it is gone
  python3 - "$WS_JSON" "$1" <<'PY'
import json, sys
ws = json.loads(sys.argv[1])
try:
    wid = int(sys.argv[2])
except (ValueError, IndexError):
    sys.exit()
print(next((w["idx"] for w in ws if w.get("id") == wid), ""))
PY
}

if [[ -f "$STATE" ]]; then
  SAVED_ID="$(cat "$STATE")"
  SAVED_IDX="$(idx_of_id "$SAVED_ID")"
  # RETURN only if we are still parked on the empty desktop and home still exists.
  if [[ "$FOC_EMPTY" == "1" && -n "$SAVED_IDX" ]]; then
    niri msg action focus-workspace "$SAVED_IDX"
    rm -f "$STATE"
    exit 0
  fi
  rm -f "$STATE"   # stale (moved away / filled the empty ws) → fall through to SHOW
fi

# SHOW: nothing to hide if already on an empty workspace.
[[ "$FOC_EMPTY" == "1" ]] && exit 0
if [[ -n "$TGT_IDX" ]]; then
  echo "$FOC_ID" > "$STATE"
  niri msg action focus-workspace "$TGT_IDX"
fi
