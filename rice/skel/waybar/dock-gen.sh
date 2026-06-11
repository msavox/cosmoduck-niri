#!/usr/bin/env bash
# Regenerate dock.jsonc and dock-pinned.css from dock-apps.json,
# then restart the waybar dock.
#
# Generated layout:
#   modules-center = [ <pinned...>, <auto-slot1..N>, <post...> ]
# Entries with "post_taskbar": true go after the auto-pin slots (e.g. settings,
# trash), all others before. Backward-compat fallback: if none has
# post_taskbar, the last entry is treated as post. The auto-slots replace
# wlr/taskbar: dock-autopin.py assigns unpinned running apps to them.
set -euo pipefail

cfg="$HOME/.config/waybar"
apps="$cfg/dock-apps.json"
out_json="$cfg/dock.jsonc"
out_css="$cfg/dock-pinned.css"

[[ -f "$apps" ]] || { echo "missing $apps" >&2; exit 1; }

count=$(jq 'length' "$apps")
(( count > 0 )) || { echo "dock-apps.json empty" >&2; exit 1; }

# Auto-pin slots (dock-autopin.py): SLOTS permanent custom modules between
# the pinned icons and the post-taskbar ones. A vacant slot hides itself
# (dock-status.sh returns empty text); the daemon assigns unpinned running
# apps to slots by rewriting dock-apps-auto.json ONLY — no dock restart, so
# windows never re-layout. Icons come from per-icon CSS classes pre-generated
# below for every installed .desktop app. This replaces wlr/taskbar.
SLOTS=16

# ── notification-count badge SVGs (regenerated if the folder is missing) ──
# Solid dark-blue pill with a white number; values 1..9 and "9+".
badges_dir="$cfg/badges"
if [[ ! -d "$badges_dir" ]]; then
  mkdir -p "$badges_dir"
  _mkbadge() { # <key> <label> <font-size>
    cat > "$badges_dir/badge-$1.svg" <<SVG
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
  <circle cx="8" cy="8" r="7.3" fill="#1e40af" stroke="#0a163f" stroke-width="1"/>
  <text x="8" y="11.5" text-anchor="middle" font-family="sans-serif" font-size="$3" font-weight="bold" fill="#ffffff">$2</text>
</svg>
SVG
  }
  for n in 1 2 3 4 5 6 7 8 9; do _mkbadge "$n" "$n" 10; done
  _mkbadge 9p "9+" 8
fi

ids=()
post_ids=()
pinned_ids=()
# Single jq (TSV) instead of 3 jq per app: id <tab> post_taskbar.
while IFS=$'\t' read -r id post; do
  ids+=("$id")
  if [[ "$post" == "true" ]]; then
    post_ids+=("$id")
  else
    pinned_ids+=("$id")
  fi
done < <(jq -r '.[] | "\(.id)\t\(.post_taskbar // false)"' "$apps")

