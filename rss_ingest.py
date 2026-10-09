"""Pull new URLs from the configured RSS feeds into the deals table as
'Pending' rows. Safe to re-run - duplicates are skipped via the URL
UNIQUE constraint.

Feeds are fetched concurrently, each with a strict timeout
(config.FEED_FETCH_TIMEOUT_SECONDS). This is what prevents a single slow
or unresponsive feed from stalling the whole run - it's timed out, logged,
and skipped instead of blocking everything behind it."""

import concurrent.futures

import feedparser
import requests

import config
import db


def _fetch_feed(feed_url):
    """Fetch and parse a single feed. Returns (feed_url, entries, error).

    error is None on success, or the exception on failure (timeout, DNS
    failure, HTTP error, etc.) - callers decide how to log/report it.
    """
    try:
        response = requests.get(
            feed_url,
            timeout=config.FEED_FETCH_TIMEOUT_SECONDS,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; ITDealIntelligenceBot/1.0)"
            },
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        return feed_url, parsed.entries, None
    except Exception as exc:
        return feed_url, [], exc


def run(feeds=None, verbose=True, progress_callback=None, conn=None):
    """Fetch every configured feed (in parallel) and insert any new URLs
    as Pending rows.

    conn: an existing db connection to reuse (recommended when calling
    this alongside other pipeline steps in the same run, so you don't end
    up with several separate connections open to the same file at once).
    If not given, a new one is opened.

    progress_callback, if given, is called as progress_callback(done,
    total, feed_url) after each feed finishes (success or failure) - this
    lets a UI show live progress instead of one long spinner.

    Returns (added, stats) where stats has "feeds_ok", "feeds_failed", and
    "feed_errors" (a few sample (feed_url, error) pairs) - this is what
    lets a caller tell "every feed failed to load" apart from "feeds
    loaded fine, there was just nothing new in them".
    """
    feeds = feeds or config.RSS_FEEDS
    conn = conn or db.get_connection()
    added = 0
    total = len(feeds)
    done = 0
    feeds_ok = 0
    feeds_failed = 0
    feed_errors = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=config.MAX_FEED_WORKERS
    ) as executor:
        futures = {
            executor.submit(_fetch_feed, feed_url): feed_url for feed_url in feeds
        }

        for future in concurrent.futures.as_completed(futures):
            feed_url, entries, error = future.result()
            done += 1

            if error is not None:
                feeds_failed += 1
                if len(feed_errors) < 3:
                    feed_errors.append((feed_url, str(error)))
                if verbose:
                    print(f"  Skipped (failed to load): {feed_url} - {error}")
            else:
                feeds_ok += 1
                if verbose:
                    print(f"\nReading: {feed_url} ({len(entries)} entries)")
                for entry in entries:
                    url = getattr(entry, "link", None)
                    if not url or not url.startswith(("http://", "https://")):
                        continue
                    if db.insert_pending_url(conn, url):
                        added += 1
                        if verbose:
                            print(f"  Added: {url}")

            if progress_callback:
                progress_callback(done, total, feed_url)

    if verbose:
        print(f"\nRSS ingestion complete. {added} new URL(s) added.")

    stats = {
        "feeds_ok": feeds_ok,
        "feeds_failed": feeds_failed,
        "feed_errors": feed_errors,
    }
    return added, stats


if __name__ == "__main__":
    run()
