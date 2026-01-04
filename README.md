# feedleech

Auto-leech links from feeds.
Only ATOM 1.0 feeds tested (all feeds supported by lib `feedparser` should be ok).

Feeds URL must be filled into `config.toml` configuration file.

A `feedleech_db.toml` file will be created by the script to memorize the last items it downloaded.

## Pre-requisite

- python3
- dependencies installed from requirements.txt

## Tests

You can do some tests hosting a feed (like the ones in `examples` directory) with `python3 -m http.server 8080`.
Configure URL `http://127.0.0.1:8080/feed.atom` and switch the feed data with `ln -sf feednnn.atom feed.atom`.

