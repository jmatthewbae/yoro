# YORO: Youth Online Risk Observatory

YORO is an open database of online behaviors. It collects public discussion about internet, phone and gaming use so that changes in how people talk about these habits can be measured over time.

This repository is the collector. It builds a local database through the official Reddit API. Scoring and public dataset releases will come in later versions.

## What it collects

| Community | Mode | What is kept |
|---|---|---|
| r/nosurf | full | every eligible post |
| r/digitalminimalism | full | every eligible post |
| r/StopGaming | full | every eligible post |
| r/internetaddiction | full | every eligible post |
| r/teenagers | filtered | only posts matching a topic term |

**Full** communities are about screen use as a whole, so every post is on topic.

**Filtered** communities are broad. Every new post is read, but only posts mentioning topics like screen time, doomscrolling, social media or specific apps are kept. The rest are counted and then discarded without being stored. The terms are in `yoro/config.py`, and each post records the terms it matched and a filter version so changes to the list stay traceable.

**Eligible** means the post is not deleted, removed, pinned, posted by moderators or AutoModerator or marked NSFW.

## What is stored and what is not

Stored per post: ID, community, time posted, title, body, whether it is a text post, link domain for link posts, post flair, score, upvote ratio, comment count, whether it was edited and matched topic terms.

**Never stored:** usernames, user flair (which often includes age or location), link URLs, permalinks, media or comments.

All data stays in `data/yoro.db` on the machine running the collector. The `data/` folder is excluded from git.

## How it works

### Collect (run hourly)

For each community the collector reads the "new" listing from newest to oldest and stops 6 hours before the newest post it saw last time. That overlap catches posts that appear late, such as ones approved from a moderation queue. Posts already stored are skipped.

Using "new" instead of "hot" or search means every post has an equal chance of being collected, not just popular ones.

**Gaps.** Reddit listings stop at about 1,000 posts. If a community gets more than that between runs, the run cannot reach back to where the last one ended and some posts are missed. The run is flagged as a gap, and `python run.py status` lists the affected periods.

**Daily counts.** The `daily_counts` table records how many posts were read, how many were eligible and how many were kept for each community and day. These are the denominators for rates, for example the share of r/teenagers posts that mention screen time. Any day that was only partly seen, such as the first day of the initial run or days inside a gap, is marked `complete = 0` and should be left out of rates.

### Sync (run daily)

Reddit requires that content deleted from Reddit is deleted here too. Sync rechecks every stored post once it has gone 24 hours without a check:

- Posts that were deleted by the author, removed by moderators or Reddit or no longer returned are **erased entirely**.
- Other posts get their current title, body, score and comment count.

Only aggregate counts of deletions are kept, in `sync_log`.

Sync can also erase post text after a set number of days (`TEXT_RETENTION_DAYS`). Reddit recommends deleting stored content within 48 hours. This is off for now because scoring has not been built and needs the text. Turn it on once scoring runs at collection time.

## Rules this collector follows

- Uses the official API with OAuth, not page scraping
- Sends an honest User-Agent in Reddit's required format: `script:yoro:v0.1.0 (by /u/<your username>)`
- Stays well within Reddit's limit of 100 requests per minute. PRAW handles rate limiting, and a normal hourly run uses a handful of requests.
- Reads only the communities listed above, in read-only mode
- Deletes content that was deleted from Reddit
- Stores no information that identifies users

See Reddit's [Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki), [Data API Terms](https://redditinc.com/policies/data-api-terms) and [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy). Anyone running this code needs their own approved Reddit app and is responsible for their own compliance.

## Setup

Requires Python 3.9 or newer.

1. Register a "script" app at https://www.reddit.com/prefs/apps. Reddit may require you to request API access first.
2. Install and configure:

```bash
pip install -r requirements.txt
cp .env.example .env   # add your client ID, secret and Reddit username
```

3. Run the first collection. This backfills up to about 1,000 recent posts per community.

```bash
python run.py collect
python run.py status
```

## Scheduling

The time series depends on regular runs. On macOS or Linux, add these with `crontab -e`. Replace `/path/to/yoro` with the repository folder and `/path/to/python3` with the output of `which python3` from the environment where you installed the requirements:

```
0 * * * *   cd "/path/to/yoro" && /path/to/python3 run.py collect >> data/cron.log 2>&1
30 4 * * *  cd "/path/to/yoro" && /path/to/python3 run.py sync >> data/cron.log 2>&1
```

On macOS, cron may need Full Disk Access (System Settings, Privacy & Security) to reach an external drive. If the computer is asleep when a run is due, the next run picks up where it left off. If the pause was long enough to overflow a busy community's listing, it is flagged as a gap.

Only one run happens at a time. A second run started while one is in progress exits immediately.

## Known limits

- **No history before the first run.** The API only shows about 1,000 recent posts per community, so the database starts at the first backfill.
- **The first backfill is biased.** Posts deleted before the first run are already gone and their scores have had longer to grow.
- **Late posts beyond 6 hours are missed.** A post that appears in the listing more than 6 hours after it was created, which is rare, will not be collected.
- **Posts only.** Comments are not collected yet.
- **Link and image posts have no body.** Only their titles are analyzed.
- **Stored data changes.** Deleted posts are erased, so counts from the posts table can drop over time. Use `daily_counts` for figures fixed at collection time.

## Database tables

| Table | Contents |
|---|---|
| `posts` | Collected posts |
| `runs` | One row per community per run: posts read, added, excluded by reason, gaps and errors |
| `daily_counts` | Posts read, eligible and kept per community per day, with a completeness flag |
| `sync_log` | Posts checked and erased per sync |

## Tests

```bash
pip install pytest
python -m pytest
```

The tests run the collector against a simulated Reddit to check incremental runs, gap detection, filtering, exclusions, error recovery and deletion.

## Roadmap

- Scoring for five signals: anger, anxiety, regret, addiction language and positive change, each kept as a separate score
- Comment collection
- Public dataset releases with aggregate tables only, archived with a DOI

## License

MIT. See `LICENSE`.

## Citation

See `CITATION.cff`.
