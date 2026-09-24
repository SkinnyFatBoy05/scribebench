"""Restore a verified SQLite snapshot to a NEW path, never over a running/live database."""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

from scripts.backup import backup


def restore(source: Path, destination: Path):
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.resolve() == destination.resolve():
        raise ValueError("restore destination must differ from source")
    if any(Path(str(destination) + suffix).exists() for suffix in ("", "-wal", "-shm")):
        raise FileExistsError("restore requires a new destination without SQLite sidecars")
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("snapshot integrity failed")
        if not db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
        ).fetchone():
            raise ValueError("snapshot has no jobs table")
    backup(source, destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("new_destination", type=Path)
    args = parser.parse_args()
    restore(args.snapshot, args.new_destination)
    print("Verified restore completed at a new path; live configuration is unchanged.")
