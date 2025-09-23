import pytest
from pydantic import ValidationError

from app.api.nft.models import TraitAttribute


@pytest.mark.parametrize(
    "input_data,expected_trait_type,expected_value",
    [
        ({"trait_type": "Color", "value": "Red"}, "Color", "Red"),
        ({"name": "Shape", "value": "Round"}, "Shape", "Round"),
        ({"value": "Some Value"}, "Unknown", "Some Value"),
        ({"trait_type": "", "value": "Empty String"}, "Unknown", "Empty String"),
        ({"trait_type": "   ", "value": "Whitespace"}, "Unknown", "Whitespace"),
        ({"trait_type": "Size"}, "Size", None),
        ({"trait_type": "Name", "value": "Test"}, "Name", "Test"),
        ({"trait_type": "Count", "value": 42}, "Count", 42),
        ({"trait_type": "Price", "value": 1.99}, "Price", 1.99),
        ({"trait_type": "Rare", "value": True}, "Rare", True),
        ({"trait_type": "Test", "value": None}, "Test", None),
        ({"trait_type": "Test", "value": ""}, "Test", ""),
        (
            {
                "trait_type": "parent",
                "value": {"parent": {"PARENT_CANNOT_SET_TTL": False}},
            },
            "parent",
            '{"parent": {"PARENT_CANNOT_SET_TTL": false}}',
        ),
        (
            {"trait_type": "tags", "value": ["tag1", "tag2", "tag3"]},
            "tags",
            '["tag1", "tag2", "tag3"]',
        ),
    ],
)
def test_trait_attribute_valid_cases(input_data, expected_trait_type, expected_value):
    attr = TraitAttribute.model_validate(input_data)
    assert attr.trait_type == expected_trait_type
    assert attr.value == expected_value


@pytest.mark.parametrize(
    "input_data,expected_error",
    [
        ("not a dict", "TraitAttribute data must be a dictionary"),
        ({}, "Either trait_type or value must be provided"),
        ({"invalid_field": "value"}, "Either trait_type or value must be provided"),
        (
            {"trait_type": "", "value": None},
            "Either trait_type or value must be provided for TraitAttribute",
        ),
        (
            {"trait_type": "", "value": ""},
            "Either trait_type or value must be provided for TraitAttribute",
        ),
        (
            {"name": "", "value": None},
            "Either trait_type or value must be provided for TraitAttribute",
        ),
        (
            {"name": "", "value": ""},
            "Either trait_type or value must be provided for TraitAttribute",
        ),
        (
            {"value": None},
            "Either trait_type or value must be provided for TraitAttribute",
        ),
        (
            {"value": ""},
            "Either trait_type or value must be provided for TraitAttribute",
        ),
    ],
)
def test_trait_attribute_invalid_cases(input_data, expected_error):
    with pytest.raises(ValidationError) as exc_info:
        TraitAttribute.model_validate(input_data)

    assert expected_error in str(exc_info.value)
