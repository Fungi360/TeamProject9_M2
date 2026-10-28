"""M3 tests: knowledge layer retrieval, category aliases, handoff payload, and guardrails."""

import json

from catalog_mcp_server import CATALOGS, compare_vendor_catalogs, retrieve_procurement_guidance
from guardrails import build_handoff_payload, check_input, check_output, handoff_ready
from knowledge_base import KNOWLEDGE_BASE

ALL_VENDORS = {item["vendor"] for products in CATALOGS.values() for item in products}


def _payload(category: str) -> dict:
    outputs = {
        "compare_vendor_catalogs": compare_vendor_catalogs(category),
        "retrieve_procurement_guidance": retrieve_procurement_guidance(category),
    }
    return build_handoff_payload(f"Compare {category}", outputs, "analyst summary")


def test_alias_maps_holiday_lights_to_catalog_key() -> None:
    result = json.loads(compare_vendor_catalogs("Holiday Lights"))
    assert result["product_category"] == "holiday string lights"
    assert result["recommendation"]["best_value_vendor"] == "Seasonal Source"


def test_retrieval_ranks_question_relevant_chunk_first() -> None:
    hits = KNOWLEDGE_BASE.search("cost per glove for different box sizes", category="restaurant nitrile gloves")
    assert hits[0]["heading"] == "Cost per glove"


def test_retrieval_never_returns_other_category_chunks() -> None:
    hits = KNOWLEDGE_BASE.search("ceramic dust noise", category="holiday string lights", top_k=10)
    assert all(hit["category"] in ("holiday string lights", "general") for hit in hits)


def test_guidance_tool_returns_sources_with_scores() -> None:
    result = json.loads(retrieve_procurement_guidance("brake pads", "towing truck heat"))
    assert result["sources"][0]["heading"] == "Ceramic versus semi-metallic"
    assert all("score" in source for source in result["sources"])


def test_handoff_payload_has_required_fields() -> None:
    payload = _payload("brake pads")
    for key in ("question", "product_category", "catalog_evidence", "retrieved_guidance", "analyst_summary"):
        assert key in payload
    assert handoff_ready(payload) == (True, "ok")


def test_handoff_blocked_for_unknown_category() -> None:
    ready, reason = handoff_ready(_payload("office chairs"))
    assert not ready
    assert "No catalog found" in reason


def test_input_guardrail_blocks_order_placement() -> None:
    allowed, reason = check_input("Please place an order for 20 brake pads")
    assert not allowed
    assert "cannot place orders" in reason


def test_input_guardrail_allows_normal_question() -> None:
    assert check_input("Compare holiday string lights across the vendors.") == (True, "ok")


def test_output_guardrail_flags_vendor_from_another_category() -> None:
    payload = _payload("brake pads")
    violations = check_output("Garage Wholesale is cheapest; Kitchen Direct is best.", payload, ALL_VENDORS)
    assert any("Kitchen Direct" in v for v in violations)


def test_output_guardrail_passes_grounded_answer() -> None:
    payload = _payload("brake pads")
    answer = "Lowest price: Garage Wholesale. Highest quality: AutoParts Hub."
    assert check_output(answer, payload, ALL_VENDORS) == []
