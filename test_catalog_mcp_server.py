"""Acceptance tests for the vendor catalog MCP tool."""

import json

from catalog_mcp_server import (
    compare_vendor_catalogs,
    retrieve_procurement_guidance,
    sequential_reason,
)


def test_holiday_lights_recommendation() -> None:
    result = json.loads(compare_vendor_catalogs("holiday string lights"))
    assert result["recommendation"]["best_value_vendor"] == "Seasonal Source"
    assert result["recommendation"]["highest_quality_vendor"] == "Bright Wholesale"


def test_restaurant_gloves_recommendation() -> None:
    result = json.loads(compare_vendor_catalogs("restaurant nitrile gloves"))
    assert result["recommendation"]["best_value_vendor"] == "FoodSafe Supply"
    assert result["recommendation"]["highest_quality_vendor"] == "Kitchen Direct"


def test_unknown_category_lists_available_inputs() -> None:
    result = json.loads(compare_vendor_catalogs("office chairs"))
    assert result["error"] == "No catalog found for 'office chairs'."
    assert "holiday string lights" in result["available_categories"]


def test_procurement_guidance_retrieval() -> None:
    result = json.loads(retrieve_procurement_guidance("holiday string lights"))
    assert result["product_category"] == "holiday string lights"
    assert any("weather-resistant PVC" in item for item in result["guidance"])


def test_sequential_reasoning_pattern() -> None:
    result = json.loads(
        sequential_reason("holiday string lights", "Three vendor records returned")
    )
    assert [step["step"] for step in result["steps"]] == [
        "Observe",
        "Retrieve",
        "Compare",
        "Decide",
    ]


def test_unknown_category_has_no_guidance() -> None:
    result = json.loads(retrieve_procurement_guidance("office chairs"))
    assert result["error"] == "No procurement guidance found for 'office chairs'."
