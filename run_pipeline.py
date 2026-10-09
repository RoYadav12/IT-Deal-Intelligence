"""Headless run (no web UI): read RSS feeds, then extract pending URLs.
Keys come from environment variables or a .env file (see .env.example).
Usage: python run_pipeline.py"""

import config
import db
import process_pending
import rss_ingest

if __name__ == "__main__":
    creds = config.credentials_from_env()
    problems = creds.problems()
    if problems:
        raise SystemExit("Cannot run: " + "; ".join(problems) + ". See .env.example.")
    conn = db.get_connection()
    added, feed_stats = rss_ingest.run(conn=conn)
    print(f"Feeds OK: {feed_stats['feeds_ok']}, failed: {feed_stats['feeds_failed']}")
    completed, _, stats = process_pending.run(creds, conn=conn)
    if stats["fatal"]:
        raise SystemExit(f"Aborted: {stats['fatal']}")
