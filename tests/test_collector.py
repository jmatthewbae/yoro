"""Tests against a simulated Reddit. Run with: python -m pytest"""
import itertools
import json
import time
from types import SimpleNamespace

import prawcore
import pytest

from yoro import collect, config, db, rules, sync

_ids = itertools.count(1)


def post(minutes_ago, title="post", text="body", author="someone", now=None, **kw):
    now = now or int(time.time())
    base = dict(id=f"p{next(_ids)}", created_utc=now - minutes_ago * 60, title=title,
                selftext=text, author=author, stickied=False, distinguished=None,
                over_18=False, removed_by_category=None, is_self=True, domain="self.x",
                link_flair_text=None, score=1, upvote_ratio=1.0, num_comments=0, edited=False)
    base.update(kw)
    return SimpleNamespace(**base)


class FakeSubreddit:
    def __init__(self, reddit, name):
        self.reddit, self.name = reddit, name

    def new(self, limit=None):
        posts = sorted(self.reddit.posts.get(self.name, []), key=lambda p: -p.created_utc)
        for i, p in enumerate(posts[: self.reddit.cap]):
            if self.reddit.fail_after is not None and i >= self.reddit.fail_after:
                raise prawcore.exceptions.ServerError(SimpleNamespace(status_code=500))
            yield p


class FakeReddit:
    def __init__(self, cap=1000):
        self.posts, self.cap, self.fail_after, self.live = {}, cap, None, {}

    def add(self, sub, *ps):
        self.posts.setdefault(sub, []).extend(ps)
        for p in ps:
            self.live[p.id] = p

    def subreddit(self, name):
        return FakeSubreddit(self, name)

    def info(self, fullnames):
        return [self.live[f[3:]] for f in fullnames if f[3:] in self.live]


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "t.db")


def stored(conn):
    return {r[0] for r in conn.execute("SELECT post_id FROM posts")}


def last_run(conn, sub):
    return conn.execute("SELECT * FROM runs WHERE subreddit = ? ORDER BY run_id DESC",
                        (sub,)).fetchone()


