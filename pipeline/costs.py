"""Summarise runs.jsonl per stage: calls, cache hits, errors, latency, GPU minutes, list-price equivalent.

    python -m pipeline.costs            # prints a Markdown table to paste into COSTS.md
"""
from __future__ import annotations

import json
from collections import defaultdict

from .common import RUNS


def main() -> None:
    rows = [json.loads(line) for line in RUNS.read_text(encoding="utf-8").splitlines() if line.strip()] if RUNS.exists() else []
    agg = defaultdict(lambda: {"calls": 0, "errors": 0, "cache_hits": 0, "placeholders": 0, "latency": [], "gpu_min": 0.0, "usd": 0.0})
    for r in rows:
        a = agg[(r["stage"], r["model"])]
        st = r["status"]
        if st == "ok":
            a["calls"] += 1
            if r.get("latency_s") is not None:
                a["latency"].append(r["latency_s"])
        elif st == "error":
            a["errors"] += 1
        elif st == "cache_hit":
            a["cache_hits"] += 1
        elif st == "placeholder":
            a["placeholders"] += 1
        elif st == "rendered" and r.get("latency_s") is not None:
            a["latency"].append(r["latency_s"])
        a["gpu_min"] += r.get("gpu_minutes") or 0
        a["usd"] += r.get("cost_usd_list_equiv") or 0
    print("| stage | model | ok calls | errors | cache hits | mean latency s | total s | GPU min | list-price USD |")
    print("|---|---|---|---|---|---|---|---|---|")
    for (stage, model), a in sorted(agg.items()):
        lat = a["latency"]
        mean = f"{sum(lat) / len(lat):.1f}" if lat else "-"
        print(f"| {stage} | {model} | {a['calls']} | {a['errors']} | {a['cache_hits']} | {mean} | {sum(lat):.0f} | "
              f"{a['gpu_min']:.1f} | {a['usd']:.4f} |")
    print(f"\n{len(rows)} log lines, {len({r['run_id'] for r in rows})} runs")


if __name__ == "__main__":
    main()
