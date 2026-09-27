"""Summary of what has been collected and any coverage gaps."""
from datetime import datetime, timezone


def fmt(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if ts else "-"


def run(conn) -> bool:
    print(f"{'subreddit':<20}{'posts':>7}  {'earliest':<17}{'latest':<17}{'last run':<17}{'gaps':>5}")
    subs = conn.execute("SELECT DISTINCT subreddit FROM runs ORDER BY subreddit").fetchall()
    for (sub,) in subs:
        p = conn.execute("SELECT COUNT(*), MIN(created_utc), MAX(created_utc) FROM posts"
                         " WHERE subreddit = ?", (sub,)).fetchone()
        r = conn.execute("SELECT MAX(finished_utc), SUM(gap) FROM runs"
                         " WHERE subreddit = ? AND status = 'ok'", (sub,)).fetchone()
        print(f"{sub:<20}{p[0]:>7}  {fmt(p[1]):<17}{fmt(p[2]):<17}{fmt(r[0]):<17}{r[1] or 0:>5}")

    gaps = conn.execute("SELECT subreddit, watermark_utc, oldest_scanned_utc FROM runs"
                        " WHERE gap = 1 ORDER BY started_utc").fetchall()
    if gaps:
        print("\nPeriods with possible missing posts (UTC):")
        for g in gaps:
            print(f"  r/{g['subreddit']}: {fmt(g['watermark_utc'])} to {fmt(g['oldest_scanned_utc'])}")

    errors = conn.execute("SELECT subreddit, error, started_utc FROM runs WHERE status = 'error'"
                          " ORDER BY started_utc DESC LIMIT 5").fetchall()
    if errors:
        print("\nRecent errors:")
        for e in errors:
            print(f"  {fmt(e['started_utc'])} r/{e['subreddit']}: {e['error']}")
    last_sync = conn.execute("SELECT MAX(sync_utc) FROM sync_log").fetchone()[0]
    print(f"\nLast sync: {fmt(last_sync)}")
    return True
