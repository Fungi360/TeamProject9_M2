# CatalogIQ: Vendor Catalog Comparison Agent

CatalogIQ helps small commercial buyers compare similar products across multiple vendor catalogs. It uses the OpenAI Agents SDK and FastMCP with an NRP-hosted `gpt-oss` model.

## Problem

Small commercial buyers such as restaurants, auto repair shops, and seasonal retailers spend hours comparing price, quality, material, and pack size across vendor catalogs. Existing tools often stop at price and availability. CatalogIQ separates the lowest-price option from the highest-quality option and explains material trade-offs for the buyer's decision.

## M3 Architecture

The application uses two agents with clearly separated roles:

1. **Catalog Analyst** calls the MCP tools, gathers exact catalog evidence, and produces a structured evidence summary.
2. **Procurement Reviewer** receives the original question and evidence summary, validates unsupported claims, applies procurement guidance, and returns the final recommendation.

The handoff is explicit in orchestration: `ask_agent` runs the analyst to completion and then invokes the reviewer with the analyst's evidence. This avoids depending on a model to generate an SDK handoff tool call correctly.

### MCP tools

- `compare_vendor_catalogs`: returns matching vendor records and identifies the lowest-price and highest-quality vendors.
- `retrieve_procurement_guidance`: retrieves category-specific knowledge guidance stored in the MCP server.
- `sequential_reason`: creates an auditable `Observe -> Retrieve -> Compare -> Decide` reasoning trace.

The `sequential_reason` tool implements a sequential-thinking reasoning pattern. `retrieve_procurement_guidance` provides a local knowledge layer, analogous to a small RAG knowledge retrieval layer, without an external vector database.

## CHANGES

### M3 changes

- Added a two-agent architecture with a **Catalog Analyst** and **Procurement Reviewer** role.
- Added an explicit, deterministic handoff passing the original question and analyst evidence to the reviewer.
- Added `sequential_reason`, an MCP sequential-thinking tool that produces an auditable `Observe -> Retrieve -> Compare -> Decide` trace.
- Added `retrieve_procurement_guidance`, a knowledge/retrieval MCP tool for category-specific procurement guidance.
- Expanded the suite from six to twelve test cases, covering each catalog category, recommendation outputs, input normalization, knowledge retrieval, and sequential reasoning.
- Updated setup and architecture documentation to reflect M3 behavior.

### M2 baseline retained

- Kept the FastMCP stdio server and `compare_vendor_catalogs` tool.
- Kept NRP-compatible model configuration and portable script-relative paths.
- Kept exact, testable sample catalog data for three categories.
- Kept `.env` outside Git while preserving the local run configuration.

## Setup and run

1. Install Python 3.10 or newer.
2. Create a virtual environment and activate it.
3. Create `.env` beside this README:

```env
NRP_BASE_URL=https://your-nrp-endpoint.example/v1
NRP_API_KEY=your-api-key
```

4. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

5. Run the two-agent workflow. The script starts the MCP server automatically:

```bash
python vendor_catalog_agent.py "Compare holiday string lights across the vendors."
```

6. Optionally run the dependency-free browser front end:

```bash
python app.py
```

Open `http://127.0.0.1:5000` and enter a catalog comparison question. `app.py` uses Python's standard library and calls the existing `ask_agent` function; it does not modify the MCP server or agent backend. Stop the server with `Ctrl+C`.

7. Run tests without an API key:

```bash
python -m pytest -q
```

## Test cases

1. `holiday string lights` -> best value `Seasonal Source`; highest quality `Bright Wholesale`.
2. `restaurant nitrile gloves` -> best value `FoodSafe Supply`; highest quality `Kitchen Direct`.
3. `office chairs` (unknown category) -> error listing available categories.
4. Holiday-light guidance retrieval -> category-specific indoor/outdoor PVC guidance.
5. Sequential reasoning -> stages `Observe`, `Retrieve`, `Compare`, `Decide`.
6. Unknown-category guidance -> explicit missing-guidance error.
7. `brake pads` -> best value `Garage Wholesale`; highest quality `AutoParts Hub`.
8. Brake-pad records -> both vendor records include the expected axle-set pack size.
9. Catalog category with extra spaces and uppercase letters -> normalized category and correct recommendation.
10. Restaurant glove guidance -> includes latex-free material guidance.
11. Guidance category with extra spaces and uppercase letters -> normalized category and both guidance entries.
12. Sequential reasoning with padded inputs -> normalized category and trimmed observation.

## Current capabilities

- Plain-language catalog comparisons for three sample categories.
- Separate lowest-price and highest-quality conclusions.
- Material and pack-size evidence in the final review.
- Explicit two-agent role separation and handoff.
- Auditable sequential reasoning and category knowledge retrieval.
- Unknown-category errors that do not invent catalog data.
- No order placement: the agent supplies decision support only.

## Known limitations

- Vendor catalogs are hard-coded sample data, not live catalogs.
- Category matching is exact; aliases such as "holiday lights" are not normalized.
- Retrieval is keyword/category lookup over a local knowledge dictionary, not semantic vector search.
- Quality scores are fixed sample values rather than derived from live reviews or specifications.
- `best value` is lowest unit price only; it does not yet weight pack count, quality, freight, or total project cost.
- The agent does not upload, parse, or persist PDFs, spreadsheets, or CSV catalogs.
- The agent does not track vendor spend over time or place orders.

## Files

- `app.py`: Optional dependency-free browser front end that calls the existing agent.
- `catalog_mcp_server.py`: FastMCP server with catalog, knowledge-retrieval, and sequential-reasoning tools.
- `vendor_catalog_agent.py`: two-agent orchestration and explicit analyst-to-reviewer handoff.
- `test_catalog_mcp_server.py`: M2 catalog acceptance tests and M3 MCP capability tests.
- `requirements.txt`: Python dependencies.
- `.gitignore`: excludes `.env`, virtual environments, caches, and local generated files.
