echo "This script will install/update the pip dependencies and Deno runtime."
read -r -p "Are you sure you want to proceed? [y/N] " response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]
then
    do_something
else
    do_something_else
fi


echo "Installing/updating dependencies (keeps yt-dlp up to date)..."
pip install -q -U -r requirements.txt || pip install -q -U flask imageio-ffmpeg "yt-dlp[default]"

echo "Installing Deno..."
curl -fsSL https://deno.land/install.sh | sh