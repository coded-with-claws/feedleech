# feedleech

Auto-leech links from feeds.
Only ATOM 1.0 feeds tested (all feeds supported by lib `feedparser` should be ok).

Feeds URLs must be filled into a configuration file in TOML format (see `examples/config.toml`).
This configuration file must be given as argument to `feedleech.py`.

A `.db` file will be created by the script to memorize the last items it downloaded. This `.db` file will be named according to the configuration filename: `.db` instead of `.toml`.

## Pre-requisite

- python3
- dependencies installed from requirements.txt

## Tests

You can do some tests hosting a feed (like the ones in `examples` directory) with `python3 -m http.server 8080`.
Configure URL `http://127.0.0.1:8080/feed.atom` and switch the feed data with `ln -sf feednnn.atom feed.atom`.

