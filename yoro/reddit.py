"""Authenticated, read-only connection to the official Reddit API."""
import os
import sys

import praw
from dotenv import load_dotenv

from . import __version__

REQUIRED = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME")


def user_agent(username: str) -> str:
    """Reddit's required format: <platform>:<app ID>:<version> (by /u/<username>)."""
    return f"script:yoro:v{__version__} (by /u/{username})"


def connect() -> praw.Reddit:
    load_dotenv()
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}. See .env.example.")
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=user_agent(os.environ["REDDIT_USERNAME"]),
    )
    reddit.read_only = True  # application-only OAuth, no user login
    return reddit
