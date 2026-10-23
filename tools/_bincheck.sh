#!/bin/bash
ROOT=/mnt/d/Github/QualityScaler-Linux
rm -rf ~/disttest && mkdir -p ~/disttest && cp "$ROOT/dist/QualityScaler" ~/disttest/
cd ~/disttest || exit 1
Xvfb :81 -screen 0 1000x675x24 -dpi 96 >/dev/null 2>&1 &
XPID=$!
sleep 3
PYTHONUNBUFFERED=1 DISPLAY=:81 timeout 60 ./QualityScaler > ~/bincheck.log 2>&1 &
APP=$!
sleep 22
DISPLAY=:81 import -window root ~/bincheck.png 2>/dev/null
kill $APP 2>/dev/null; wait $APP 2>/dev/null; kill $XPID 2>/dev/null
echo "--- log ---"; cat ~/bincheck.log
cp ~/bincheck.png "$ROOT/tools/_bincheck.png"