# Backward-compat: if no post_taskbar, move the last one into post
if (( ${#post_ids[@]} == 0 )); then
  post_ids=("${pinned_ids[-1]}")
  unset 'pinned_ids[-1]'
fi

# ── modules-center array ─────────────────────────────────────────────
slot_ids=()
for ((s=1; s<=SLOTS; s++)); do slot_ids+=("auto-slot${s}"); done

center='['
first=1
for id in "${pinned_ids[@]}" "${slot_ids[@]}"; do
  (( first )) || center+=","
  center+="\"custom/$id\""
  first=0
done
for id in "${post_ids[@]}"; do
  center+=",\"custom/$id\""
done
center+=']'

# ── per-app module blocks (custom/<id>) ──────────────────────────────
# A single jq builds the object with ALL modules (instead of one per app).
modules_json=$(jq -c --argjson slots "$SLOTS" '
  [ (.[].id), ("auto-slot" + (range(1; $slots + 1) | tostring))
    | { ("custom/"+.): {
          "exec": ("__HOME__/.config/waybar/dock-status.sh " + .),
          "interval": 1,
          "return-type": "json",
          "tooltip": true,
          "on-click": ("__HOME__/.config/waybar/dock-click.sh " + .),
          "on-click-right": ("/usr/bin/python3 __HOME__/.config/waybar/dock-menu.py " + .)
        } }
  ] | add' "$apps")

# ── dock sizes derived from height (slider in dock-manager) ───────────
# Source: dock-config.json {"height": N}. Everything scales proportionally
# to the H=52 baseline (icons, modules, radius, badge), so the slider sets
# the height and the icon size follows.
H=$(jq -r '.height // 52' "$cfg/dock-config.json" 2>/dev/null || echo 52)
[[ "$H" =~ ^[0-9]+$ ]] || H=52
(( H < 36 )) && H=36
(( H > 110 )) && H=110
icon_size=$(( H * 32 / 52 ))   # wlr/taskbar icon-size
mod_h=$(( H * 40 / 52 ))       # module min-height
mod_w=$(( H * 36 / 52 ))       # module min-width
bg_size=$(( H * 28 / 52 ))     # icon (background-size)
radius=$(( H * 12 / 52 ))      # border-radius
badge_px=$(( H * 17 / 52 ))    # notification badge
(( badge_px < 13 )) && badge_px=13

# ── running indicator: split the bar into N equal segments ─────────────
# seg_bar <n> echoes a CSS gradient painting N segments of equal width,
# separated by gaps, across the SAME 50%-wide band (so the total width is
# constant regardless of the number of open instances). n=1 is a solid bar.
# Stops are emitted in tenths-of-percent for crisp, symmetric hard edges.
MAXSEG=4
seg_bar() {
  local n=$1
  if (( n <= 1 )); then printf 'linear-gradient(#d6edff, #d6edff)'; return; fi
  local gap=70 total=1000          # gap between segments, in tenths of a percent
  local seg=$(( (total - (n-1)*gap) / n ))
  local i pos=0 out='linear-gradient(90deg'
  for ((i=0; i<n; i++)); do
    local s=$pos e=$((pos+seg))
    out+=", #d6edff $((s/10)).$((s%10))%, #d6edff $((e/10)).$((e%10))%"
    if (( i < n-1 )); then
      pos=$((e+gap))
      out+=", transparent $((e/10)).$((e%10))%, transparent $((pos/10)).$((pos%10))%"
    fi
  done
  out+=')'
  printf '%s' "$out"
}

# ── compose final dock.jsonc ─────────────────────────────────────────
{
  echo '// Waybar dock for niri (generated by dock-gen.sh — do not edit by hand).'
  echo '// Source: dock-apps.json'
  jq -n \
    --argjson center "$center" \
    --argjson height "$H" \
    --argjson mods "$modules_json" \
    '{
      "layer": "top",
      "position": "bottom",
      "height": $height,
      "spacing": 6,
      "margin-bottom": 10,
      "margin-left": 6,
      "margin-right": 6,
      "modules-left": [],
      "modules-center": $center,
      "modules-right": []
    } * $mods'
} > "$out_json"

# ── resolve icons in a SINGLE pass (icon_name -> file, css class) ─────
# This used to launch python+Gtk for EVERY app (slow: ~one interpreter
# start per app = several seconds). Here a single process resolves them all:
# the pinned icon_names from stdin PLUS the Icon= of every installed
# .desktop app (for the auto-pin slots, whose icon can be any app's).
# Output: name <tab> path <tab> css-class. The name->class map is also
# written to auto-icon-classes.json — dock-autopin.py reads it to tag a
# slot with the right class (apps installed later fall back to icon-fallback
# until the next dock-gen run).
declare -A ICON_PATHS ICON_CLASS
while IFS=$'\t' read -r in_name in_path in_class; do
  [[ -n "$in_name" ]] && ICON_PATHS["$in_name"]="$in_path" && ICON_CLASS["$in_name"]="$in_class"
done < <(jq -r '.[].icon_name // empty' "$apps" | sort -u | python3 -c '
import json, re, sys, gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio
theme = Gtk.IconTheme.get_default()
names = {l.strip() for l in sys.stdin if l.strip()}
for ai in Gio.AppInfo.get_all():
    if isinstance(ai, Gio.DesktopAppInfo) and ai.should_show():
        ic = ai.get_string("Icon")
        if ic:
            names.add(ic)
names.add("application-x-executable")   # icon-fallback source
def resolve(name):
    if name.startswith("/"):           # Icon= with an absolute path
        return name
    info = theme.lookup_icon(name, 48, 0)
    return info.get_filename() if info else ""
classes = {}
for name in sorted(names):
    path = resolve(name)
    cls = "icon-" + (re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-") or "x")
    if path:
        classes[name] = cls
    print(name + "\t" + path + "\t" + cls)
import os
out = os.path.expanduser("~/.config/waybar/auto-icon-classes.json")
with open(out + ".tmp", "w") as f:
    json.dump(classes, f, indent=1, sort_keys=True)
os.replace(out + ".tmp", out)
')

# ── dock-pinned.css: common rules + icon from GTK theme + color ──────
{
  echo "/* Generated by dock-gen.sh — do not edit by hand. */"

  # Common rules applied to ALL modules (pinned + post-taskbar).
  # Single selector = CSV list of IDs, in array order.
  joined=""
  for id in "${ids[@]}" "${slot_ids[@]}"; do
    [[ -n "$joined" ]] && joined+=","
    joined+="#custom-${id}"
  done

  echo "${joined} {"
  echo "  padding: 0;"
  echo "  margin: 6px 3px;"
  echo "  min-width: ${mod_w}px;"
  echo "  min-height: ${mod_h}px;"
  echo "  border-radius: ${radius}px;"
  echo "  background-color: transparent;"
  echo "  background-repeat: no-repeat;"
  echo "  background-position: center 30%;"
  echo "  background-size: ${bg_size}px ${bg_size}px;"
  echo "  transition: background-color 120ms ease;"
  echo "}"

  hover=""
  running=""
  for id in "${ids[@]}" "${slot_ids[@]}"; do
    [[ -n "$hover" ]] && hover+=","
    hover+="#custom-${id}:hover"
    [[ -n "$running" ]] && running+=","
    running+="#custom-${id}.running"
  done

  echo "${hover} {"
  echo "  background-color: rgba(138, 173, 244, 0.28);"
  echo "  color: #ffffff;"
  echo "}"

  # "running" indicator: short centered bar at the bottom (NOT full-width).
  # Emitted per-icon in the loop below as a background layer, so it stays
  # centered and does not cover the icon. Bar width = 50%, thickness 3px.
  # With N open instances the bar splits into N segments (class instN, set by
  # dock-status.sh) within the SAME 50% band — see seg_bar() above. The bar
  # layer is always the LAST background-image layer (under icon + badge).

  # Precompute the segment gradients once (identical for every app).
  declare -A SEGBAR
  for ((s=2; s<=MAXSEG; s++)); do SEGBAR[$s]=$(seg_bar "$s"); done

  while IFS=$'\t' read -r id color icon_name; do
    icon_path="${ICON_PATHS[$icon_name]:-}"
    bar="linear-gradient(#d6edff, #d6edff)"   # solid bar (light blue toward white), n=1
    bpos="100% 0%"       # badge: outer top-right corner of the icon
    bsize="${badge_px}px ${badge_px}px"
    isize="${bg_size}px ${bg_size}px"
    # NB: in multiple background-image layers the FIRST one is on top.
    # The badge must come first so it sits ON the icon (otherwise hidden).
    if [[ -n "$icon_path" ]]; then
      ic="url(\"${icon_path}\")"
      echo "#custom-${id} { background-image: ${ic}; color: ${color}; }"
      echo "#custom-${id}.running { background-image: ${ic}, ${bar}; background-size: ${isize}, 50% 3px; background-position: center 30%, center bottom; background-repeat: no-repeat, no-repeat; }"
      for ((s=2; s<=MAXSEG; s++)); do
        echo "#custom-${id}.running.inst${s} { background-image: ${ic}, ${SEGBAR[$s]}; background-size: ${isize}, 50% 3px; background-position: center 30%, center bottom; background-repeat: no-repeat, no-repeat; }"
      done
      for k in 1 2 3 4 5 6 7 8 9 9p; do
        bg="url(\"${badges_dir}/badge-${k}.svg\")"
        echo "#custom-${id}.nb${k} { background-image: ${bg}, ${ic}; background-size: ${bsize}, ${isize}; background-position: ${bpos}, center 30%; background-repeat: no-repeat, no-repeat; }"
        echo "#custom-${id}.running.nb${k} { background-image: ${bg}, ${ic}, ${bar}; background-size: ${bsize}, ${isize}, 50% 3px; background-position: ${bpos}, center 30%, center bottom; background-repeat: no-repeat, no-repeat, no-repeat; }"
        for ((s=2; s<=MAXSEG; s++)); do
          echo "#custom-${id}.running.inst${s}.nb${k} { background-image: ${bg}, ${ic}, ${SEGBAR[$s]}; background-size: ${bsize}, ${isize}, 50% 3px; background-position: ${bpos}, center 30%, center bottom; background-repeat: no-repeat, no-repeat, no-repeat; }"
        done
      done
    else
      echo "#custom-${id} { color: ${color}; }"
      echo "#custom-${id}.running { background-image: ${bar}; background-size: 50% 3px; background-position: center bottom; background-repeat: no-repeat; }"
      for ((s=2; s<=MAXSEG; s++)); do
        echo "#custom-${id}.running.inst${s} { background-image: ${SEGBAR[$s]}; background-size: 50% 3px; background-position: center bottom; background-repeat: no-repeat; }"
      done
      for k in 1 2 3 4 5 6 7 8 9 9p; do
        bg="url(\"${badges_dir}/badge-${k}.svg\")"
        echo "#custom-${id}.nb${k} { background-image: ${bg}; background-size: ${bsize}; background-position: ${bpos}; background-repeat: no-repeat; }"
        echo "#custom-${id}.running.nb${k} { background-image: ${bg}, ${bar}; background-size: ${bsize}, 50% 3px; background-position: ${bpos}, center bottom; background-repeat: no-repeat, no-repeat; }"
        for ((s=2; s<=MAXSEG; s++)); do
          echo "#custom-${id}.running.inst${s}.nb${k} { background-image: ${bg}, ${SEGBAR[$s]}; background-size: ${bsize}, 50% 3px; background-position: ${bpos}, center bottom; background-repeat: no-repeat, no-repeat; }"
        done
      done
    fi
  done < <(jq -r '.[] | "\(.id)\t\(.color)\t\(.icon_name // "")"' "$apps")

  # ── auto-pin slot rules: one per UNIQUE resolved icon, all slots in the
  # selector list. An occupied slot is by definition a running app, so the
  # icon and the single running bar are layered in the same rule (no instN
  # split for slots: the bar stays solid). Class set by dock-status.sh from
  # the slot entry's icon_class field (manifest: auto-icon-classes.json).
  bar="linear-gradient(#d6edff, #d6edff)"
  isize="${bg_size}px ${bg_size}px"
  for icon_name in "${!ICON_PATHS[@]}"; do
    icon_path="${ICON_PATHS[$icon_name]}"
    [[ -n "$icon_path" ]] || continue
    cls="${ICON_CLASS[$icon_name]}"
    sel=""
    for sid in "${slot_ids[@]}"; do
      [[ -n "$sel" ]] && sel+=","
      sel+="#custom-${sid}.${cls}"
    done
    echo "${sel} { background-image: url(\"${icon_path}\"), ${bar}; background-size: ${isize}, 50% 3px; background-position: center 30%, center bottom; background-repeat: no-repeat, no-repeat; }"
    # instN variants: bar split into N segments, same as the pinned icons
    # (class emitted by dock-status.sh; capped at MAXSEG).
    for ((s=2; s<=MAXSEG; s++)); do
      sel=""
      for sid in "${slot_ids[@]}"; do
        [[ -n "$sel" ]] && sel+=","
        sel+="#custom-${sid}.${cls}.inst${s}"
      done
      echo "${sel} { background-image: url(\"${icon_path}\"), ${SEGBAR[$s]}; background-size: ${isize}, 50% 3px; background-position: center 30%, center bottom; background-repeat: no-repeat, no-repeat; }"
    done
  done
} > "$out_css"

# ── restart dock waybar ──────────────────────────────────────────────
if [[ "${1:-}" != "--no-reload" ]]; then
  pkill -f "waybar -c .*dock.jsonc" 2>/dev/null || true
  sleep 0.4
  setsid sh -c "waybar -c $out_json -s $cfg/dock.css" >/tmp/waybar-dock.log 2>&1 < /dev/null &
  disown 2>/dev/null || true
fi

echo "Dock regenerated: $count apps (${#pinned_ids[@]} pre-taskbar, ${#post_ids[@]} post-taskbar: ${post_ids[*]})."
