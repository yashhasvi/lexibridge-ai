"""
ask.py — Interactive test script for the Brain Module API.

Usage:
    # Run all questions from questions.txt
    python ask.py

    # Ask a single question directly
    python ask.py "What is memory management?"

    # Ask with custom top_k
    python ask.py "What is memory management?" --top_k 8

    # Skip cache (force fresh retrieval)
    python ask.py "What is memory management?" --no-cache

    # Run all questions but skip ones already cached
    python ask.py --all

    # Run all questions, forcing fresh retrieval for each
    python ask.py --all --no-cache
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx not found. Install it: pip install httpx")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = "http://127.0.0.1:8001"
QUESTIONS_FILE = Path(__file__).parent / "questions.txt"
DEFAULT_TOP_K = 5
REQUEST_TIMEOUT = 180  # seconds — Ollama is slow on CPU

# ── Helpers ───────────────────────────────────────────────────────────────────

def ask(question: str, top_k: int = DEFAULT_TOP_K, use_cache: bool = True) -> dict:
    payload = {"question": question, "top_k": top_k, "use_cache": use_cache}
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        resp = client.post(f"{BASE_URL}/ask", json=payload)
        resp.raise_for_status()
        return resp.json()


def print_result(q: str, d: dict, idx: int | None = None) -> None:
    prefix = f"[Q{idx}]" if idx is not None else "[Q]"
    from_cache = d.get("_from_cache", False)
    cache_tag = " \033[32m(cache hit)\033[0m" if from_cache else " \033[33m(cold)\033[0m"
    latency = d.get("latency_ms", 0)

    print(f"\n{'─'*70}")
    print(f"{prefix} \033[1m{q}\033[0m{cache_tag}")
    print(f"{'─'*70}")
    print(f"  Answer     : {d.get('answer', 'N/A')[:400]}")
    print(f"  Confidence : {d.get('confidence', 0):.4f}")
    print(f"  Latency    : {latency:,.0f} ms")
    print(f"  Intent     : {d.get('routing', {}).get('intent', '?')}  "
          f"complexity={d.get('routing', {}).get('complexity', '?')}")
    print(f"  Fetchers   : {d.get('routing', {}).get('fetchers_used', [])}")
    print(f"  Sources    : {len(d.get('sources', []))}")
    if d.get("error"):
        print(f"  \033[31mError\033[0m      : {d['error']}")


def load_questions() -> list[str]:
    if not QUESTIONS_FILE.exists():
        print(f"questions.txt not found at {QUESTIONS_FILE}")
        sys.exit(1)
    lines = QUESTIONS_FILE.read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Brain Module test client")
    parser.add_argument("question", nargs="?", help="Single question to ask")
    parser.add_argument("--top_k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--no-cache", action="store_true", help="Bypass cache")
    parser.add_argument("--all", action="store_true", help="Run all questions from questions.txt")
    args = parser.parse_args()

    use_cache = not args.no_cache

    # health check
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        r.raise_for_status()
    except Exception as e:
        print(f"\033[31mServer not reachable at {BASE_URL}: {e}\033[0m")
        sys.exit(1)

    if args.question:
        # single question mode
        print(f"\nAsking: {args.question}")
        t0 = time.time()
        result = ask(args.question, top_k=args.top_k, use_cache=use_cache)
        wall = (time.time() - t0) * 1000
        print_result(args.question, result)
        print(f"\n  Wall time  : {wall:,.0f} ms\n")

    else:
        # batch mode — run all questions from questions.txt
        questions = load_questions()
        print(f"\nRunning {len(questions)} questions against {BASE_URL}\n")
        total_cold_ms = 0
        total_cache_ms = 0
        cold_count = cache_count = 0

        for i, q in enumerate(questions, 1):
            print(f"\n[{i}/{len(questions)}] Asking...")
            t0 = time.time()
            try:
                result = ask(q, top_k=args.top_k, use_cache=use_cache)
                wall = (time.time() - t0) * 1000
                print_result(q, result, idx=i)
                print(f"  Wall time  : {wall:,.0f} ms")
                if result.get("_from_cache"):
                    cache_count += 1
                    total_cache_ms += wall
                else:
                    cold_count += 1
                    total_cold_ms += wall
            except Exception as e:
                print(f"\n  \033[31mFailed: {e}\033[0m")

        # summary
        print(f"\n{'═'*70}")
        print(f"  Summary: {len(questions)} questions")
        if cold_count:
            print(f"  Cold hits   : {cold_count}  avg {total_cold_ms/cold_count:,.0f} ms")
        if cache_count:
            print(f"  Cache hits  : {cache_count}  avg {total_cache_ms/cache_count:,.0f} ms")
        print(f"{'═'*70}\n")


if __name__ == "__main__":
    main()
