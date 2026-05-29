#!/bin/bash
# Custom Waybar module: niri workspaces (polled).
# Emits JSON consumed by waybar custom module (return-type: json).

ws=$(niri msg --json workspaces 2>/dev/null)
if [ -z "$ws" ]; then
    printf '{"text":"","tooltip":"niri non risponde"}\n'
    exit 0
fi

jq -c '
    sort_by(.output, .idx) as $list
    | {
        text: (
            $list
            | map(
                if .is_focused then "<span foreground=\"#8aadf4\" weight=\"bold\">[\(.idx)]</span>"
                elif .is_active then "<span foreground=\"#a6da95\">(\(.idx))</span>"
                elif .is_urgent then "<span foreground=\"#ed8796\" weight=\"bold\">!\(.idx)!</span>"
                else " \(.idx) "
                end
              )
            | join(" ")
        ),
        tooltip: (
            $list
            | map("\(.output) ws \(.idx)" + (if .is_focused then " ← focus" elif .is_active then " (active)" else "" end))
            | join("\n")
        ),
        class: "niri-workspaces"
    }
' <<<"$ws"
