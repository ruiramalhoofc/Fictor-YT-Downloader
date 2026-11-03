#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1
[ -d venv ] || python3 -m venv venv || { echo "Python 3.9+ is required."; exit 1; }
. venv/bin/activate
echo "Installing/updating dependencies (keeps yt-dlp up to date)..."
pip install -q -U -r requirements.txt || pip install -q -U flask imageio-ffmpeg "yt-dlp[default]"
exec python server.py
