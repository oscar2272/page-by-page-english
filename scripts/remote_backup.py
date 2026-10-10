"""Stream a consistent SQLite snapshot and uploaded files to stdout."""

from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile


DATA_DIR = Path("/var/lib/docker/volumes/page-by-page_study_data/_data")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="page-by-page-backup-") as temporary:
        snapshot = Path(temporary) / "study.sqlite3"
        with sqlite3.connect(f"file:{DATA_DIR / 'study.sqlite3'}?mode=ro", uri=True) as source:
            with sqlite3.connect(snapshot) as destination:
                source.backup(destination)

        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as archive:
            archive.add(snapshot, arcname="study.sqlite3")
            archive.add(DATA_DIR / "secret.key", arcname="secret.key")
            archive.add(DATA_DIR / "uploads", arcname="uploads")
            if (DATA_DIR / "openai.key").exists():
                archive.add(DATA_DIR / "openai.key", arcname="openai.key")


if __name__ == "__main__":
    main()
