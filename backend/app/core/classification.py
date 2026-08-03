from __future__ import annotations

from typing import Final


# The current model is a label taxonomy; access enforcement is a later concern.
CONFIDENTIALITY_LEVELS: Final[tuple[str, ...]] = ("公开", "内部", "管理员")
AI_CONFIDENTIALITY_LEVELS: Final[tuple[str, ...]] = ("公开", "内部")

_CONFIDENTIALITY_ALIASES: Final[dict[str, str]] = {
    "公开": "公开",
    "public": "公开",
    "内部": "内部",
    "internal": "内部",
    "管理员": "管理员",
    "admin": "管理员",
    # Legacy labels mixed source accessibility with confidentiality.
    "非公开": "内部",
    "付费来源": "内部",
    "受限来源": "内部",
    "秘密": "内部",
    "机密": "内部",
    "secret": "内部",
    "top_secret": "内部",
}


def normalize_confidentiality(value: object | None) -> str | None:
    """Normalize canonical and legacy labels to the current three-level model."""
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    canonical = _CONFIDENTIALITY_ALIASES.get(normalized)
    if canonical is None:
        canonical = _CONFIDENTIALITY_ALIASES.get(normalized.lower())
    if canonical is None:
        allowed = "、".join(CONFIDENTIALITY_LEVELS)
        raise ValueError(f"密级只能是：{allowed}")
    return canonical
