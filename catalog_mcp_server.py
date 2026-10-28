"""MCP server for comparing small-business vendor catalogs."""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from knowledge_base import KNOWLEDGE_BASE


mcp = FastMCP("Vendor Catalog Comparison")

CATEGORY_ALIASES: dict[str, str] = {
    "holiday lights": "holiday string lights",
    "christmas lights": "holiday string lights",
    "string lights": "holiday string lights",
    "led string lights": "holiday string lights",
    "nitrile gloves": "restaurant nitrile gloves",
    "gloves": "restaurant nitrile gloves",
    "food service gloves": "restaurant nitrile gloves",
    "brake pad": "brake pads",
    "ceramic brake pads": "brake pads",
}


def normalize_category(product_category: str) -> str:
    """Lowercase, collapse whitespace, and map known aliases to catalog keys."""
    category = " ".join(product_category.lower().split())
    return CATEGORY_ALIASES.get(category, category)


CATALOGS: dict[str, list[dict[str, Any]]] = {
    "holiday string lights": [
        {
            "vendor": "SunCo Supply",
            "product": "Commercial LED string lights",
            "unit_price": 18.50,
            "pack_size": "25 lights",
            "material": "weather-resistant PVC",
            "quality_score": 4.2,
        },
        {
            "vendor": "Seasonal Source",
            "product": "Commercial LED string lights",
            "unit_price": 16.75,
            "pack_size": "25 lights",
            "material": "indoor PVC",
            "quality_score": 3.6,
        },
        {
            "vendor": "Bright Wholesale",
            "product": "Commercial LED string lights",
            "unit_price": 21.00,
            "pack_size": "25 lights",
            "material": "weather-resistant PVC",
            "quality_score": 4.8,
        },
    ],
    "restaurant nitrile gloves": [
        {
            "vendor": "Kitchen Direct",
            "product": "Blue nitrile gloves",
            "unit_price": 12.00,
            "pack_size": "100 gloves",
            "material": "latex-free nitrile",
            "quality_score": 4.4,
        },
        {
            "vendor": "FoodSafe Supply",
            "product": "Blue nitrile gloves",
            "unit_price": 10.50,
            "pack_size": "100 gloves",
            "material": "latex-free nitrile",
            "quality_score": 4.0,
        },
    ],
    "brake pads": [
        {
            "vendor": "AutoParts Hub",
            "product": "Ceramic brake pads",
            "unit_price": 42.00,
            "pack_size": "1 axle set",
            "material": "ceramic composite",
            "quality_score": 4.5,
        },
        {
            "vendor": "Garage Wholesale",
            "product": "Ceramic brake pads",
            "unit_price": 38.00,
            "pack_size": "1 axle set",
            "material": "semi-metallic composite",
            "quality_score": 3.8,
        },
    ],
}


@mcp.tool()
def compare_vendor_catalogs(product_category: str) -> str:
    """Compare matching products across vendors on price, quality, and material."""
    category = normalize_category(product_category)
    products = CATALOGS.get(category)
    if not products:
        available = ", ".join(sorted(CATALOGS))
        return json.dumps(
            {"error": f"No catalog found for '{product_category}'.", "available_categories": available},
            indent=2,
        )

    best_value = min(products, key=lambda item: (item["unit_price"], -item["quality_score"]))
    highest_quality = max(products, key=lambda item: item["quality_score"])
    return json.dumps(
        {
            "product_category": category,
            "vendors": products,
            "recommendation": {
                "best_value_vendor": best_value["vendor"],
                "highest_quality_vendor": highest_quality["vendor"],
                "reason": (
                    f"{best_value['vendor']} has the lowest unit price at "
                    f"${best_value['unit_price']:.2f}; {highest_quality['vendor']} "
                    f"has the highest quality score at {highest_quality['quality_score']:.1f}."
                ),
            },
        },
        indent=2,
    )


@mcp.tool()
def retrieve_procurement_guidance(product_category: str, question: str = "") -> str:
    """Retrieve the most relevant procurement guidance chunks (RAG) for a category and question."""
    category = normalize_category(product_category)
    if category not in KNOWLEDGE_BASE.categories():
        return json.dumps(
            {"error": f"No procurement guidance found for '{product_category}'."},
            indent=2,
        )
    hits = KNOWLEDGE_BASE.search(f"{category} {question}", category=category, top_k=3)
    return json.dumps(
        {
            "product_category": category,
            "guidance": [hit["text"] for hit in hits],
            "sources": [
                {"chunk_id": hit["chunk_id"], "heading": hit["heading"], "score": hit["score"]}
                for hit in hits
            ],
        },
        indent=2,
    )


@mcp.tool()
def sequential_reason(product_category: str, observation: str) -> str:
    """Create an auditable Observe, Retrieve, Compare, Decide reasoning trace."""
    category = normalize_category(product_category)
    return json.dumps(
        {
            "product_category": category,
            "steps": [
                {"step": "Observe", "result": observation.strip()},
                {
                    "step": "Retrieve",
                    "result": f"Use compare_vendor_catalogs and retrieve_procurement_guidance for '{category}'.",
                },
                {
                    "step": "Compare",
                    "result": "Compare unit prices, quality scores, pack sizes, materials, and category guidance.",
                },
                {
                    "step": "Decide",
                    "result": "Present separate lowest-price and highest-quality conclusions; identify trade-offs without ordering.",
                },
            ],
        },
        indent=2,
    )


if __name__ == "__main__":
    mcp.run()
