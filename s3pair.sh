#!/bin/bash

cd /home/pi/work/m5000

RUN='python main.py'

if [ "$1" = "run" ]; then
    $RUN &
elif [ "$1" = "kill" ]; then
    pkill -f $RUN
fi