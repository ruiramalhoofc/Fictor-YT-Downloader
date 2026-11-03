echo This script will install/update the pip dependencies and Deno runtime.
@echo off
setlocal
:PROMPT
SET /P CONFIRM=Are you sure you want to proceed? (Y/[N])?
IF /I "%CONFIRM%" NEQ "Y" GOTO END

echo Installing/updating pip dependencies (keeps yt-dlp up to date)...
pip install -q -U -r requirements.txt || pip install -q -U flask imageio-ffmpeg "yt-dlp[default]"

echo Installing Deno...
irm https://deno.land/install.ps1 | iex

pause