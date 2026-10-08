import importlib.util
import json
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_empty_changes_pack_contains_no_indexes(tmp_path):
    b = module("build_feed_package")
    data, count, summary = b.build_changes_slice([], {})
    package = tmp_path / "empty.zip"; package.write_bytes(data)
    with zipfile.ZipFile(package) as z:
        assert set(z.namelist()) == {"manifest.json", "records.json", "changes.json"}
        assert json.loads(z.read("records.json")) == []
        assert json.loads(z.read("changes.json")) == []
    assert count == 0 and summary["sequence"] == 1
    assert module("verify_feed_sequence").load_manifest(package)["record_count"] == 0


def test_calendar_gap_is_failure_even_when_change_chain_is_continuous(tmp_path):
    b = module("build_feed_package")
    chain = ""
    for seq, date in enumerate(("2026-10-01", "2026-10-03"), 1):
        manifest = {"date": date, "sequence": seq, "predecessor": chain,
                    "record_count": 0, "records_sha256": hashlib.sha256(b"[]").hexdigest()}
        digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        chain = hashlib.sha256((chain + digest).encode()).hexdigest()
        manifest.update(manifest_digest=digest, chain=chain)
        with zipfile.ZipFile(tmp_path / f"{date}.zip", "w") as z:
            z.writestr("manifest.json", json.dumps(manifest)); z.writestr("records.json", "[]")
    v = module("verify_feed_sequence")
    assert v.main([str(tmp_path)]) == 2
    assert v.main([str(tmp_path), "--allow-date-gaps"]) == 0
