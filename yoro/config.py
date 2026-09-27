"""Collection settings. Changing TOPIC_TERMS changes the filter version."""
from pathlib import Path

DB_PATH = Path("data/yoro.db")
LOCK_PATH = Path("data/.lock")

# Communities where the whole community is on topic. Every eligible post is kept.
FULL_SUBREDDITS = [
    "nosurf",
    "digitalminimalism",
    "StopGaming",
    "internetaddiction",
]

# Broad communities. Every new post is scanned, only posts matching
# TOPIC_TERMS are kept and the rest are discarded without being stored.
FILTERED_SUBREDDITS = [
    "teenagers",
]

# Regular expressions matched case-insensitively against title and body,
# with word boundaries on both ends.
TOPIC_TERMS = [
    r"screen ?time",
    r"phone addict(ion|ed)?",
    r"addicted to (my|the|his|her) phone",
    r"social media",
    r"doom ?scroll(ing)?",
    r"can'?t stop scrolling",
    r"tik ?tok",
    r"instagram",
    r"snapchat",
    r"youtube shorts",
    r"reels",
    r"internet addict(ion|ed)?",
    r"addicted to (the )?internet",
    r"gaming addict(ion|ed)?",
    r"addicted to (gaming|video games|games)",
    r"(digital|dopamine) detox",
]

# How far behind the previous run's newest post each run rescans, to catch
# posts that appear late (for example, approved from a moderation queue).
OVERLAP_HOURS = 6

# Stored posts are rechecked after this many hours to apply deletions and
# refresh scores.
SYNC_AFTER_HOURS = 24

# When set, post titles and bodies older than this many days are erased
# during sync. Reddit recommends deleting stored content within 48 hours.
# Leave as None until scoring runs at collection time, or text will be lost.
TEXT_RETENTION_DAYS = None
