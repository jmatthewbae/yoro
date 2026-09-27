"""
YORO collector.

    python run.py collect   pull new posts (schedule hourly)
    python run.py sync      apply deletions and refresh scores (schedule daily)
    python run.py status    show what has been collected
"""
import sys
from contextlib import contextmanager

from yoro import collect, config, db, status, sync


@contextmanager
def single_run():
    """Stop two scheduled runs from overlapping."""
    config.LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.LOCK_PATH, "w") as f:
        try:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            pass  # no locking on Windows
        except BlockingIOError:
            sys.exit("Another YORO run is in progress.")
        yield


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "status":
        ok = status.run(db.connect(config.DB_PATH))
    elif command in ("collect", "sync"):
        from yoro.reddit import connect
        with single_run():
            reddit, conn = connect(), db.connect(config.DB_PATH)
            ok = (collect if command == "collect" else sync).run(reddit, conn)
    else:
        sys.exit(__doc__)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