def test_no_author_column(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(posts)")}
    assert not {"author", "author_flair", "url", "permalink"} & cols


def test_user_agent_format():
    from yoro.reddit import user_agent
    assert user_agent("matt") == "script:yoro:v0.1.0 (by /u/matt)"


def test_exclusions(conn):
    r = FakeReddit()
    keep = post(1)
    r.add("s", keep, post(2, stickied=True), post(3, distinguished="moderator"),
          post(4, author="AutoModerator"), post(5, over_18=True),
          post(6, author=None, text="[deleted]"), post(7, text="[removed]"),
          post(8, removed_by_category="moderator"))
    collect.collect_subreddit(r, conn, "s", filtered=False)
    assert stored(conn) == {keep.id}
    ex = json.loads(last_run(conn, "s")["excluded"])
    assert ex == {"moderator": 2, "automod": 1, "nsfw": 1, "deleted": 1, "removed": 2}


def test_incremental_no_duplicates(conn):
    r = FakeReddit()
    r.add("s", *[post(m) for m in range(60, 0, -10)])
    collect.collect_subreddit(r, conn, "s", filtered=False)
    assert last_run(conn, "s")["backfill"] == 1
    r.add("s", post(0.5), post(0.2))
    res = collect.collect_subreddit(r, conn, "s", filtered=False)
    assert res["new"] == 2 and res["gap"] == 0
    assert len(stored(conn)) == 8
    run = last_run(conn, "s")
    assert run["scanned"] == 8  # overlap window rescans older posts


def test_daily_counts_not_double_counted(conn):
    now = int(time.time())
    r = FakeReddit()
    r.add("s", *[post(m, now=now) for m in (3, 2)])
    collect.collect_subreddit(r, conn, "s", filtered=False)
    r.add("s", post(1, now=now))
    collect.collect_subreddit(r, conn, "s", filtered=False)
    total, complete = conn.execute("SELECT SUM(scanned), MIN(complete) FROM daily_counts").fetchone()
    assert total == 3
    assert complete == 0  # first day of a backfill is never trusted as complete


def test_gap_detected_when_listing_runs_out(conn):
    r = FakeReddit(cap=5)
    r.add("s", *[post(m) for m in (600, 590)])
    collect.collect_subreddit(r, conn, "s", filtered=False)
    # 10 new posts arrive, but the listing only shows 5
    r.add("s", *[post(m) for m in range(20, 0, -2)])
    res = collect.collect_subreddit(r, conn, "s", filtered=False)
    assert res["gap"] == 1
    flagged = conn.execute("SELECT COUNT(*) FROM daily_counts WHERE complete = 0").fetchone()[0]
    assert flagged >= 1


def test_gap_marks_every_day_in_between(conn):
    now = int(time.time())
    r = FakeReddit(cap=3)
    r.add("s", post(60 * 24 * 5, now=now))           # 5 days ago
    collect.collect_subreddit(r, conn, "s", filtered=False)
    r.add("s", *[post(m, now=now) for m in (3, 2, 1, 0.5)])  # today, more than the cap
    collect.collect_subreddit(r, conn, "s", filtered=False)
    days = conn.execute("SELECT COUNT(*) FROM daily_counts WHERE complete = 0").fetchone()[0]
    assert days >= 5


def test_no_false_gap_when_overlap_is_truncated(conn):
    # Busy subreddit: overlap window alone exceeds the listing cap,
    # but the run still reaches back past the watermark.
    r = FakeReddit(cap=5)
    r.add("s", *[post(m) for m in range(100, 60, -5)])
    collect.collect_subreddit(r, conn, "s", filtered=False)
    r.add("s", post(1), post(0.5))
    res = collect.collect_subreddit(r, conn, "s", filtered=False)
    assert res["gap"] == 0 and res["new"] == 2


def test_filtered_subreddit(conn):
    r = FakeReddit()
    hit = post(1, title="I can't stop scrolling TikTok")
    miss = post(2, title="Rate my outfit")
    r.add("teenagers", hit, miss)
    collect.collect_subreddit(r, conn, "teenagers", filtered=True)
    assert stored(conn) == {hit.id}
    row = conn.execute("SELECT matched_terms, filter_version FROM posts").fetchone()
    assert "tik ?tok" in row[0] and row[1] == rules.FILTER_VERSION
    s, e, k = conn.execute("SELECT SUM(scanned), SUM(eligible), SUM(kept) FROM daily_counts").fetchone()
    assert (s, e, k) == (2, 2, 1)


def test_error_rolls_back_and_keeps_watermark(conn):
    r = FakeReddit()
    r.add("s", *[post(m) for m in (30, 20)])
    collect.collect_subreddit(r, conn, "s", filtered=False)
    wm = collect.watermark(conn, "s")
    r.add("s", post(5), post(4), post(3))
    r.fail_after = 1
    res = collect.collect_subreddit(r, conn, "s", filtered=False)
    assert res["status"] == "error"
    assert collect.watermark(conn, "s") == wm
    assert len(stored(conn)) == 2
    r.fail_after = None
    assert collect.collect_subreddit(r, conn, "s", filtered=False)["new"] == 3


def test_sync_erases_deleted_and_updates_live(conn):
    r = FakeReddit()
    a, b, c, d = post(4), post(3), post(2), post(1)
    r.add("s", a, b, c, d)
    collect.collect_subreddit(r, conn, "s", filtered=False)
    b.author, b.selftext = None, "[deleted]"
    c.selftext = "[removed]"
    del r.live[d.id]
    a.score, a.selftext = 99, "edited body"
    later = int(time.time()) + config.SYNC_AFTER_HOURS * 3600 + 1
    sync.run(r, conn, now=later)
    assert stored(conn) == {a.id}
    row = conn.execute("SELECT score, selftext FROM posts").fetchone()
    assert row["score"] == 99 and row["selftext"] == "edited body"
    log = conn.execute("SELECT deleted, removed, missing FROM sync_log").fetchone()
    assert tuple(log) == (1, 1, 1)


def test_retention_purges_text(conn, monkeypatch):
    r = FakeReddit()
    r.add("s", post(60 * 24 * 3))
    collect.collect_subreddit(r, conn, "s", filtered=False)
    monkeypatch.setattr(config, "TEXT_RETENTION_DAYS", 2)
    later = int(time.time()) + config.SYNC_AFTER_HOURS * 3600 + 1
    sync.run(r, conn, now=later)
    row = conn.execute("SELECT title, selftext, text_purged FROM posts").fetchone()
    assert row["title"] is None and row["selftext"] is None and row["text_purged"] == 1
