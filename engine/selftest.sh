#!/usr/bin/env bash
# Synthetic source for plumbing tests (robotic Russian speech over a test pattern). Not a quality test.
set -euo pipefail
out="${1:-source.mp4}"
sudo apt-get install -y espeak-ng >/dev/null
cat > /tmp/selftest.txt <<'TXT'
Сегодня я расскажу, как заработать первый миллион рублей. Э, ну, как бы, короче. Первое. Правильная цель на весь мир.
Второе. Быстрый старт без ошибок. Быстрый старт без ошибок и без риска. Третье, это время, которое вы экономите каждый день.
Если делать это каждый день, результат будет через три месяца. Подписывайтесь, чтобы не потерять этот метод.
TXT
espeak-ng -v ru -s 150 -f /tmp/selftest.txt -w /tmp/selftest.wav
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 /tmp/selftest.wav)
ffmpeg -y -loglevel error -f lavfi -i "testsrc2=s=1080x1920:r=30" -i /tmp/selftest.wav -t "$dur" \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$out"
