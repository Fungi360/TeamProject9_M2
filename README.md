# CatalogIQ: Vendor Catalog Comparison Agent

CatalogIQ helps small commercial buyers compare similar products across multiple vendor catalogs. It uses the OpenAI Agents SDK and FastMCP with an NRP-hosted `gpt-oss` model.

## Problem

Small commercial buyers such as restaurants, auto repair shops, and seasonal retailers spend hours comparing price, quality, material, and pack size across vendor catalogs. Existing tools often stop at price and availability. CatalogIQ separates the lowest-price option from the highest-quality option and explains material trade-offs for the buyer's decision.

## M3 Architecture

The application uses two agents with clearly separated roles:

1. **Catalog Analyst** calls the MCP tools, gathers exact catalog evidence, and produces a structured evidence summary.
2. **Procurement Reviewer** receives the original question and evidence summary, validates unsupported claims, applies procurement guidance, and returns the final recommendation.

The handoff is explicit in orchestration: `ask_agent` runs the analyst to completion, collects every MCP tool result from the run, and builds a JSON **handoff payload** (`question`, `product_category`, `catalog_evidence`, `retrieved_guidance`, `reasoning_trace`, `analyst_summary`, `tools_called`). This avoids depending on a model to generate an SDK handoff tool call correctly.

**Handoff trigger:** the reviewer runs only when the analyst called `compare_vendor_catalogs` and it returned vendor records. If the category is unknown or the tool was never called, the workflow stops and returns the error with the available categories instead of letting the reviewer guess.

### Guardrails (`guardrails.py`)

- **Input guardrail:** blocks empty or overlong questions, order-placement requests ("place an order", "buy this for me"), and prompt-injection phrases before any model call.
- **Output guardrail:** checks the reviewer's answer against the payload. It flags vendors that are not in this category's evidence, answers that name no evidence vendor, and claims that an order was placed. On a failure the reviewer is retried once; if it still fails, the answer is returned with a visible guardrail notice.

### MCP tools

- `compare_vendor_catalogs`: returns matching vendor records and identifies the lowest-price and highest-quality vendors.
- `retrieve_procurement_guidance`: retrieval-augmented guidance. Takes the category and the buyer's question and returns the top 3 most relevant guidance chunks with their source IDs and similarity scores.
- `sequential_reason`: creates an auditable `Observe -> Retrieve -> Compare -> Decide` reasoning trace.

The `sequential_reason` tool implements a sequential-thinking reasoning pattern.

### Knowledge layer (`knowledge_base.py` + `knowledge/`)

Procurement guidance lives in Markdown files under `knowledge/` (one per category plus a general file). Each `## ` section becomes a chunk. At startup the chunks are embedded as TF-IDF vectors in an in-memory index, and `retrieve_procurement_guidance` ranks them by cosine similarity to the category plus the buyer's question, filtered to that category and the general guidance. Adding guidance means adding a section to a Markdown file; no code change is needed.

## CHANGES

### M3 changes, round 2 (structured handoff, RAG, guardrails, evaluation)

- **Replaced the hard-coded guidance dictionary with a retrieval layer** (`knowledge_base.py`, `knowledge/*.md`). Why: the dictionary always returned the same two lines regardless of the question; retrieval now returns the guidance that matches what the buyer asked (for example, a towing question surfaces the semi-metallic heat guidance first).
- **Made the handoff payload explicit JSON** built from the analyst's actual tool results, not its free-text summary. Why: the reviewer can now check claims against raw evidence instead of trusting the analyst's paraphrase.
- **Added a handoff trigger** (`handoff_ready`). Why: in M2 an unknown category still reached the second stage, which wasted a model call and risked an invented answer.
- **Added input and output guardrails** (`guardrails.py`). Why: CatalogIQ is decision support only, so it must never invent vendors or claim to act on the buyer's behalf, even if the model drifts.
- **Added category aliases** (`holiday lights`, `christmas lights`, `gloves`, `brake pad`, and others). Why: exact matching was M2 known limitation 1.
- **Added stage logging** to stderr (`[analyst]`, `[handoff]`, `[input-guardrail]`, `[output-guardrail]`) so a run can be narrated and debugged.
- **Added `test_m3_system.py`** (10 tests for retrieval, aliases, payload, trigger, and guardrails) and **`eval/`** with the 10 M3 evaluation cases and a keyword-stage runner for M4.
- Relaxed one existing test from exactly 2 guidance items to at least 2, because retrieval now returns the top 3 chunks.

