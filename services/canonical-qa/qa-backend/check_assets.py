#!/usr/bin/env python3
"""Validate the immutable QA model, record, and index bundle."""
from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
MANIFEST_PATH = Path(__file__).resolve().with_name("qa-assets-manifest.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text("utf-8"))
    for relative, expected in manifest["files"].items():
        path = REPO / relative
        if not path.is_file():
            raise SystemExit(f"missing QA asset: {relative}")
        actual_size = path.stat().st_size
        if actual_size != expected["bytes"]:
            raise SystemExit(
                f"QA asset size mismatch: {relative}: {actual_size} != {expected['bytes']}"
            )
        actual_hash = sha256(path)
        if actual_hash != expected["sha256"]:
            raise SystemExit(f"QA asset SHA-256 mismatch: {relative}: {actual_hash}")

    records = json.loads((REPO / "data/processed/all-records-lite.json").read_text("utf-8"))
    with (REPO / "data/lightrag/vector_index_v2.pkl").open("rb") as stream:
        vector = pickle.load(stream)
    with (REPO / "data/lightrag/bm25_index.pkl").open("rb") as stream:
        bm25 = pickle.load(stream)

    checks = {
        "total_records": (len(records), manifest["expected_total_records"]),
        "vector_records": (len(vector["meta"]), manifest["expected_indexed_records"]),
        "bm25_records": (len(bm25["meta"]), manifest["expected_indexed_records"]),
        "embedding_dim": (int(vector["dim"]), manifest["expected_embedding_dim"]),
    }
    failures = {name: values for name, values in checks.items() if values[0] != values[1]}
    if failures:
        raise SystemExit(f"QA asset count mismatch: {failures}")
    print(json.dumps({name: actual for name, (actual, _) in checks.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
