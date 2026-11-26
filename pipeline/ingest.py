"""Append GPU-notebook log lines (Kaggle/Colab: Wan 2.2, ACE-Step) to runs.jsonl so every model call lives in one log.

    python -m pipeline.ingest path/to/gpu_runs.jsonl
"""
from __future__ import annotations

import json
import sys

from .common import RUNS

REQUIRED = {"ts", "stage", "model", "status", "latency_s"}


def main(path: str) -> None:
    n = 0
    with open(path, encoding="utf-8") as src, open(RUNS, "a", encoding="utf-8") as dst:
        for line in src:
            if not line.strip():
                continue
            rec = json.loads(line)
            missing = REQUIRED - rec.keys()
            if missing:
                raise SystemExit(f"line {n + 1} missing {missing}")
            rec.setdefault("model_call", True)
            rec.setdefault("source", "gpu-notebook")
            dst.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"appended {n} lines to {RUNS.name}")


if __name__ == "__main__":
    main(sys.argv[1])
