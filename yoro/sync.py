"""
Recheck stored posts against Reddit.

Reddit requires that content deleted from Reddit is deleted here too. Every
stored post is rechecked once it is SYNC_AFTER_HOURS old since its last
check. Posts that were deleted, removed or no longer returned are erased
entirely. Others get their current title, body, score and comment count.
Only aggregate counts of deletions are kept, in sync_log.
"""
from __future__ import annotations

import time
from collections import defaultdict

import prawcore

from . import config, rules

BATCH = 100  # maximum items per /api/info request


def run(reddit, conn, now: int | None = None) -> bool:
    now = now or int(time.time())
    due = conn.execute(
        "SELECT post_id, subreddit FROM posts WHERE last_synced_utc <= ?"
        " ORDER BY last_synced_utc",
        (now - config.SYNC_AFTER_HOURS * 3600,)).fetchall()
    stats = defaultdict(lambda: {"checked": 0, "deleted": 0, "removed": 0, "missing": 0})
    ok = True

    for i in range(0, len(due), BATCH):
        batch = due[i:i + BATCH]
        try:
            found = {p.id: p for p in reddit.info(fullnames=[f"t3_{r['post_id']}" for r in batch])}
        except prawcore.exceptions.PrawcoreException as e:
            print(f"Sync stopped: {type(e).__name__}: {e}. Progress so far is saved.")
            ok = False
            break
        for row in batch:
            post = found.get(row["post_id"])
            reason = "missing" if post is None else rules.is_gone(post)
            stats[row["subreddit"]]["checked"] += 1
            if reason:
                conn.execute("DELETE FROM posts WHERE post_id = ?", (row["post_id"],))
                stats[row["subreddit"]][reason] += 1
            else:
                conn.execute(
                    "UPDATE posts SET"
                    " title = CASE WHEN text_purged THEN NULL ELSE ? END,"
                    " selftext = CASE WHEN text_purged THEN NULL ELSE ? END,"
                    " score = ?, upvote_ratio = ?, num_comments = ?, edited = ?,"
                    " last_synced_utc = ? WHERE post_id = ?",
                    (post.title, post.selftext or "", post.score, post.upvote_ratio,
                     post.num_comments, int(bool(post.edited)), now, row["post_id"]))
        conn.commit()

    purged = 0
    if config.TEXT_RETENTION_DAYS is not None:
        purged = conn.execute(
            "UPDATE posts SET title = NULL, selftext = NULL, text_purged = 1"
            " WHERE text_purged = 0 AND created_utc < ?",
            (now - config.TEXT_RETENTION_DAYS * 86400,)).rowcount

    for sub, s in stats.items():
        conn.execute("INSERT INTO sync_log VALUES (?, ?, ?, ?, ?, ?)",
                     (now, sub, s["checked"], s["deleted"], s["removed"], s["missing"]))
    conn.commit()

    total = {k: sum(s[k] for s in stats.values()) for k in ("checked", "deleted", "removed", "missing")}
    print(f"Checked {total['checked']} posts. Erased {total['deleted']} deleted,"
          f" {total['removed']} removed and {total['missing']} missing."
          + (f" Purged text from {purged}." if purged else ""))
    return ok
