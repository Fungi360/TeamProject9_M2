"""Deterministic guardrails and the analyst-to-reviewer handoff payload for CatalogIQ.

These checks run in plain Python around the two agents so they behave the same way
on every run, regardless of how the model phrases its output.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_QUESTION_CHARS = 1000

_ORDER_PATTERNS = [
    r"\b(place|submit|make|put in)\b.{0,30}\border\b",
    r"\b(buy|purchase|order)\b.{0,20}\bfor (me|us)\b",
    r"\bcheck ?out\b",
]
_INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above) instructions",
    r"\bsystem prompt\b",
]
_ORDER_CLAIMS = [
    r"\b(i|we) (have )?(placed|submitted|completed) (the|an|your) order\b",
    r"\byour order (has been|was) (placed|submitted)\b",
]


def check_input(question: str) -> tuple[bool, str]:
    """Input guardrail. Returns (allowed, reason)."""
    text = (question or "").strip()
    if not text:
        return False, "Please enter a product comparison question."
    if len(text) > MAX_QUESTION_CHARS:
        return False, f"Questions are limited to {MAX_QUESTION_CHARS} characters."
    lowered = text.lower()
    if any(re.search(p, lowered) for p in _INJECTION_PATTERNS):
        return False, "This request tries to change the agent's instructions, so it was not run."
    if any(re.search(p, lowered) for p in _ORDER_PATTERNS):
        return False, (
            "CatalogIQ provides decision support only and cannot place orders. "
            "Ask for a comparison instead, for example: 'Compare brake pads across the vendors.'"
        )
    return True, "ok"


def _parse_tool_output(raw: Any) -> Any:
    """MCP tool results may arrive as JSON text or as a wrapped text content block."""
    if isinstance(raw, (dict, list)):
        data = raw
    else:
        try:
            data = json.loads(str(raw))
        except (TypeError, json.JSONDecodeError):
            return {"raw": str(raw)}
    if isinstance(data, dict) and "text" in data and data.get("type") == "text":
        return _parse_tool_output(data["text"])
    if isinstance(data, list) and data and isinstance(data[0], dict) and "text" in data[0]:
        return _parse_tool_output(data[0]["text"])
    return data


def build_handoff_payload(
    question: str, tool_outputs: dict[str, Any], analyst_summary: str
) -> dict[str, Any]:
    """Assemble the explicit payload passed from the Catalog Analyst to the Procurement Reviewer."""
    catalog = _parse_tool_output(tool_outputs.get("compare_vendor_catalogs", {}))
    guidance = _parse_tool_output(tool_outputs.get("retrieve_procurement_guidance", {}))
    reasoning = _parse_tool_output(tool_outputs.get("sequential_reason", {}))
    return {
        "question": question,
        "product_category": catalog.get("product_category") if isinstance(catalog, dict) else None,
        "catalog_evidence": catalog,
        "retrieved_guidance": guidance,
        "reasoning_trace": reasoning,
        "analyst_summary": analyst_summary,
        "tools_called": sorted(tool_outputs),
    }


def handoff_ready(payload: dict[str, Any]) -> tuple[bool, str]:
    """Handoff trigger: the analyst must have returned real catalog evidence."""
    catalog = payload.get("catalog_evidence") or {}
    if "compare_vendor_catalogs" not in payload.get("tools_called", []):
        return False, "The Catalog Analyst did not call compare_vendor_catalogs, so there is no evidence to review."
    if isinstance(catalog, dict) and catalog.get("error"):
        categories = catalog.get("available_categories", "")
        return False, f"{catalog['error']} Available categories: {categories}."
    if not isinstance(catalog, dict) or not catalog.get("vendors"):
        return False, "The catalog tool returned no vendor records."
    return True, "ok"


def check_output(answer: str, payload: dict[str, Any], all_vendors: set[str]) -> list[str]:
    """Output guardrail. Returns a list of violations (empty list means the answer passed)."""
    violations: list[str] = []
    evidence_vendors = {v["vendor"] for v in payload["catalog_evidence"].get("vendors", [])}
    lowered = answer.lower()
    for vendor in sorted(all_vendors - evidence_vendors):
        if vendor.lower() in lowered:
            violations.append(f"mentions vendor '{vendor}', which is not in this category's evidence")
    if not any(vendor.lower() in lowered for vendor in evidence_vendors):
        violations.append("does not name any vendor from the evidence")
    if any(re.search(p, lowered) for p in _ORDER_CLAIMS):
        violations.append("claims an order was placed")
    return violations
