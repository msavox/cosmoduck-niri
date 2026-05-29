#!/bin/bash

set -ex

cd "$(dirname "$0")"
mkdir -p data
touch ./data/title ./data/artist ./data/status

# Fetch playing info from playerctl.
playerctl -F metadata mpris:artUrl | ./scripts/curl_stdin.sh ./data/artwork.png &
ARTWORK_PID=$!
playerctl -F status  | ./scripts/write_to_file.sh ./data/status &
STATUS_PID=$!
playerctl -F metadata artist  | ./scripts/write_to_file.sh ./data/artist &
ARTIST_PID=$!
playerctl -F metadata title  | ./scripts/write_to_file.sh ./data/title &
TITLE_PID=$!

kill_playerctl_processes() {
    kill $ARTWORK_PID
    kill $STATUS_PID
    kill $ARTIST_PID
    kill $TITLE_PID
}

# Make sure we kill the playerctl processes when we exit.
trap kill_playerctl_processes SIGINT
trap kill_playerctl_processes SIGTERM

# Launch conky.
conky -c $HOME/.config/conky/Regulus-MOD-Cosmoduck/config/cnp.conf &> /dev/null &
conky -c $HOME/.config/conky/Regulus-MOD-Cosmoduck/config/Regulus.conf &> /dev/null &


exit
