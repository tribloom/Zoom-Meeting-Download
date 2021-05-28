# Zoom-Meeting-Download

Note: You must create a "logs" directory under scripts location or you will get an error. You will need to have a OAuth credentials from Zoom in order to run the script, not a user's key and secret. Instructions for Zoom Oauth are found at https://marketplace.zoom.us/docs/guides/build/oauth-app.

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

Troubleshooting:
AttributeError: 'str' object has no attribute 'decode':
There appears to be an issue with PyJWT that causes this error in newer versions of the library. See https://github.com/jazzband/djangorestframework-simplejwt/issues/346 for details. You can run 'pip freeze' to see the installed version of PyJWT. To downgrade library verions:
```
pip uninstall PyJWT
pip install --upgrade PyJWT==1.7.1
```
