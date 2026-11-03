@echo off
cd /d "%~dp0"
if not exist venv (
  echo Creating virtual environment...
  python -m venv venv || (echo Python 3.9+ is required. & pause & exit /b 1)
)
call venv\Scripts\activate
echo Installing/updating pip dependencies (keeps yt-dlp up to date)...
pip install -q -U -r requirements.txt || pip install -q -U flask imageio-ffmpeg "yt-dlp[default]"
python server.py
pause
