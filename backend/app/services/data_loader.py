from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"
_ENV_DATA_DIR = os.getenv("DATA_DIR")
_DATA_DIR = Path(_ENV_DATA_DIR) if _ENV_DATA_DIR else _DEFAULT_DATA_DIR


def load_json(filename: str) -> Any:
    path = _DATA_DIR / filename
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
