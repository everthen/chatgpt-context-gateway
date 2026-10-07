from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import run_ucg_retrieval_benchmark
from .schema import load_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic UCG retrieval benchmark.")
    parser.add_argument(
        "dataset",
        nargs="?",
        default="benchmarks/data/seed_v0.1.jsonl",
        help="Path to a JSONL/JSON benchmark dataset.",
    )
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    cases = load_dataset(Path(args.dataset))
    result = run_ucg_retrieval_benchmark(
        cases,
        limit=max(1, min(args.limit, 50)),
        output_dir=args.output_dir,
    )
    print(json.dumps({
        "dataset_cases": result["dataset_cases"],
        "runnable_arms": result["runnable_arms"],
        "aggregate": result["aggregate"],
    }, indent=2))


if __name__ == "__main__":
    main()
