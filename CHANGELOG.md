# Changelog

## 0.1.0 (2026-09-27)

First public release: the collector.

- Collection through the official Reddit API with an honest User-Agent
- Incremental runs from each community's "new" listing with a 6 hour overlap
- Gap detection when a listing overflows between runs
- Daily counts of posts read, eligible and kept, with completeness flags
- Topic filtering for broad communities, with a filter version on every post
- Daily sync that erases posts deleted from Reddit and refreshes scores
- No usernames, user flair, links or permalinks stored
