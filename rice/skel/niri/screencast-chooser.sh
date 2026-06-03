#!/usr/bin/env bash
# screencast-chooser.sh — output chooser for xdg-desktop-portal-wlr (screen share).
#
# xdpw (dmenu mode) pipes the list of shareable outputs to this script, one
# connector name per line (e.g. eDP-1 / DP-1). Bare connector names are hard to
# tell apart, so we annotate each with "(laptop)" or "(external · Vendor)" by
# reading make/model from `niri msg outputs`, show them in wofi, and print the
# ORIGINAL line of the chosen entry back to stdout (xdpw matches it as-is).
#
# Wired up via rice/skel/xdg-desktop-portal-wlr/config:
#   chooser_cmd=__HOME__/.config/niri/screencast-chooser.sh

set -euo pipefail

# Lines xdpw asks us to choose from (one output name per line).
mapfile -t inputs

# connector -> annotation, parsed from niri.
declare -A annot
while IFS= read -r line; do
  # Format: Output "<make model serial>" (<connector>)
  if [[ $line =~ ^Output\ \"(.*)\"\ \(([^\)]+)\)[[:space:]]*$ ]]; then
    desc="${BASH_REMATCH[1]}"
    conn="${BASH_REMATCH[2]}"
    case "$conn" in
      eDP-*|LVDS-*|DSI-*)
        annot[$conn]="laptop"
        ;;
      *)
        vendor="${desc%% *}"   # first word of the description = vendor/brand
        if [[ -n $vendor && $vendor != "Unknown" ]]; then
          annot[$conn]="external · $vendor"
        else
          annot[$conn]="external"
        fi
        ;;
    esac
  fi
done < <(niri msg outputs 2>/dev/null || true)

# Build the annotated menu and map each label back to its original line.
declare -A back
menu=""
for orig in "${inputs[@]}"; do
  label="$orig"
  for conn in "${!annot[@]}"; do
    if [[ $orig == *"$conn"* ]]; then
      label="$orig (${annot[$conn]})"
      break
    fi
  done
  back[$label]="$orig"
  menu+="$label"$'\n'
done

chosen=$(printf '%s' "$menu" | wofi --dmenu --prompt "Select monitor to share")
[[ -z $chosen ]] && exit 1   # empty stdout => user declined

# Return the original line untouched so xdpw recognizes the output.
printf '%s\n' "${back[$chosen]:-$chosen}"
