#!/usr/bin/env python3
"""Validate the files that are allowed into the application repository.

This check is intentionally read-only. It validates Git-tracked paths rather
than copying, rebuilding, or hydrating any runtime data.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_TRACKED_FILE_BYTES = 50 * 1024 * 1024
REQUIRED_FILES = (
    ".env.example",
    "docker-compose.yml",
    "web/Dockerfile",
    "backend/Dockerfile",
    "backend/alembic.ini",
)
FORBIDDEN_NAMES = {".env", ".env.local", ".env.production"}
FORBIDDEN_PREFIXES = (
    "backup/",
    "pg_data/",
    "runtime-data/",
    "uploads/",
    "external-data/knowledge-base/",
)
FORBIDDEN_SUFFIXES = (
    ".dump",
    ".pem",
    ".p12",
    ".pfx",
    ".sqlite",
    ".sqlite3",
    ".sql.gz",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".zip",
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def main() -> int:
    if not (ROOT / ".git").exists():
        print(f"ERROR: not a Git worktree: {ROOT}", file=sys.stderr)
        return 1

    issues: list[str] = []
    files = tracked_files()
    tracked = {path.replace("\\", "/") for path in files}

    for required in REQUIRED_FILES:
        if required not in tracked or not (ROOT / required).is_file():
            issues.append(f"required file is missing or untracked: {required}")

    for relative in sorted(tracked):
        path = ROOT / relative
        name = path.name.lower()
        if name in FORBIDDEN_NAMES:
            issues.append(f"forbidden secret file is tracked: {relative}")
        if path.name != ".gitkeep" and any(
            relative.startswith(prefix) for prefix in FORBIDDEN_PREFIXES
        ):
            issues.append(f"runtime data is tracked: {relative}")
        if relative.lower().endswith(FORBIDDEN_SUFFIXES):
            issues.append(f"generated or sensitive archive is tracked: {relative}")
        if path.is_file() and path.stat().st_size > MAX_TRACKED_FILE_BYTES:
            issues.append(
                f"tracked file exceeds {MAX_TRACKED_FILE_BYTES} bytes: {relative}"
            )

    if issues:
        print("Repository validation failed:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1

    print(f"Repository validation passed: {len(tracked)} tracked files checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
