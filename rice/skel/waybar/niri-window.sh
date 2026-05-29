#!/bin/bash
# Custom Waybar module: title of the currently focused window.

w=$(niri msg --json focused-window 2>/dev/null)
if [ -z "$w" ] || [ "$w" = "null" ]; then
    printf '{"text":""}\n'
    exit 0
fi

jq -c '
    (.title // .app_id // "") as $t
    | {
        text: (if ($t | length) > 80 then ($t[0:77] + "…") else $t end),
        tooltip: (.app_id // ""),
        class: "niri-window"
    }
' <<<"$w"