### M3 changes, round 1

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

8. Run the evaluation cases against the live model (writes `eval/results.csv`):

```bash
python eval/run_eval.py
```

## Test cases

`test_catalog_mcp_server.py` (M2 and M3 round 1):

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

`test_m3_system.py` (M3 round 2):

13. `Holiday Lights` alias -> resolves to `holiday string lights`, best value `Seasonal Source`.
14. Retrieval for "cost per glove for different box sizes" -> top chunk is "Cost per glove".
15. Retrieval filtered to lights never returns brake-pad or glove chunks.
16. Brake-pad guidance for "towing truck heat" -> top source is "Ceramic versus semi-metallic", with scores.
17. Handoff payload for brake pads -> contains every required field and the trigger fires.
18. Handoff for `office chairs` -> trigger does not fire; reason lists the missing catalog.
19. "Please place an order..." -> input guardrail blocks it.
20. Normal comparison question -> input guardrail allows it.
21. Brake-pad answer naming `Kitchen Direct` -> output guardrail flags the out-of-evidence vendor.
22. Grounded brake-pad answer -> output guardrail passes.

The 10 end-to-end evaluation cases for M4 are in `eval/m3_eval_cases.json`.

## Current capabilities

- Plain-language catalog comparisons for three sample categories.
- Separate lowest-price and highest-quality conclusions.
- Material and pack-size evidence in the final review.
- Explicit two-agent role separation with a JSON handoff payload and a handoff trigger.
- Auditable sequential reasoning and question-aware guidance retrieval with sources.
- Input and output guardrails; common category aliases.
- Unknown-category errors that do not invent catalog data.
- No order placement: the agent supplies decision support only.

## Known limitations

- Vendor catalogs are hard-coded sample data, not live catalogs.
- Aliases are a fixed list; a phrasing we did not anticipate (for example "outdoor lighting") still fails.
- Retrieval uses TF-IDF vectors, so it matches words, not meaning; a question with no shared words ranks chunks almost evenly. The knowledge base is 15 hand-written chunks.
- Guardrails are pattern-based and can miss reworded order requests or flag a vendor name used in a different sense.
- The output guardrail checks vendor names, not prices, so a wrong price for a correct vendor would pass.
- Each question makes at least two model runs (more if the guardrail retries), so latency is roughly double M2.
- Quality scores are fixed sample values rather than derived from live reviews or specifications.
- `best value` is lowest unit price only; it does not yet weight pack count, quality, freight, or total project cost.
- The agent does not upload, parse, or persist PDFs, spreadsheets, or CSV catalogs.
- The agent does not track vendor spend over time or place orders.

## Files

- `app.py`: Optional dependency-free browser front end that calls the existing agent.
- `catalog_mcp_server.py`: FastMCP server with catalog, knowledge-retrieval, and sequential-reasoning tools, plus category aliases.
- `knowledge_base.py`: TF-IDF vector index and cosine-similarity retrieval over `knowledge/`.
- `knowledge/`: procurement guidance documents (the RAG corpus).
- `guardrails.py`: input guardrail, handoff payload and trigger, output guardrail.
- `vendor_catalog_agent.py`: two-agent orchestration and explicit analyst-to-reviewer handoff.
- `test_catalog_mcp_server.py`: M2 catalog acceptance tests and M3 MCP capability tests.
- `test_m3_system.py`: M3 retrieval, alias, handoff, and guardrail tests.
- `eval/m3_eval_cases.json`, `eval/run_eval.py`: the 10 evaluation cases and their runner.
- `requirements.txt`: Python dependencies.
- `.gitignore`: excludes `.env`, virtual environments, caches, and local generated files.
