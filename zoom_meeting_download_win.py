#!/usr/bin/env python

# Psuedocode for Windows environment
# given an email, lookup zoom user id
# given a zoom id and a date, download all videos before the date
# videos are only viewable 1 month at a time
# for all time periods before the given date, query 1 month at a time
# if multiple pages are returned, iterate through the pages

__author__ = "Michael McCarthy, Tribloom Inc."
__copyright__ = "Copyright 2020 University of California Berkeley"
__credits__ = ["Michael McCarthy", "Ian Crew"]
__license__ = "MIT License"
__version__ = "0.01"
__maintainer__ = "Michael McCarthy"
__email__ = "mmccarthy@tribloom.com"
__status__ = "Beta"


# System Imports
from datetime import datetime
from datetime import date
from datetime import timedelta
from datetime import timezone
import getopt
import http.client
import json
import logging
from logging import Formatter, Logger, StreamHandler
from logging.handlers import RotatingFileHandler
from multiprocessing import Manager, Process, Queue, Value
import os
import queue
from retrying import retry
import sys
from sys import argv
from time import time
import traceback
import urllib.request
import base64

# Third Party Imports
import jwt # pip install pyjwt

# Loaded from settings file
settings = {}

# Mapping of Zoom type to file extension see: https://marketplace.zoom.us/docs/api-reference/zoom-api/cloud-recording/recordingslist
extensions = {
    "MP4": "mp4",
    "M4A": "m4a",
    "TIMELINE": "json",
    "TRANSCRIPT": "vtt",
    "CHAT": "txt",
    "CC": "vtt"
    }

token = None
token_timeout = 3599
token_time = None


