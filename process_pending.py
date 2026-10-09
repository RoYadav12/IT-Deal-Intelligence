"""Process every row with Status = 'Pending': fetch the article with Serper,
extract structured fields (LLM if keyed, otherwise heuristic), and write
results back to SQLite."""

import time

import config
import db
import extraction


def run(creds, verbose=True, progress_callback=None, conn=None, limit=None):
    """Process currently-pending rows (up to `limit`, default
    config.MAX_PENDING_PER_RUN; 0 = unlimited).

    Returns (completed_count, batch_ids, stats). stats has:
      "found"         - how many rows this run attempted
      "failed"        - how many errored out
      "sample_errors" - a few example error messages
      "remaining"     - pending rows left over because of the cap
      "fatal"         - error text if the run was aborted (bad API key /
                        no credits), else None. Aborted rows stay Pending.
    """
    problems = creds.problems()
    if problems:
        raise RuntimeError("Cannot extract: " + "; ".join(problems) + ".")
    conn = conn or db.get_connection()
    limit = config.MAX_PENDING_PER_RUN if limit is None else limit
    total_pending = db.count_by_status(conn)["pending"]
    pending = db.get_pending_deals(conn, limit=limit)
    total = len(pending)
    batch_ids = []

    if verbose:
        print(f"\nFound {total_pending} pending URL(s); processing {total}\n")

    completed = 0
    failed = 0
    sample_errors = []
    fatal = None
    for done, (deal_id, url) in enumerate(pending, start=1):
        if verbose:
            print(f"Processing: {url}")
        try:
            fields = extraction.process_url(url, creds)
            db.update_deal(conn, deal_id, fields)
            batch_ids.append(deal_id)
            completed += 1
            if verbose:
                print("  Completed successfully\n")
        except extraction.FatalAPIError as exc:
            # Bad key / no credit: every remaining URL would fail the same
            # way. Leave this row Pending and stop.
            fatal = str(exc)
            if verbose:
                print(f"  Aborting run: {exc}\n")
            break
        except Exception as exc:
            db.mark_failed(conn, deal_id, str(exc))
            batch_ids.append(deal_id)
            failed += 1
            if len(sample_errors) < 3:
                sample_errors.append(str(exc))
            if verbose:
                print(f"  Error: {exc}\n")

        if progress_callback:
            progress_callback(done, total, url)

        time.sleep(config.RATE_LIMIT_SLEEP_SECONDS)

    remaining = db.count_by_status(conn)["pending"]
    if verbose:
        print(f"Done: {completed}/{total} succeeded, {failed} failed, "
              f"{remaining} still pending.")

    stats = {
        "found": total,
        "failed": failed,
        "sample_errors": sample_errors,
        "remaining": remaining,
        "fatal": fatal,
    }
    return completed, batch_ids, stats


if __name__ == "__main__":
    run(config.credentials_from_env())
