#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set syntax=python:

#TODO
# - lib newspaper3k to leech articles (https://pypi.org/project/newspaper3k/)

import argparse
import datetime
import feedparser
import tomllib
import tomli_w
import os
import pickle
import requests
import yt_dlp
import time
import re
from urllib.error import URLError
from weasyprint import HTML


# global scope variables
DB_FILE_NAME = None
LEECH_DIR = None
ATTR_LAST_LEECH = "last_leech"

def main():
    global LEECH_DIR, DB_FILE_NAME

    print(f"feedleech run - {datetime.datetime.now()}")

    # handle arguments
    argparser = argparse.ArgumentParser()
    argparser.add_argument("config_file", help="config file in TOML format")
    args = argparser.parse_args()
    config_file = args.config_file
    print(f"[+] config file: {config_file}")

    # initialize
    db_data = {}
    feed_data = {}
    print("[*] feedleech initializing...")

    # load config
    conf = config_load(config_file)
    if not conf:
        print(f"exit: invalid configuration file")
        return -1
    try:
        LEECH_DIR = conf["general"]["leech_dir"]
        feeds_urls = conf["feeds"]["feeds_url"]
    except KeyError as e:
        print(f"[!] exit: missing parameters into configuration file")
        return -1
    if not LEECH_DIR:
        print(f"[!] exit: no leech directory found in configuration file")
        return -1
    if not feeds_urls:
        print(f"[!] exit: no URLs found in configuration file {config_file}")
        return -1
    DB_FILE_NAME = str(config_file).replace(".toml", ".db")
    print(f"[+] leech directory: {LEECH_DIR}")
    print(f"[+] feed URLs: {feeds_urls}")

    # create leech directory (if doesn't already exists)
    os.makedirs(LEECH_DIR, exist_ok=True)

    # create / open db
    db_data, is_db_created = db_create_load()
    if not is_db_created:
        print(f"[+] db loaded: {db_data.keys()}")
        #init_last_entry(db_data)
        for k in db_data:
            last_entry = db_data[k][ATTR_LAST_LEECH]
            print(f"  {k}: last entry leeched = {last_entry}")
        #print(f"{db_data}")
    else:
        db_data = {}

    # inject configured urls into db (if not already there)
    init_feedurls_db(feeds_urls, db_data)

    # get feeds
    print("[*] getting feeds...")
    get_feeds(feeds_urls, feed_data)

    # leech new items
    leech_res = leech_new_entries(feed_data, db_data)
    if not leech_res:
        # do not update db
        # (in case of first time, we must leech all the feed,
        # so that later the diff will work correctly)
        return -1

    # update db
    db_update(db_data)

def config_load(config_filename):
    conf_handle = None
    if not str(config_filename).lower().endswith(".toml"):
        print(f"[!] {config_filename} doesn't end with .toml extension")
        return conf_handle
    with open(config_filename, "rb") as f:
        try:
            conf_handle = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            print(f"[!] {config_filename} doesn't seem to be in TOML format")
    return conf_handle

def db_create_load():
    db_content = None
    db_created = False
    try:
        db_handle = open(DB_FILE_NAME, "rb")
        db_content = tomllib.load(db_handle)
        db_handle.close()
        print("[+] db found, fetched data")
    except(FileNotFoundError):
        empty_data = {}
        db_handle = open(DB_FILE_NAME, "wb")
        tomli_w.dump(empty_data, db_handle)
        db_handle.close()
        db_created = True
        print("[+] db not found, created")
    return db_content, db_created

def get_feeds(urls: list, db_data):
    for u in urls:
        print(f"[*] getting content of {u}")
        content = get_feed(u)
        if content:
            db_data[u] = content

