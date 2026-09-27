#!/usr/bin/env python3
"""Hydrate the pinned Tech DB breadth runtime before local Docker builds.

The runtime snapshot is intentionally excluded from this repository. This script
fetches only data/processed from the trusted, pinned upstream commit, validates
it, builds Tech Boundary DB's two derived snapshots, and installs the result
under breadth/data/processed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "breadth" / "data"
PROCESSED_DIR = DATA_DIR / "processed"
UPSTREAM_REPOSITORY = "https://github.com/sbq9712/tech-db.git"
UPSTREAM_COMMIT = "18b6e3f3ceca6afa01cbdd64f2bf46bbcf0cd892"
EXPECTED_DATA_VERSION = "7e365a2158b5"
EXPECTED_RECORDS = 68026
EXPECTED_SHARDS = 35
EXPECTED_UPSTREAM_FILES = None
STAMP_NAME = ".techdb-runtime-source.json"
DERIVED_FILES = ("alert-records.json", "category-counts.json")
DERIVATION_VERSION = 1
PRESERVED_FILES = {".gitkeep", "README.md"}


class RuntimeValidationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_manifest_data(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise RuntimeValidationError(f"{path.name} does not contain a JSON object")
    try:
        value = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeValidationError(f"{path.name} contains invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeValidationError(f"{path.name} must contain an object")
    return value


def numbered_files(processed: Path, prefix: str) -> set[int]:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)\.js$")
    return {
        int(match.group(1))
        for path in processed.iterdir()
        if path.is_file() and (match := pattern.match(path.name))
    }


def validate_structure(
    processed: Path,
    *,
    expected_records: int = EXPECTED_RECORDS,
    expected_shards: int = EXPECTED_SHARDS,
    expected_data_version: str = EXPECTED_DATA_VERSION,
    expected_upstream_files: int | None = EXPECTED_UPSTREAM_FILES,
) -> list[str]:
    errors: list[str] = []
    if not processed.is_dir():
        return [f"missing directory: {processed}"]

    required = ("manifest-data.js", "manifest.json", "conferences.json", "intelligence.json")
    for name in required:
        path = processed / name
        if not path.is_file() or path.stat().st_size <= 0:
            errors.append(f"missing or empty required file: {name}")

    manifest_data: dict = {}
    if (processed / "manifest-data.js").is_file():
        try:
            manifest_data = parse_manifest_data(processed / "manifest-data.js")
        except (OSError, RuntimeValidationError) as exc:
            errors.append(str(exc))
    meta = manifest_data.get("meta", {}) if isinstance(manifest_data, dict) else {}
    if meta.get("records_total") != expected_records:
        errors.append(
            f"manifest-data records_total is {meta.get('records_total')!r}; expected {expected_records}"
        )
    if meta.get("total_shards") != expected_shards:
        errors.append(
            f"manifest-data total_shards is {meta.get('total_shards')!r}; expected {expected_shards}"
        )
    if meta.get("data_version") != expected_data_version:
        errors.append(
            f"manifest-data data_version is {meta.get('data_version')!r}; "
            f"expected {expected_data_version}"
        )

    manifest: dict = {}
    manifest_path = processed / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                errors.append("manifest.json must contain an object")
                manifest = {}
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"manifest.json is invalid: {exc}")

    expected_indices = set(range(expected_shards))
    for prefix in ("lite-part", "meta-part", "summary-part"):
        actual = numbered_files(processed, prefix)
        if actual != expected_indices:
            missing = sorted(expected_indices - actual)
            extra = sorted(actual - expected_indices)
            errors.append(f"{prefix} shard set mismatch; missing={missing}, extra={extra}")

    for shard in manifest.get("shards", []) if isinstance(manifest, dict) else []:
        raw_path = str(shard.get("path", ""))
        name = Path(raw_path).name
        if not name or name != raw_path.rsplit("/", 1)[-1]:
            errors.append(f"unsafe manifest shard path: {raw_path!r}")
            continue
        path = processed / name
        if not path.is_file() or path.stat().st_size <= 0:
            errors.append(f"missing manifest record shard: {name}")

    source_files = [
        path
        for path in processed.iterdir()
        if path.is_file() and path.name not in {*DERIVED_FILES, STAMP_NAME, *PRESERVED_FILES}
    ]
    if expected_upstream_files is not None and len(source_files) != expected_upstream_files:
        errors.append(
            f"upstream processed file count is {len(source_files)}; expected {expected_upstream_files}"
        )
    if any(path.is_symlink() for path in processed.iterdir()):
        errors.append("runtime directory must not contain symlinks")
    return errors


def build_inventory(processed: Path, names: Iterable[str]) -> dict[str, dict[str, int | str]]:
    inventory: dict[str, dict[str, int | str]] = {}
    for name in sorted(names):
        if Path(name).name != name or name in {"", ".", ".."}:
            raise RuntimeValidationError(f"unsafe inventory path: {name!r}")
        path = processed / name
        if not path.is_file() or path.is_symlink():
            raise RuntimeValidationError(f"inventory file is missing or unsafe: {name}")
        inventory[name] = {"size": path.stat().st_size, "sha256": sha256_file(path)}
    return inventory


def validate_inventory(processed: Path, inventory: object, label: str) -> list[str]:
    if not isinstance(inventory, dict) or not inventory:
        return [f"{label} inventory is missing"]
    errors: list[str] = []
    for name, expected in inventory.items():
        if not isinstance(name, str) or Path(name).name != name:
            errors.append(f"unsafe {label} inventory path: {name!r}")
            continue
        if not isinstance(expected, dict):
            errors.append(f"invalid {label} inventory entry: {name}")
            continue
        path = processed / name
        if not path.is_file() or path.is_symlink():
            errors.append(f"missing {label} file: {name}")
            continue
        size = path.stat().st_size
        if size != expected.get("size"):
            errors.append(f"{label} size mismatch: {name}")
            continue
        if sha256_file(path) != expected.get("sha256"):
            errors.append(f"{label} SHA-256 mismatch: {name}")
    return errors


def load_stamp(processed: Path) -> dict:
    path = processed / STAMP_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def validate_installed(processed: Path = PROCESSED_DIR) -> list[str]:
    errors = validate_structure(processed)
    stamp = load_stamp(processed)
    if stamp.get("repository") != UPSTREAM_REPOSITORY:
        errors.append("runtime source repository stamp is missing or unexpected")
    if stamp.get("commit") != UPSTREAM_COMMIT:
        errors.append("runtime source commit stamp is missing or unexpected")
    if stamp.get("derivation_version") != DERIVATION_VERSION:
        errors.append("derived snapshot version stamp is missing or stale")
    errors.extend(validate_inventory(processed, stamp.get("upstream_files"), "upstream"))
    errors.extend(validate_inventory(processed, stamp.get("derived_files"), "derived"))

    category_path = processed / "category-counts.json"
    alert_path = processed / "alert-records.json"
    try:
        category = json.loads(category_path.read_text(encoding="utf-8"))
        if category.get("record_total") != EXPECTED_RECORDS:
            errors.append("category-counts.json record_total does not match the pinned runtime")
        if category.get("data_version") != EXPECTED_DATA_VERSION:
            errors.append("category-counts.json data_version does not match the pinned runtime")
        if not isinstance(category.get("categories"), list) or not category["categories"]:
            errors.append("category-counts.json has no categories")
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        errors.append(f"category-counts.json is invalid: {exc}")
    try:
        alerts = json.loads(alert_path.read_text(encoding="utf-8"))
        items = alerts.get("items")
        if not isinstance(items, list) or alerts.get("total") != len(items) or not items:
            errors.append("alert-records.json is empty or internally inconsistent")
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        errors.append(f"alert-records.json is invalid: {exc}")
    return errors


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def build_derived(data_dir: Path) -> None:
    run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_breadth_alert_snapshot.py"),
            "--data-dir",
            str(data_dir),
        ]
    )
    run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_breadth_category_counts.py"),
            "--data-dir",
            str(data_dir),
        ]
    )


def make_stamp(processed: Path) -> dict:
    upstream_names = [
        path.name
        for path in processed.iterdir()
        if path.is_file() and path.name not in {*DERIVED_FILES, STAMP_NAME, *PRESERVED_FILES}
    ]
    return {
        "schema": "tech-boundary-breadth-runtime/v1",
        "repository": UPSTREAM_REPOSITORY,
        "commit": UPSTREAM_COMMIT,
        "records_total": EXPECTED_RECORDS,
        "data_version": EXPECTED_DATA_VERSION,
        "total_shards": EXPECTED_SHARDS,
        "derivation_version": DERIVATION_VERSION,
        "upstream_files": build_inventory(processed, upstream_names),
        "derived_files": build_inventory(processed, DERIVED_FILES),
    }


def write_stamp(processed: Path, stamp: dict) -> None:
    target = processed / STAMP_NAME
    temporary = processed / f"{STAMP_NAME}.tmp"
    temporary.write_text(json.dumps(stamp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def install_candidate(candidate: Path, target: Path) -> None:
    expected_parent = (ROOT / "breadth" / "data").resolve()
    if target.resolve().parent != expected_parent or target.name != "processed":
        raise RuntimeValidationError(f"refusing unsafe runtime target: {target}")
    target.mkdir(parents=True, exist_ok=True)
    (target / STAMP_NAME).unlink(missing_ok=True)

    candidate_names = {path.name for path in candidate.iterdir() if path.is_file()}
    for path in target.iterdir():
        if path.name in PRESERVED_FILES:
            continue
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    for source in sorted(candidate.iterdir()):
        if not source.is_file() or source.name == STAMP_NAME:
            continue
        temporary = target / f".{source.name}.hydrate-tmp"
        shutil.copy2(source, temporary)
        os.replace(temporary, target / source.name)
    shutil.copy2(candidate / STAMP_NAME, target / STAMP_NAME)

    installed = {path.name for path in target.iterdir() if path.is_file()}
    missing = candidate_names - installed
    if missing:
        raise RuntimeValidationError(f"runtime install omitted files: {sorted(missing)}")


def hydrate() -> None:
    if shutil.which("git") is None:
        raise RuntimeValidationError("git is required to download the pinned public runtime snapshot")
    print(
        "Breadth runtime is missing, incomplete, or from a different version.\n"
        "Downloading the pinned Tech DB snapshot (about 282 MB on first run).",
        flush=True,
    )
    with tempfile.TemporaryDirectory(prefix="techdb-breadth-runtime-") as temp:
        temp_root = Path(temp)
        checkout = temp_root / "upstream"
        staged_data = temp_root / "staged-data"
        staged_processed = staged_data / "processed"

        run(["git", "init", "--quiet", str(checkout)])
        run(["git", "-C", str(checkout), "remote", "add", "origin", UPSTREAM_REPOSITORY])
        run(
            [
                "git",
                "-C",
                str(checkout),
                "-c",
                "protocol.version=2",
                "fetch",
                "--depth=1",
                "--filter=blob:none",
                "origin",
                UPSTREAM_COMMIT,
            ]
        )
        run(["git", "-C", str(checkout), "sparse-checkout", "init", "--cone"])
        run(["git", "-C", str(checkout), "sparse-checkout", "set", "data/processed"])
        run(["git", "-C", str(checkout), "checkout", "--detach", "FETCH_HEAD"])
        actual_commit = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
        ).strip()
        if actual_commit != UPSTREAM_COMMIT:
            raise RuntimeValidationError(
                f"downloaded commit {actual_commit}; expected {UPSTREAM_COMMIT}"
            )

        shutil.copytree(checkout / "data" / "processed", staged_processed)
        structure_errors = validate_structure(staged_processed)
        if structure_errors:
            raise RuntimeValidationError(
                "downloaded runtime failed validation:\n- " + "\n- ".join(structure_errors)
            )
        build_derived(staged_data)
        write_stamp(staged_processed, make_stamp(staged_processed))
        install_candidate(staged_processed, PROCESSED_DIR)

    errors = validate_installed()
    if errors:
        raise RuntimeValidationError(
            "installed runtime failed validation:\n- " + "\n- ".join(errors)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the installed runtime without downloading or changing files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="download and replace the pinned runtime even when the current copy is valid",
    )
    args = parser.parse_args()

    print(
        f"Checking breadth runtime: Tech DB {UPSTREAM_COMMIT[:12]} / "
        f"{EXPECTED_RECORDS:,} records / {EXPECTED_SHARDS} shards",
        flush=True,
    )
    errors = validate_installed()
    if not errors and not args.force:
        print("Breadth runtime is complete and verified; reusing local files.", flush=True)
        return 0
    if args.check:
        print("Breadth runtime validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if errors:
        print("Current runtime cannot be reused:")
        for error in errors[:12]:
            print(f"- {error}")
        if len(errors) > 12:
            print(f"- ... and {len(errors) - 12} more")
    try:
        hydrate()
    except (OSError, RuntimeValidationError, subprocess.CalledProcessError) as exc:
        print(f"Breadth runtime hydration failed: {exc}", file=sys.stderr)
        print(
            "Docker was not started. Check network access to github.com and rerun "
            "bash ./start_with_local_ai.sh.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Breadth runtime ready: {EXPECTED_RECORDS:,} records, "
        f"{EXPECTED_SHARDS} lite/meta/summary shards.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
