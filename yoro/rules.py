"""What gets excluded and what counts as on topic."""
from __future__ import annotations

import hashlib
import re

from . import config

_PATTERNS = [(t, re.compile(rf"\b{t}\b", re.IGNORECASE)) for t in config.TOPIC_TERMS]
FILTER_VERSION = hashlib.sha256("\n".join(config.TOPIC_TERMS).encode()).hexdigest()[:8]


def exclusion_reason(post) -> str | None:
    """Reason to skip a post before storing anything, or None to continue."""
    text = post.selftext or ""
    if post.author is None or text == "[deleted]":
        return "deleted"
    if getattr(post, "removed_by_category", None) or text == "[removed]":
        return "removed"
    if post.stickied or post.distinguished:
        return "moderator"  # pinned or official moderator posts
    if str(post.author).lower() == "automoderator":
        return "automod"
    if post.over_18:
        return "nsfw"
    return None


def matched_terms(post) -> list[str]:
    text = f"{post.title or ''} {post.selftext or ''}"
    return [term for term, pattern in _PATTERNS if pattern.search(text)]


def is_gone(post) -> str | None:
    """On recheck: deleted by the author, removed by moderators or Reddit, or neither."""
    text = post.selftext or ""
    if post.author is None or text == "[deleted]":
        return "deleted"
    if getattr(post, "removed_by_category", None) or text == "[removed]":
        return "removed"
    return None