def get_feed(url: str):
    feed_content = feedparser.parse(url)
    if "status" in feed_content and feed_content["status"] == 200:
        return feed_content
    else:
        print(f"[!] Couldn't get feed {url}")
        return None

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
        print(f"[*] feed {u}, comparing db last leech {last_leech_db} with feed last leech {last_leech_feed}")
        if last_leech_db != last_leech_feed:
            print("[+] new shit found into feed")
            is_new_entries = True
            new_entries = get_new_entries(feed_data, u, last_leech_db)
            # leech new entries
            for n in new_entries:
                print("~LEECH TIME~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                leech_res, leeched_file = leech_entry(u, n)
                if leech_res:
                    update_entry_leech(feed_data, db_data, u, n, leeched_file)
                else:
                    print(f"[!] FAILED leeching {n['link']}")
                    leech_new_entries_res = False
                    break
            if(leech_new_entries_res):
                update_last_leech(feed_data, db_data, u, last_leech_feed)
        else:
            print("[+] nothing new found into feed")
    return leech_new_entries_res

def get_new_entries(feed_data, feed_url, last_leech_db):
    # seek last leech entry in new feed
    # if not found, all entries must be leeched
    entries_to_leech = []
    for e in feed_data[feed_url].entries:
        if e["id"] == last_leech_db:
            #print(f"last leech found: {e}")
            print(f"[+] last leech found into new feed {last_leech_db}")
            break
        else:
            entries_to_leech.append(e)
    return entries_to_leech

# Return (result, filename)
def leech_entry(url, entry):
    leech_res = False
    leeched_file = None
    link = entry["link"]
    article_pattern = re.compile(r"/[\w\-]+/?")
    print(f"[*] leeching {entry['title']} from {link}")
    if ("youtube.com" in link or
        "youtu.be" in link):
        leech_res, leeched_file = leech_entry_yt(link)
    elif (link.endswith(".pdf") or
          link.endswith(".docx")):
        leech_res, leeched_file = leech_entry_ddl(link)
    elif(link.endswith(".html") or
         link.endswith(".htm") or
         article_pattern.search(link)):
        leech_res, leeched_file = leech_entry_article(link, entry["id"])
    else:
        print(f"[!] no extractor found for {link}")
    return leech_res, leeched_file

# Return (result, filename)
def leech_entry_yt(url):
    #print(f"DEBUG: {LEECH_DIR}")
    print("[+] YOUTUBE extractor chosen")

    yt_dlp_res = True
    yt_paths = {}
    yt_paths["home"] = LEECH_DIR
    output_fullpath = None

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
            output_fullpath = ydl.prepare_filename(info_dict)

            # skip download if already downloaded
            if is_entry_already_leeched(output_fullpath):
                return True, output_fullpath

            # delay to avoid being blocked by youtube
            # if we already downloaded from a previous entry
            time.sleep(5)

            # download
            error_code = ydl.download(url)
            #print(f"yt_dlp error_code {error_code}")
            if error_code != 0:
                yt_dlp_res = False
        except yt_dlp.utils.YoutubeDLError as e:
            #print(f"yt_dlp error {e}")
            if "Video unavailable" in str(e):
                print(f"[!] Can't leech {url}: video unavailable: deleted / geo-fencing / ... => LEECH IGNORED")
                output_fullpath = "UNAVAILABLE"
            else:
                yt_dlp_res = False
        except Exception as e:
            #print(f"yt_dlp error {e}")
            yt_dlp_res = False
    return yt_dlp_res, output_fullpath

# Return (result, filename)
def leech_entry_ddl(url):
    print("[+] DDL extractor chosen")
    leech_res = True
    output_filename = None
    headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
               "Accept-Language": "fr,fr-FR;q=0.9,en-US;q=0.8,en;q=0.7",
               "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0",
               "DNT": "1"}

    if ("/" in url):
        file_in_url = url.rsplit("/", 1)[-1]
    else:
        return False

    response = requests.get(url, headers=headers)
    output_fullpath = f"{LEECH_DIR}/{file_in_url}"

    # skip download if already downloaded
    if is_entry_already_leeched(output_fullpath):
        return True, output_fullpath

    with open(output_fullpath, "wb") as f:
        f.write(response.content)

    return leech_res, output_fullpath

# Return (result, filename)
def leech_entry_article(url, entry_id):
    print("[+] ARTICLE (HTML TO PDF) extractor chosen")
    article_res = True
    output_filename = None
    article_data = []

    if str(entry_id) == "":
        return False, None
    entry_id_filenamecompat = entry_id.replace(":", "").replace("/", "-").replace(".", "-")

    output_filename = f"{entry_id_filenamecompat}.pdf"
    output_fullpath = f"{LEECH_DIR}/{output_filename}"

    # skip download if already downloaded
    if is_entry_already_leeched(output_fullpath):
        return True, output_filename

    try:
        HTML(url).write_pdf(output_fullpath)
    except URLError as e:
        print(f"[!] Error processing {url}: {str(e)}")
        article_res = False
    except Exception as e:
        print(f"[!] Error processing {url}: {str(e)}")
        article_res = False

    return article_res, output_filename

def is_entry_already_leeched(filepath):
    #print(f"DEBUG: is_entry_already_leeched {filepath}")
    res = False

    print(f"[*] checking if already leeched {filepath}")
    try:
        filestat = os.stat(filepath)
        #print(f"DEBUG: {filepath} found")
        if filestat.st_size > 0:
            res = True
            print(f"[!] already leeched {filepath}")
    except FileNotFoundError:
        res = False
        #print(f"DEBUG: {filepath} not found")

    return res

# update id of last leech
def update_last_leech(feed_data, db_data, url, entry_id):
    print(f"[+] last entry for {url}: {entry_id}")
    db_data[url][ATTR_LAST_LEECH] = entry_id

# trace id with filename
def update_entry_leech(feed_data, db_data, url, entry, filename):
    entry_id = entry["id"]
    print(f"[+] entry {entry_id} saved to file {filename}")
    db_data[url][entry_id] = filename

def db_update(db_data):
    #print(f"data to dump into db:\n{db_data}")
    with open(DB_FILE_NAME, "wb") as f:
        tomli_w.dump(db_data, f)
    f.close()
    print("[+] db saved")

if __name__ == "__main__":
    main()

