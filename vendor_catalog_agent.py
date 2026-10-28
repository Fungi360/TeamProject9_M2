"""Agent that uses the vendor catalog MCP tool."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from agents import (
    Agent,
    Runner,
    set_default_openai_api,
    set_default_openai_client,
    set_trace_processors,
)
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.mcp import MCPServerStdio, MCPServerStdioParams
from agents.tracing import TracingProcessor
from dotenv import load_dotenv
from openai import AsyncOpenAI

from catalog_mcp_server import CATALOGS
from guardrails import build_handoff_payload, check_input, check_output, handoff_ready


PROJECT_FOLDER = Path(__file__).resolve().parent
load_dotenv(PROJECT_FOLDER / ".env")


class ConsoleTracingProcessor(TracingProcessor):
    """Print trace and span utilization without exporting to OpenAI."""

    def on_trace_start(self, trace):
        print(f"\n[trace] '{trace.name}' started")

    def on_trace_end(self, trace):
        print(f"[trace] '{trace.name}' finished")

    def on_span_start(self, span):
        pass

    def on_span_end(self, span):
        data = span.span_data.export()
        summary = f"  [span] {data.get('type', 'unknown')}"
        if data.get("name"):
            summary += f" - {data['name']}"
        if data.get("usage"):
            summary += f" | usage={data['usage']}"
        print(summary)

    def shutdown(self):
        pass

    def force_flush(self):
        pass


def configure_model_client() -> None:
    """Configure the NRP OpenAI-compatible endpoint used by the course examples."""
    base_url = os.getenv("NRP_BASE_URL")
    api_key = os.getenv("NRP_API_KEY")
    if not base_url or not api_key:
        raise RuntimeError("Set NRP_BASE_URL and NRP_API_KEY in .env before running the agent.")
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    set_default_openai_client(client, use_for_tracing=False)
    set_default_openai_api("chat_completions")
    set_trace_processors([ConsoleTracingProcessor()])


ALL_VENDORS = {item["vendor"] for products in CATALOGS.values() for item in products}


def _field(obj, name):
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def collect_tool_outputs(run_result) -> dict[str, str]:
    """Map each MCP tool name to its latest output from the analyst's run items."""
    names_by_call: dict[str, str] = {}
    outputs: dict[str, str] = {}
    for item in run_result.new_items:
        if isinstance(item, ToolCallItem):
            call_id = _field(item.raw_item, "call_id") or _field(item.raw_item, "id")
            names_by_call[call_id] = _field(item.raw_item, "name")
        elif isinstance(item, ToolCallOutputItem):
            name = names_by_call.get(_field(item.raw_item, "call_id"))
            if name:
                outputs[name] = item.output
    return outputs


def log(step: str, message: str) -> None:
    print(f"[{step}] {message}", file=sys.stderr)


async def ask_agent(question: str) -> str:
    """Run one question through the two-agent workflow and its MCP server."""
    allowed, reason = check_input(question)
    if not allowed:
        log("input-guardrail", f"blocked: {reason}")
        return reason
    configure_model_client()
    server_path = PROJECT_FOLDER / "catalog_mcp_server.py"
    async with MCPServerStdio(
        name="Vendor Catalog MCP",
        params=MCPServerStdioParams(
            command=sys.executable,
            args=[str(server_path)],
        ),
        client_session_timeout_seconds=90,
    ) as server:
        reviewer = Agent(
            name="Procurement Reviewer",
            instructions=(
                "You are the second-stage Procurement Reviewer. You receive a JSON handoff "
                "payload with catalog_evidence, retrieved_guidance, reasoning_trace, and the "
                "analyst_summary. Treat catalog_evidence as the only source of vendor facts. "
                "Correct any analyst claim that the evidence does not support, state separate "
                "lowest-price and highest-quality conclusions, explain material trade-offs "
                "using the retrieved guidance, and never place an order or name vendors "
                "outside the evidence."
            ),
            mcp_servers=[server],
            model="gpt-oss",
        )
        analyst = Agent(
            name="Catalog Analyst",
            instructions=(
                "You are the first-stage Catalog Analyst. For every product comparison, call "
                "sequential_reason, compare_vendor_catalogs, and retrieve_procurement_guidance. "
                "Present only evidence returned by those tools, including each vendor, price, "
                "pack size, material, and quality score. Pass the buyer's question to "
                "retrieve_procurement_guidance so it can retrieve the most relevant guidance. "
                "If the catalog tool returns an error, report the error and the available "
                "categories without guessing. End with a short evidence summary."
            ),
            mcp_servers=[server],
            model="gpt-oss",
        )
        log("analyst", "Catalog Analyst gathering evidence with MCP tools")
        evidence = await Runner.run(analyst, question, max_turns=25)
        tool_outputs = collect_tool_outputs(evidence)
        log("analyst", f"tools called: {sorted(tool_outputs) or 'none'}")

        payload = build_handoff_payload(question, tool_outputs, evidence.final_output)
        ready, reason = handoff_ready(payload)
        if not ready:
            log("handoff", f"not triggered: {reason}")
            return f"{reason}\n\nAnalyst notes:\n{evidence.final_output}"
        log("handoff", f"triggered for '{payload['product_category']}' with "
            f"{len(payload['catalog_evidence']['vendors'])} vendor records")

        review_request = (
            "Handoff payload from the Catalog Analyst (JSON):\n"
            f"{json.dumps(payload, indent=2)}\n\nPerform the final procurement review."
        )
        final_review = await Runner.run(reviewer, review_request, max_turns=25)
        answer = final_review.final_output

        violations = check_output(answer, payload, ALL_VENDORS)
        if violations:
            log("output-guardrail", f"retrying reviewer once: {violations}")
            retry_request = (
                f"{review_request}\n\nYour previous answer failed these checks: "
                f"{'; '.join(violations)}. Rewrite it using only the payload evidence."
            )
            answer = (await Runner.run(reviewer, retry_request, max_turns=25)).final_output
            violations = check_output(answer, payload, ALL_VENDORS)
            if violations:
                log("output-guardrail", f"still failing: {violations}")
                answer += "\n\n[Guardrail notice: " + "; ".join(violations) + ". Verify before acting.]"
        else:
            log("output-guardrail", "passed")
        return answer


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the vendor catalog comparison agent a question.")
    parser.add_argument("question", nargs="?", default="Compare holiday string lights across the vendors.")
    args = parser.parse_args()
    print(await ask_agent(args.question))


if __name__ == "__main__":
    asyncio.run(main())
