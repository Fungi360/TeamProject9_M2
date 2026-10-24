"""Agent that uses the vendor catalog MCP tool."""

import argparse
import asyncio
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
from agents.mcp import MCPServerStdio, MCPServerStdioParams
from agents.tracing import TracingProcessor
from dotenv import load_dotenv
from openai import AsyncOpenAI


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


async def ask_agent(question: str) -> str:
    """Run one question through the agent and its MCP server."""
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
                "You are the second-stage procurement reviewer. Review the Catalog Analyst's "
                "evidence and preserve its factual recommendations. Correct unsupported claims, "
                "state separate lowest-price and highest-quality conclusions, explain material "
                "trade-offs, and do not place an order or invent vendor data."
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
                "pack size, material, and quality score. Hand off to Procurement Reviewer "
                "after producing the evidence summary."
            ),
            mcp_servers=[server],
            model="gpt-oss",
        )
        evidence = await Runner.run(analyst, question, max_turns=25)
        review_request = (
            f"Original buyer question: {question}\n\n"
            f"Catalog Analyst evidence to review:\n{evidence.final_output}\n\n"
            "Perform the final procurement review."
        )
        final_review = await Runner.run(reviewer, review_request, max_turns=25)
        return final_review.final_output


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the vendor catalog comparison agent a question.")
    parser.add_argument("question", nargs="?", default="Compare holiday string lights across the vendors.")
    args = parser.parse_args()
    print(await ask_agent(args.question))


if __name__ == "__main__":
    asyncio.run(main())
