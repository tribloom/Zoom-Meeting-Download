# Zoom-Meeting-Download

Note: You must create a "logs" directory under scripts location or you will get an error. You will need to have a OAuth credentials from Zoom in order to run the script, not a user's key and secret. Instructions for Zoom Oauth are found at https://marketplace.zoom.us/docs/guides/build/oauth-app. You may want/need to adjust line 553 (directory = "/srv/app_bconnsync_aux0/" + args["email"] + " Zoom recordings"+date_string) to fit your OS and directory structure.

Download Zoom cloud recordings and transfer them to Google drive

Usage:

```
$ python zoom_meeting_download.py

python zoom_meeting_download.py -s <settings_file> -e <email> -f <from> -t <to>
Options:
  -e email     download this Zoom user's recordings
  -f from      the date from which to download recordings, format yyyy-mm-dd, if not provided defaults to 2019-09-26
  -s settings  load settings from file
  -t to        the date from which to download recordings, format yyyy-mm-dd, if not provided defaults to today's date
  ```

Note: JWT has been removed and now uses OAuth. If you run into problems with the OAuth token becoming invalid (usually an hour), you may have to rerun the script or remove multiprocessing.
