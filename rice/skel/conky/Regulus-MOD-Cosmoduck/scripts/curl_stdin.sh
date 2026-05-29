#!/bin/sh
# playerctl -F metadata mpris:artUrl | ./curl_stdin.sh artwork.png

while read -r url; do
    curl -s "$url" -o "$1"
done
