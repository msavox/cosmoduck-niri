#!/usr/bin/env bash
# osd-notify.sh <volume|mic|brightness>
# Poke the OSD daemon (osd.py) after a volume/brightness key bind has run.
# The timeout guards the corner case where the fifo exists but the daemon is
# dead (open would block forever); the actual setting change happened anyway.
p="${XDG_RUNTIME_DIR:-/tmp}/cosmoduck-osd.fifo"
[[ -p "$p" ]] && timeout 0.3 sh -c "echo '$1' > '$p'" 2>/dev/null
exit 0