# Create logger with "zoom"
logger = logging.getLogger("zoom")
logger.setLevel(logging.DEBUG)
# create rotating file handler
now = datetime.now().strftime("%Y-%m-%d.%H.%M.%S")
file_handler = RotatingFileHandler("logs/"+now+"-zoom-download.log")
file_handler.setLevel(logging.DEBUG)
# create console handler
console_handler = StreamHandler()
console_handler.setLevel(logging.DEBUG)
# create a formatter and add it to the handlers
formatter = Formatter("%(asctime)s %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)


#===============================================================================
#= Server-to-Server OAuth
#===============================================================================


"""
Generate an OAuth access token to send with the request to Zoom.
curl -X POST -H "Authorization: Basic cXpxeGF5TXBTaHE0U2tOQnF5ZVNGZzpxZHVkRjQ5NVM1dGQ4OXlSaWhBUVI2YVI5a0JoZGNQQg==" "https://zoom.us/oauth/token?grant_type=account_credentials&account_id=3UsMLvXPSHaZYOVqDRE-Rw"
"""
@retry(wait_exponential_multiplier=5000, wait_exponential_max=50000,stop_max_attempt_number=10) #set to 10 for prod
def get_token():
    global token
    global token_time
    if token is not None:
       return token
    encoded = base64.b64encode(bytes(settings["zoom"]['client_id']+':'+settings['zoom']['client_secret'], 'utf-8'))
    encoded = str(encoded, 'utf-8')
    headers = {
              'authorization': 'Basic'+encoded
              }
    connection = http.client.HTTPSConnection(settings["zoom"]["url"])
    connection.request("POST", "/oauth/token/?grant_type=account_credentials&account_id=%s" % settings['zoom']['account_id'], headers=headers)
    res = connection.getresponse()
    token_time = datetime.now()
    data = res.read()
    t = json.loads(data.decode("utf-8"))['access_token']
    token = t

    return token


"""
Get request headers with a  Sever-to-Server access token, refesh as needed.
"""
def get_headers():
    global token_time
    global token
    if token_time == None:
        get_token()

    if (datetime.now() - token_time).total_seconds() > token_timeout:
        token = None
    headers = {
        'authorization': "Bearer %s" % get_token()
    }

    return headers



#===============================================================================
#= Settings File
#===============================================================================


"""
Load the settings from the settings file (JSON).
"""
def load_settings(settings_filename):
    with open(settings_filename, "r") as settings_file:
        return json.load(settings_file)


#===============================================================================
#= Argument Parsing
#===============================================================================


"""
Parse command line arguments.
"""
def parse_args(argv):
    # command line args
    clargs = {}

    if argv == []:
        usage()
        sys.exit(2)

    try:
        opts, args = getopt.getopt(argv,"s:e:f:t:",["settings","email","from","to"])
    except getopt.GetoptError as e:
        logger.error("Failure parsing arguments:")
        logger.error(str(e))
        traceback.print_exc()
        usage()
        sys.exit(2)

    for opt, arg in opts:
        if opt in ("-s", "--settings"):
            clargs["settings_filename"] = arg
            logger.info("Using settings file: " + str(clargs["settings_filename"]))
        elif opt in ("-e", "--email"):
            clargs["email"] = arg
            logger.info("Using email address: " + str(clargs["email"]))
        elif opt in ("-f", "--from"):
            dt = datetime.strptime(arg, "%Y-%m-%d")
            clargs["from"] = date(dt.year, dt.month, dt.day)
            logger.info("Using from date: " + str(clargs["from"]))
        elif opt in ("-t", "--to"):
            dt = datetime.strptime(arg, "%Y-%m-%d")
            clargs["to"] = date(dt.year, dt.month, dt.day)
            logger.info("Using to date: " + str(clargs["to"]))

    return clargs


"""
Print usage.
"""
def usage():
    print("python zoom_meeting_download.py -s <settings_file> -e <email> [-f <from>] [-t <to>]")
    print("Options:")
    print("  -e email     download this Zoom user's recordings")
    print("  -f from      the date from which to download recordings, format yyyy-mm-dd, if not provided defaults to 2019-09-26")
    print("  -s settings  load settings from file")
    print("  -t to        the date from which to download recordings, format yyyy-mm-dd, if not provided defaults to today's date")


#===============================================================================
#= Settings File
#===============================================================================


"""
Load the settings from the settings file (JSON).
"""
def load_settings(settings_filename):
    with open(settings_filename, "r") as settings_file:
        return json.load(settings_file)


#===============================================================================
#= ZOOM
#===============================================================================


"""
Get a Zoom user by Zoom user ID and return it. 
A Zoom login (an email address) is synonymous to a Zoom ID in terms of the API,
so "zoom_user_id" can be "tribloom@berkeley.edu" or "odkolRk8R8q5qF0KsGLtpA".
"""
@retry(wait_exponential_multiplier=5000, wait_exponential_max=50000,stop_max_attempt_number=10) 
def get_zoom_user(zoom_user_id):
    global settings
    logger.debug("Settings: " + json.dumps(settings, indent=4, sort_keys=True))

    connection = http.client.HTTPSConnection(settings["zoom"]["url"])
    connection.request("GET", "/v2/users/%s" % zoom_user_id, headers=get_headers())
    res = connection.getresponse()

    if res.status == 429:
        message = res.msg
        logger.warning("API requests too fast looking up user '" + zoom_user_id + "'. Message: "+message)
        debug_response(res)
        connection.close()
        raise Exception("API requests too fast looking up user '" + zoom_user_id + "'. Message: "+message)
    elif res.status == 401:
        logger.debug('OAuth token expired. Refreshing.')
        global token
        token = None
    elif res.status == 404:
        logger.warning("User '" + zoom_user_id + "' was not found in Zoom, status "+str(res.status)+".")
        debug_response(res)
        return None
    else: #elif res.status == 200:
        data = res.read()
        if len(data) == 0:
            logger.warning("User '" + zoom_user_id + "' no data returned.")
            debug_response(res)
        user = json.loads(data.decode("utf-8"))
    # can't return a response after the connection is closed
    connection.close()
    return user

"""
Get a Zoom user's (by user id) recordings given an optional from and to date.
If no from_date is given, use the "earliest_date" from the settings file.
If no to_date is given, use yesterday's date.
The Zoom API only returns a maximum of 4 weeks of recordings so break up the
time range into 4 week segments.
"""
def get_user_recordings(user_id, from_date="", to_date=""):
    global settings
    logger.debug("Settings: " + json.dumps(settings, indent=4, sort_keys=True))
    meetings = []

    logger.debug("Using FROM date: "+str(from_date))
    logger.debug("Using TO date: "+str(to_date))

    dt = datetime.strptime(settings["earliest_date"], "%Y-%m-%d")
    earliest_date = date(dt.year, dt.month, dt.day)
    td = to_date
    fd = td - timedelta(weeks=4)
    if from_date > fd:
        fd=from_date
    (m, npt, meeting_ids) =  query_zoom_recordings(user_id, fd, td)
    meetings = meetings + m
    #logger.debug("meetings: "+str(meetings))

    # subtract 1 month from to_date until it is before or equal to earliest_date
    while fd > from_date and fd > earliest_date:
        #logger.debug("fd >= from_date: "+str( fd >= from_date))
        #logger.debug("fd >= earliest_date: "+str( fd >= earliest_date))
        #logger.debug("subtract 1 month from to date "+str(fd))
        td = td - timedelta(weeks=4, days=1)
        fd = td - timedelta(weeks=4)
        if from_date > earliest_date:
            if fd < from_date:
                fd = from_date
        else:
            if fd < earliest_date:
                fd = earliest_date
        logger.debug(str(fd)+ " to "+str(td))
        (m, npt, meeting_ids) =  query_zoom_recordings(user_id, fd, td)
        meetings = meetings + m
        #logger.debug("Meetings: "+str(meetings))
    #logger.debug("Meetings: "+str(meetings))
    return meetings

"""
Query the Zoom API to get the user's (by user id) recordings for the given time period.
If there are multiple pages for the time period, use a page token to get the next page.

As of 9/15/2020 Zoom acknowleged that there is an issue with the API:
It appears the getaccountcloudrecording API endpoint (https://marketplace.zoom.us/docs/api-reference/zoom-api/cloud-recording/getaccountcloudrecording) is not respecting the page_size parameter. I set the page_size to 1 and get 2 meeting recordings back AND a next page token. The second page is exactly the same as the first except it has no page token. 
"""
def query_zoom_recordings(user_id, from_date="", to_date="", next_page_token=""):
    #logger.debug("entry next page token: "+next_page_token)
    connection = http.client.HTTPSConnection(settings["zoom"]["url"])
    query_str = "/v2/users/%s/recordings?page_size=300" % user_id
    if next_page_token is not None and next_page_token != "":
        query_str += "&next_page_token="+next_page_token
    if not from_date == "":
        query_str += "&from="+datetime.strftime(from_date, "%Y-%m-%d")

    if not to_date == "":
        query_str += "&to="+datetime.strftime(to_date, "%Y-%m-%d")

    logger.debug("Query: "+query_str)
    connection.request("GET", query_str, headers=get_headers())
    res = connection.getresponse()

    if res.status == 404:
        message = res.msg
        logger.warning("User '" + user_id + "' does not exist or does not belong to this account. Message: " + message)
        debug_response(res)
        connection.close()
        return None
    elif res.status == 401:
        logger.debug('OAuth token expired. Refreshing.')
        global token
        token = None
    else: # res.status == 200
        data = res.read()
        if len(data) == 0:
            logger.warning("User '" + user_id + "' no data returned.")
            debug_response(res)
        recordings = json.loads(data.decode("utf-8"))
        #logger.debug("recordings: "+str(recordings))
        meetings = recordings["meetings"]
        meeting_ids = set()
        for meeting in meetings:
            meeting_ids.add(meeting["uuid"])
        #logger.debug("Meetings Outer: "+str(meetings))
        #logger.debug(str(recordings))
        #logger.debug("next page token: '"+recordings["next_page_token"]+"'")
        #logger.debug("not empty: " + str( recordings["next_page_token"] != ""))
        npt = recordings["next_page_token"]
        while npt != "":
            #logger.debug("test: "+npt)
            (m, npt, mi) = query_zoom_recordings(user_id, from_date, to_date, npt)
            for mx in m:
                #print("meeting: "+str(mx))
                #print("UUID: "+mx["uuid"])
                #print("UUIDs: "+str(meeting_ids))
                #print("uid in uids: "+str(mx["uuid"] in meeting_ids))
                if mx["uuid"] in meeting_ids:
                    logger.error("Skipping already added meeting "+mx["uuid"])
                    continue
                else:
                    meetings.append(mx)
                    meeting_ids.add(mx["uuid"])
            #meetings = meetings + m
            
            #logger.debug("Meetings Inner: "+str(meetings))
            
    connection.close()
    return (meetings, npt, meeting_ids)



"""
Debug a HTTP response object.
"""
def debug_response(res):
    data = res.read()
    logger.debug("Data: "+data.decode("utf-8"))
    logger.debug("Headers: "+str(res.getheaders()))
    logger.debug("Message: "+str(res.msg))
    logger.debug("Status: " +str(res.status))
    logger.debug("Reason: " +str(res.reason))


#===============================================================================
#= 
#===============================================================================


"""
Download the files from Zoom, use an access token to prevent being prompted for login.
"""
def download_recordings(meetings, directory):
    #print(str(meetings))
    for meeting in meetings:
        start_time = datetime.strptime(meeting["start_time"], "%Y-%m-%dT%H:%M:%SZ")
        start_time = start_time.replace(tzinfo=timezone.utc).astimezone(tz=None)
        #subdir = meeting["start_time"] + " - " + meeting["topic"]
        subdir = start_time.strftime("%Y-%m-%d %I.%M.%S %p") + " - " + meeting["topic"]
        logger.debug("subdir: "+subdir)
        subdir = subdir.replace("\\", "-")
        subdir = subdir.replace("/", "-")
        subdir = subdir.replace(" ", "-")
        logger.debug("subdir: "+subdir)
        try:
            if not os.path.exists(directory + "\\" + subdir):
                logger.debug("Making directory: "+directory + "\\" + subdir)
                os.mkdir(directory + "\\" + subdir)
            else:
                logger.warning("Directory already exists: " + directory + "\\" + subdir)
        except OSError as ose:
            traceback.print_exc()
            logger.error(ose)
            logger.error("Creation of the directory failed: " + directory + "\\" + subdir)
            
        for f in meeting["recording_files"]:
            #print("f: "+str(f))
            if "status" in f and f["status"] == "processing":
                logger.warning("Skipping meeting file being processed: " + meeting["topic"])
                continue
            filename = (f["recording_type"] + " " if "recording_type" in f else "") + f["file_type"] + "." + extensions[f["file_type"]]
            opener = urllib.request.build_opener()
            opener.addheaders(tuple(get_headers().items()))
            urllib.request.install_opener(opener)
            urllib.request.urlretrieve(f["download_url"], directory + "/" + subdir + "/" + filename)




"""
multiprocessing
"""
def multi_download_zoom_recordings(meetings, directory, num_workers=8):
    log_separator(logging.INFO, "Multiprocessing download zoom recordings.")
    # create a shared work queue
    manager = Manager()
 
    queue_download_zoom_meetings = manager.Queue()
    # while we still have items to process
    while len(meetings) > 0:
        # if our shared queue_download_zoom_meetings is empty, add up to 25000 items to it
        if queue_download_zoom_meetings.qsize() == 0:
            i = 0
            while i < 25000 and len(meetings) > 0:
                user = meetings.pop(0)
                queue_download_zoom_meetings.put(user)
                i += 1
            logger.info("Added " + str(i) + " items to queue_download_zoom_meetings. " + str(len(meetings)) + " remaining")
        workers = []
        while queue_download_zoom_meetings.qsize() > 0:
            num_workers = min(queue_download_zoom_meetings.qsize(), num_workers)
            for _ in range(num_workers):
 #                for user, payload in queue_download_zoom_meetings.get().items():
                    #user = queue_download_zoom_meetings.get().items()[0]
                    #print("user: "+str(user))
                    #print("payload: "+str(payload))
                    #print("User: "+str(user.keys()))
                    #print("User: "+str(user[user.keys()]))
                worker = Process(target = worker_download_meetings, args = (queue_download_zoom_meetings,directory))
                worker.start()
                workers.append(worker)
            for worker in workers:
                worker.join(7200)
                if worker.is_alive():
                    logger.error("Failed to process "+ str(worker) + " after 2 hours.")

        logger.debug("All workers processes joined successfully. "+str(len(meetings))+" meetings remaining")


def worker_download_meetings(queue_download_zoom_meetings,directory):
    while not queue_download_zoom_meetings.empty():
        try:
            meeting=queue_download_zoom_meetings.get(timeout=0.001)
            download_single_meeting(meeting,directory) #doing this as a function call so that we can use the @retry decorator
            if queue_download_zoom_meetings.qsize() ==0: break
        except queue.Empty:
            #we're done, so leave
            break
        except urllib.error.HTTPError as e:
            logger.error("Failed to download meeting "+str(meeting["topic"])+" at "+str(meeting["start_time"])+" to directory "+directory+" due to "+str(e)+".")
#             traceback.print_exc()
#             logger.error(e)
            raise
        except:
            raise
            break

@retry(wait_exponential_multiplier=5000, wait_exponential_max=50000,stop_max_attempt_number=5) #set to 10 for prod
def download_single_meeting(meeting,directory):
        global settings
        args = parse_args(argv)
        settings = load_settings("download_settings_dev.json")
        try:
            start_time = datetime.strptime(meeting["start_time"], "%Y-%m-%dT%H:%M:%SZ")
            start_time = start_time.replace(tzinfo=timezone.utc).astimezone(tz=None)
            #subdir = meeting["start_time"] + " - " + meeting["topic"]
            subdir = start_time.strftime("%Y-%m-%d %I.%M.%S %p") + " - " + meeting["topic"]
            logger.debug("subdir: "+subdir)
            subdir = subdir.replace("\\", "-")
            subdir = subdir.replace("/", "-")
            subdir = subdir.replace(" ", "-")
            logger.debug("subdir: "+subdir)
            try:
                if not os.path.exists(directory + "\\" + subdir):
                    logger.debug("Making directory: "+directory + "\\" + subdir)
                    os.mkdir(directory + "\\" + subdir)
                else:
                    logger.warning("Directory already exists: " + directory + "\\" + subdir)
            except OSError as ose:
                traceback.print_exc()
                logger.error(ose)
                logger.error("Creation of the directory failed: " + directory + "\\" + subdir)
        
            for f in meeting["recording_files"]:
                #print("f: "+str(f))
                if "status" in f and f["status"] == "processing":
                    logger.warning("Skipping meeting file being processed: " + meeting["topic"])
                    continue
                filename = (f["recording_type"] + " " if "recording_type" in f else "") + f["file_type"] + "." + extensions[f["file_type"]]
                opener = urllib.request.build_opener()
                opener.addheaders(tuple(get_headers().items()))
                urllib.request.install_opener(opener)
                urllib.request.urlretrieve(f["download_url"], directory + "/" + subdir + "/" + filename)
        except urllib.error.HTTPError as e:
            logger.error("Got error "+str(e)+" when trying to download single meeting to directory "+directory+" with meeting "+str(meeting["topic"])+" at "+str(meeting["start_time"])+", retrying.")
#             traceback.print_exc()
#             logger.error(e)
            raise
      	
        except:
            logger.error("Got error when trying to download single meeting to directory "+directory+" with meeting "+str(meeting)+", retrying.")
            traceback.print_exc()
#             logger.error(e)
            raise


#===============================================================================
#= Logging Helpers
#===============================================================================


def log_separator(level, title):
    logger.log(level, "===============================================================================")
    logger.log(level, title)
    logger.log(level, "===============================================================================")


def log_user_changes(level, items):
    logger.log(level, "===============================================================================")
    for item in items:
        logger.log(level, item)
    logger.log(level, "===============================================================================")


def log(level, message):
    global settings

    if settings["testing"]:
        message = "Would have: " + message
    logger.log(level, message)

#===============================================================================
#= Main
#===============================================================================


"""
"""
def main(argv):
    global settings
    ssl._create_default_https_context = ssl._create_unverified_context

    # Command line arguments
    args = parse_args(argv)
    #logger.debug("Args: "+ json.dumps(args, indent=4, sort_keys=True))

    # Settings file parameters
    settings = load_settings(args["settings_filename"])
    logger.debug("Settings: " + json.dumps(settings, indent=4, sort_keys=True))

    if "email" in args:
        user = get_zoom_user(args["email"])
        logger.debug("Zoom User: " + str(user))
        if user is not None:
            user_id = user["id"]
            from_date = args["from"] if "from" in args else date(2020, 11, 30)
            now = datetime.now()
            yesterday = now - timedelta(days=1)
            to_date = args["to"] if "to" in args else date(yesterday.year, yesterday.month, yesterday.day)
            
            date_string=''
            if "from" in args:
                date_string="-"+str(from_date) + "-" + str(to_date)
            else:
                date_string="Through"+str(to_date)

            directory = "C:\\inetpub\\wwwroot\\ZoomMeeting\\" + args["email"] + "ZoomRecordings"+date_string
            #directory = "/srv/app_bconnsync_aux0/" + args["email"] + " Zoom recordings"+date_string
            try:
                if not os.path.exists(directory):
                    os.mkdir(directory)
                else:
                    logger.warning("Directory already exists: " + directory)
            except OSError as ose:
                logger.error(ose)
                logger.error("Creation of the directory failed: " + directory)
            
            meetings = get_user_recordings(user_id, from_date, to_date)
            #download_recordings(meetings, directory)
            multi_download_zoom_recordings(meetings, directory)
            print("rclone copy --progress --transfers 6 " + directory.replace(" ", "\ ") + " remote_google_drive:" + directory.replace(" ", "\ "))
            #os.system("rclone copy --progress --transfers 6 " + directory.replace(" ", "\ ") + " gdrive:" + directory.replace(" ", "\ "))
            os.system("rclone copy --progress --transfers 6 " + directory  + " gdrive:/" + "ZoomRecordings/" + args["email"])
            

if __name__ == "__main__":
    main(sys.argv[1:])

