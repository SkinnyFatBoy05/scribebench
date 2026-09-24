from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def backup(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.resolve() == destination.resolve():
        raise ValueError("backup destination must differ from source")
    if destination.exists():
        raise FileExistsError("use a fresh snapshot path; existing backups are immutable")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as source_db,
        closing(sqlite3.connect(destination)) as destination_db,
    ):
        source_db.backup(destination_db)
        result = destination_db.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise RuntimeError("backup integrity check failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    backup(args.source, args.destination)
    print(f"Verified backup: {args.destination}")
