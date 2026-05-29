#!/bin/sh
# playerctl -F status | ./write_to_file.sh filename

while read -r data; do
    echo "$data"
    echo "$data" > "$1"
done
