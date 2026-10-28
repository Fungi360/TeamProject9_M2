"""Run the M3 evaluation cases through the two-agent workflow (keyword stage).

Usage (from the repo root, with .env set):
    python eval/run_eval.py
Writes eval/results.csv. The critic-agent and human-review stages are added in M4.
"""

import asyncio
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vendor_catalog_agent import ask_agent  # noqa: E402


def keyword_check(case: dict, output: str) -> tuple[bool, str]:
    lowered = output.lower()
    missing = [k for k in case["must_include"] if k.lower() not in lowered]
    present = [k for k in case["must_exclude"] if k.lower() in lowered]
    notes = []
    if missing:
        notes.append(f"missing: {missing}")
    if present:
        notes.append(f"should not contain: {present}")
    return not notes, "; ".join(notes)


async def main() -> None:
    cases = json.loads((ROOT / "eval" / "m3_eval_cases.json").read_text())
    rows = []
    for case in cases:
        try:
            output = await ask_agent(case["input"])
        except Exception as exc:  # record the failure instead of stopping the suite
            output = f"ERROR: {exc}"
        passed, notes = keyword_check(case, output)
        rows.append({"id": case["id"], "input": case["input"], "expected": case["expected"],
                     "actual": output, "keyword_pass": passed, "notes": notes})
        print(f"{case['id']}: {'PASS' if passed else 'FAIL'} {notes}")
    with open(ROOT / "eval" / "results.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Keyword pass rate: {sum(r['keyword_pass'] for r in rows)}/{len(rows)}")


if __name__ == "__main__":
    asyncio.run(main())
