#!/bin/bash
current_hour=$(date +%H)

if [ $current_hour -ge 5 -a $current_hour -lt 12 ]; then
    echo "Good morning,"
elif [ $current_hour -ge 12 -a $current_hour -lt 17 ]; then
    echo "Good afternoon,"
elif [ $current_hour -ge 17 -a $current_hour -lt 21 ]; then
    echo "Good evening,"
else
    echo "Good night,"
fi
