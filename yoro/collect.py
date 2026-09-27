"""
Incremental collection from each subreddit's "new" listing.

How a run works, per subreddit:
1. Look up the watermark: the newest post seen by the last successful run.
2. Read the "new" listing from newest to oldest, stopping OVERLAP_HOURS
   before the watermark. The overlap catches posts that show up late.
3. Skip deleted, removed, moderator, AutoModerator and NSFW posts. In
   filtered subreddits, also skip posts that match no topic term. Skipped
   posts are counted but never stored.
4. Store the rest. Posts already stored are left alone (sync refreshes them).
5. Record the run, including whether posts may have been missed (a gap).

Reddit listings stop at roughly 1,000 posts. If a run reaches the end of the
listing before getting back to the watermark, some posts in between were
never seen. The run is flagged with gap = 1 so that period can be excluded.
"""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

import prawcore

from . import config, rules

INSERT = """
INSERT OR IGNORE INTO posts (
    post_id, subreddit, created_utc, title, selftext, is_self, domain,
    link_flair, score, upvote_ratio, num_comments, edited, matched_terms,
    filter_version, first_seen_utc, last_synced_utc
) VALUES (
    :post_id, :subreddit, :created_utc, :title, :selftext, :is_self, :domain,
    :link_flair, :score, :upvote_ratio, :num_comments, :edited, :matched_terms,
    :filter_version, :now, :now
)
"""

UPSERT_DAY = """
INSERT INTO daily_counts (subreddit, day, scanned, eligible, kept, complete)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (subreddit, day) DO UPDATE SET
    scanned  = scanned  + excluded.scanned,
    eligible = eligible + excluded.eligible,
    kept     = kept     + excluded.kept,
    complete = MIN(complete, excluded.complete)
"""


def utc_day(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def watermark(conn, subreddit: str) -> int | None:
    row = conn.execute(
        "SELECT MAX(newest_scanned_utc) FROM runs WHERE subreddit = ? AND status = 'ok'",
        (subreddit,)).fetchone()
    return row[0]


def to_row(post, subreddit: str, matched: list[str], filtered: bool, now: int) -> dict:
    # Deliberately not stored: author, author flair (often includes age or
    # location), link URL, permalink, media and comments.
    return {
        "post_id": post.id,
        "subreddit": subreddit,
        "created_utc": int(post.created_utc),
        "title": post.title,
        "selftext": post.selftext or "",
        "is_self": int(bool(post.is_self)),
        "domain": None if post.is_self else post.domain,
        "link_flair": post.link_flair_text,
        "score": post.score,
        "upvote_ratio": post.upvote_ratio,
        "num_comments": post.num_comments,
        "edited": int(bool(post.edited)),
        "matched_terms": "|".join(matched) or None,
        "filter_version": rules.FILTER_VERSION if filtered else None,
        "now": now,
    }


def collect_subreddit(reddit, conn, subreddit: str, filtered: bool) -> dict:
    now = int(time.time())
    wm = watermark(conn, subreddit)
    stop_at = wm - config.OVERLAP_HOURS * 3600 if wm is not None else None
    run_id = conn.execute(
        "INSERT INTO runs (subreddit, mode, filter_version, started_utc, status,"
        " watermark_utc, backfill) VALUES (?, ?, ?, ?, 'running', ?, ?)",
        (subreddit, "filtered" if filtered else "full",
         rules.FILTER_VERSION if filtered else None, now, wm, int(wm is None)),
    ).lastrowid
    conn.commit()

    scanned = new = 0
    excluded = Counter()
    days = defaultdict(lambda: [0, 0, 0])  # day -> [scanned, eligible, kept]
    oldest = newest = None
    reached_stop = False

    try:
        for post in reddit.subreddit(subreddit).new(limit=None):
            created = int(post.created_utc)
            if stop_at is not None and created < stop_at:
                reached_stop = True
                break
            scanned += 1
            oldest = created if oldest is None else min(oldest, created)
            newest = created if newest is None else max(newest, created)
            # Posts at or before the watermark were counted by an earlier run.
            counts = days[utc_day(created)] if wm is None or created > wm else [0, 0, 0]
            counts[0] += 1

            reason = rules.exclusion_reason(post)
            if reason:
                excluded[reason] += 1
                continue
            counts[1] += 1

            matched = rules.matched_terms(post)
            if filtered and not matched:
                excluded["off_topic"] += 1
                continue
            counts[2] += 1

            new += conn.execute(INSERT, to_row(post, subreddit, matched, filtered, now)).rowcount

    except prawcore.exceptions.PrawcoreException as e:
        conn.rollback()  # the next run starts again from the same watermark
        conn.execute(
            "UPDATE runs SET status = 'error', error = ?, finished_utc = ? WHERE run_id = ?",
            (f"{type(e).__name__}: {e}", int(time.time()), run_id))
        conn.commit()
        return {"subreddit": subreddit, "status": "error", "error": f"{type(e).__name__}: {e}"}

    exhausted = not reached_stop
    gap = int(wm is not None and exhausted and oldest is not None and oldest > wm)
    # Days that were only partly seen are marked incomplete, so rates are
    # never computed from them. On a first run that is the oldest day
    # reached. After a gap it is every day from the watermark to the oldest
    # post this run reached.
    incomplete = set()
    if exhausted and oldest is not None and wm is None:
        incomplete.add(utc_day(oldest))
    if gap:
        d, end = date.fromisoformat(utc_day(wm)), date.fromisoformat(utc_day(oldest))
        while d <= end:
            incomplete.add(d.isoformat())
            d += timedelta(days=1)

    for day in set(days) | incomplete:
        s, e, k = days.get(day, (0, 0, 0))
        conn.execute(UPSERT_DAY, (subreddit, day, s, e, k, int(day not in incomplete)))
    conn.execute(
        "UPDATE runs SET status = 'ok', finished_utc = ?, oldest_scanned_utc = ?,"
        " newest_scanned_utc = ?, scanned = ?, new_posts = ?, excluded = ?, gap = ?"
        " WHERE run_id = ?",
        (int(time.time()), oldest, newest, scanned, new,
         json.dumps(dict(excluded)), gap, run_id))
    conn.commit()
    return {"subreddit": subreddit, "status": "ok", "scanned": scanned,
            "new": new, "gap": gap, "backfill": wm is None}


def run(reddit, conn) -> bool:
    targets = [(s, False) for s in config.FULL_SUBREDDITS]
    targets += [(s, True) for s in config.FILTERED_SUBREDDITS]
    ok = True
    for subreddit, filtered in targets:
        r = collect_subreddit(reddit, conn, subreddit, filtered)
        if r["status"] == "error":
            ok = False
            print(f"r/{subreddit}: ERROR {r['error']}")
            continue
        notes = [n for n, on in (("backfill", r["backfill"]), ("GAP", r["gap"])) if on]
        print(f"r/{subreddit}: scanned {r['scanned']}, new {r['new']}"
              + (f" ({', '.join(notes)})" if notes else ""))
    return ok
