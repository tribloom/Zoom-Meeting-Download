#! /bin/bash

source /home/app_bconnsync/venvs/box_venv/bin/activate
cd /home/app_bconnsync/box-user-info/dev/zoom/

while IFS="" read -r current_zoom_user || [ -n "$current_zoom_user" ]
do
  printf '================================\n%s\n' "$current_zoom_user"
  date
  python -u zoom_meeting_download.py -s download_settings_prod.json -e $current_zoom_user
  #rm -rvf  /srv/app_bconnsync_aux0/$current_zoom_user*
done < download_file.txt

date
echo "RUN COMPLETE!"
