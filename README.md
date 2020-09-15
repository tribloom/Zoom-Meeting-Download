# Zoom-Meeting-Download
Download Zoom cloud recordings and transfer them to Google drive

Usage:
$ python zoom_meeting_download.py
python zoom_meeting_download.py -s <settings_file> -e <email> -f <from> -t <to>
Options:
  -e email     download this Zoom user's recordings
  -f from      the date from which to download recordings, format yyyy-mm-dd, if not provided defaults to 2019-09-26
  -s settings  load settings from file
  -t to        the date from which to download recordings, format yyyy-mm-dd, if not provided defaults to today's date

