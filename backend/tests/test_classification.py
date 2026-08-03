import pytest
from pydantic import ValidationError

from app.core.classification import (
    AI_CONFIDENTIALITY_LEVELS,
    CONFIDENTIALITY_LEVELS,
    normalize_confidentiality,
)
from app.schemas.info_items import InfoItemDetailsUpdateIn


def test_confidentiality_taxonomy_has_three_canonical_levels():
    assert CONFIDENTIALITY_LEVELS == ("公开", "内部", "管理员")
    assert AI_CONFIDENTIALITY_LEVELS == ("公开", "内部")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("public", "公开"),
        ("internal", "内部"),
        ("admin", "管理员"),
        ("付费来源", "内部"),
        ("秘密", "内部"),
        ("top_secret", "内部"),
    ],
)
def test_legacy_confidentiality_labels_are_normalized(value, expected):
    assert normalize_confidentiality(value) == expected


def test_unknown_confidentiality_is_rejected():
    with pytest.raises(ValueError, match="密级只能是"):
        normalize_confidentiality("最高机密")


def test_info_item_schema_persists_canonical_legacy_value():
    payload = InfoItemDetailsUpdateIn(classification="机密")
    assert payload.classification == "内部"


def test_info_item_schema_rejects_unknown_value():
    with pytest.raises(ValidationError):
        InfoItemDetailsUpdateIn(classification="最高机密")
