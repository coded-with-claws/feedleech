# vim: set syntax=python:

#TODO
# - lib newspaper3k to leech articles (https://pypi.org/project/newspaper3k/)

import feedparser
import tomllib
import tomli_w
import os
import pickle
import yt_dlp

# global scope variables
CONFIG_FILE_NAME = "config.toml"
DB_FILE_NAME = "feedleech_db.toml"
LEECH_DIR = "leech"
ATTR_LAST_LEECH = "last_leech"

def main():
    # initialize
    db_data = {}
    feed_data = {}
    print("feedleech initializing...")
    # load config
    conf = config_load()
    LEECH_DIR = conf["general"]["leech_dir"]
    feeds_urls = conf["feeds"]["feeds_url"]
    if not feeds_urls:
        print(f"no URLs found in configuration file {CONFIG_FILE_NAME}")
    print(f"feed URLs: {feeds_urls}")
    # create leech directory (if doesn't already exists)
    os.makedirs(LEECH_DIR, exist_ok=True)
    # create / open db
    db_data, is_db_created = db_create_load()
    if not is_db_created:
        print(f"db loaded: {db_data.keys()}")
        #init_last_entry(db_data)
        for k in db_data:
            last_entry = db_data[k][ATTR_LAST_LEECH]
            print(f"{k}: last entry leeched = {last_entry}")
        #print(f"{db_data}")
    else:
        db_data = {}
    # inject configured urls into db (if not already there)
    init_feedurls_db(feeds_urls, db_data)
    # get feeds
    get_feeds(feeds_urls, feed_data)
    # leech new items
    leech_res = leech_new_entries(feed_data, db_data)
    if not leech_res:
        # do not update db
        return -1
    # update db
    db_update(db_data)

def config_load():
    conf_handle = None
    with open(CONFIG_FILE_NAME, "rb") as f:
        conf_handle = tomllib.load(f)
    return conf_handle

def db_create_load():
    db_content = None
    db_created = False
    try:
        db_handle = open(DB_FILE_NAME, "rb")
        db_content = tomllib.load(db_handle)
        db_handle.close()
        print("db found, fetched data")
    except(FileNotFoundError):
        empty_data = {}
        db_handle = open(DB_FILE_NAME, "wb")
        tomli_w.dump(empty_data, db_handle)
        db_handle.close()
        db_created = True
        print("db not found, created")
    return db_content, db_created

def get_feeds(urls: list, db_data):
    for u in urls:
        print(f"getting content of {u}")
        content = get_feed(u)
        if content:
            db_data[u] = content

def get_feed(url: str):
    feed_content = feedparser.parse(url)
    if feed_content["status"] == 200:
        return feed_content
    else:
        return None

#def init_last_entry(db_data):
#    for k in db_data:
#        try:
#            last_entry = db_data[k][ATTR_LAST_LEECH]
#        except(KeyError):
#            db_data[k][ATTR_LAST_LEECH] = None

def init_feedurls_db(urls, db_data):
    for u in urls:
        try:
            db_data[u]
        except(KeyError):
            db_data[u] = {}
            db_data[u][ATTR_LAST_LEECH] = None

# leech new entries and update last leech
def leech_new_entries(feed_data, db_data):
    leech_new_entries_res = True
    is_new_entries = False
    for u in db_data:
        # ignore urls being in database but not into configured feed urls
        if u not in feed_data:
            continue
        last_leech_db = db_data[u][ATTR_LAST_LEECH]
        last_leech_feed = feed_data[u].entries[0]["id"]
        print(f"feed {u}, comparing db last leech {last_leech_db} with feed last leech {last_leech_feed}")
        if last_leech_db != last_leech_feed:
            print("new shit found into feed")
            is_new_entries = True
            new_entries = get_new_entries(feed_data, u, last_leech_db)
            # leech new entries
            for n in new_entries:
                leech_res, leeched_file = leech_entry(u, n)
                if leech_res:
                    update_last_leech(feed_data, db_data, u, n, leeched_file)
                else:
                    print(f"FAILED leeching {n['link']}")
                    leech_new_entries_res = False
                    break
        else:
            print("nothing new found into feed")
    return leech_new_entries_res

def get_new_entries(feed_data, feed_url, last_leech_db):
    # seek last leech entry in new feed
    # if not found, all entries must be leeched
    entries_to_leech = []
    for e in feed_data[feed_url].entries:
        if e["id"] == last_leech_db:
            #print(f"last leech found: {e}")
            print(f"last leech found into new feed {last_leech_db}")
            break
        else:
            entries_to_leech.append(e)
    return entries_to_leech

# Return (result, filename)
def leech_entry(url, entry):
    leech_res = False
    link = entry["link"]
    print(f"leeching {entry['title']} {link}")
    if ("youtube.com" in link or
        "youtu.be" in link):
        leech_res, leeched_file = leech_entry_yt(link)
    else:
        print(f"no extractor found for {link}")
    return leech_res, leeched_file

# Return (result, filename)
def leech_entry_yt(url):
    yt_dlp_res = True
    yt_paths = {}
    yt_paths["home"] = LEECH_DIR

    ydl_opts = {
        'paths': yt_paths,
        #'format': 'm4a/bestaudio/best',
        'format': 'bestvideo+bestaudio/best',
        #'merge_output_format': 'mp4',
        'writethumbnail': True,
        'writeinfojson': True,
        # See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
        #'postprocessors': [{  # Extract audio using ffmpeg
        #    'key': 'FFmpegExtractAudio',
        #    'preferredcodec': 'm4a',
        #}]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # get filename
            info_dict = ydl.extract_info(url, download=False)
            output_filename = ydl.prepare_filename(info_dict)

            # download
            error_code = ydl.download(url)
            #print(f"yt_dlp error_code {error_code}")
            if error_code != 0:
                yt_dlp_res = False
        except yt_dlp.utils.YoutubeDLError as e:
            #print(f"yt_dlp error {e}")
            yt_dlp_res = False
        except Exception as e:
            #print(f"yt_dlp error {e}")
            yt_dlp_res = False
    return yt_dlp_res, output_filename

def update_last_leech(feed_data, db_data, url, entry, filename):
    # update id of last leech
    entry_id = entry["id"]
    print(f"last entry for {url}: {entry_id}")
    db_data[url][ATTR_LAST_LEECH] = entry_id
    # trace id with filename
    db_data[url][entry_id] = filename

def db_update(db_data):
    #print(f"data to dump into db:\n{db_data}")
    with open(DB_FILE_NAME, "wb") as f:
        tomli_w.dump(db_data, f)
    f.close()
    print("db saved")

if __name__ == "__main__":
    main()

