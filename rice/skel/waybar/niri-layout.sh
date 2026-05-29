#!/usr/bin/env bash
data=$(niri msg --json keyboard-layouts 2>/dev/null) || { echo '{"text":"?","tooltip":"niri not responding"}'; exit 0; }
idx=$(echo "$data" | jq -r '.current_idx')
name=$(echo "$data" | jq -r ".names[$idx]")
case "$name" in
  "Italian")                                        sigla="IT" ;;
  "English (US)")                                   sigla="US" ;;
  "English (US, intl., with dead keys)")            sigla="US-INTL" ;;
  *intl*|*Intl*|*INTL*)                             sigla="US-INTL" ;;
  *)                                                sigla="$(echo "$name" | tr -d -c 'A-Z')" ;;
esac
printf '{"text":"%s","tooltip":"%s"}\n' "$sigla" "$name"
