from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    uri = f"file:{args.database.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    if not integrity or integrity[0] != "ok":
        raise SystemExit("integrity check failed")
    print(f"Integrity ok; {jobs} job rows")
