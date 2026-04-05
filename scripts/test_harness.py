#!/usr/bin/env python3
"""
Test harness for OAN backend - runs standardized queries and reports metrics.
Usage: python scripts/test_harness.py [--url http://localhost:8000]
"""
import argparse
import time
import requests

TEST_CASES = [
    {"query": "What is the price of teff in Adama?", "category": "crop_price"},
    {"query": "What is the price of oxen in Dubti?", "category": "livestock_price"},
    {"query": "What is the correct crop width for teff?", "category": "rag_knowledge"},
    {"query": "What is the treatment for mastitis?", "category": "rag_knowledge"},
    {"query": "How to prepare land for maize planting?", "category": "rag_knowledge"},
    {"query": "What is the weather forecast for Adama?", "category": "weather"},
    {"query": "List all crops available in Bishoftu", "category": "market_list"},
    {"query": "Hello, what can you help me with?", "category": "greeting"},
]


def run_test(url: str, test_case: dict, index: int) -> dict:
    """Run a single test case and return results."""
    payload = {
        "query": test_case["query"],
        "session_id": f"test_harness_{index}",
        "source_lang": "en",
        "target_lang": "en",
    }
    start = time.perf_counter()
    try:
        resp = requests.post(f"{url}/api/chat/", json=payload, timeout=120)
        elapsed_ms = (time.perf_counter() - start) * 1000
        resp.raise_for_status()
        data = resp.json()
        metrics = data.get("metrics", {})
        response_text = data.get("response", "")
        preview = response_text[:80].replace("\n", " ")
        return {
            "index": index,
            "query": test_case["query"],
            "category": test_case["category"],
            "status": data.get("status", "unknown"),
            "e2e_ms": round(elapsed_ms, 1),
            "llm_ms": metrics.get("llm_total_time", 0),
            "tools": metrics.get("tool_calls", 0),
            "prompt_tokens": metrics.get("prompt_tokens", 0),
            "completion_tokens": metrics.get("completion_tokens", 0),
            "total_tokens": metrics.get("total_tokens", 0),
            "response_preview": preview,
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "index": index,
            "query": test_case["query"],
            "category": test_case["category"],
            "status": "error",
            "e2e_ms": round(elapsed_ms, 1),
            "llm_ms": 0,
            "tools": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "response_preview": str(e)[:80],
        }


def print_report(results: list):
    """Print markdown-formatted report table."""
    header = "| # | Category | Status | E2E ms | LLM ms | Tools | Tokens P/C/T | Response |"
    sep = "|---|----------|--------|--------|--------|-------|--------------|----------|"
    print(f"\n{'='*120}")
    print("OAN Backend Test Harness Report")
    print(f"{'='*120}\n")
    print(header)
    print(sep)

    total_e2e = 0
    total_llm = 0
    total_tools = 0
    total_pt = 0
    total_ct = 0
    total_tt = 0

    for r in results:
        tokens = f"{r['prompt_tokens']}/{r['completion_tokens']}/{r['total_tokens']}"
        preview = r["response_preview"][:60]
        print(
            f"| {r['index']} | {r['category']:<14} | {r['status']:<6} | "
            f"{r['e2e_ms']:>6} | {r['llm_ms']:>6} | {r['tools']:>5} | "
            f"{tokens:>12} | {preview} |"
        )
        total_e2e += r["e2e_ms"]
        total_llm += r["llm_ms"]
        total_tools += r["tools"]
        total_pt += r["prompt_tokens"]
        total_ct += r["completion_tokens"]
        total_tt += r["total_tokens"]

    count = len(results)
    totals_tokens = f"{total_pt}/{total_ct}/{total_tt}"
    print(sep)
    print(
        f"| **TOTALS** | | "
        f"{sum(1 for r in results if r['status']=='success')}/{count} ok | "
        f"{total_e2e/count:>6.0f} avg | {total_llm/count:>6.0f} avg | "
        f"{total_tools:>5} | {totals_tokens:>12} | |"
    )
    print(f"\n{'='*120}\n")


def main():
    parser = argparse.ArgumentParser(description="OAN Backend Test Harness")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the backend")
    args = parser.parse_args()

    print(f"Running {len(TEST_CASES)} test cases against {args.url} ...\n")
    results = []
    for i, tc in enumerate(TEST_CASES, 1):
        print(f"  [{i}/{len(TEST_CASES)}] {tc['category']}: {tc['query'][:50]}...")
        result = run_test(args.url, tc, i)
        results.append(result)
        status_icon = "OK" if result["status"] == "success" else "FAIL"
        print(f"         -> {status_icon} in {result['e2e_ms']:.0f}ms")

    print_report(results)


if __name__ == "__main__":
    main()
