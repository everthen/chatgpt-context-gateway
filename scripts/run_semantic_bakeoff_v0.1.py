from __future__ import annotations

import hashlib
import json
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from context_gateway.benchmark.semantic_assessor import (
    build_semantic_assessment_prompt,
    normalize_semantic_response,
)
from scripts.run_semantic_worthiness_matrix import (
    blind_candidates,
    call_model,
    candidate_pool,
    gold_labels,
)


MODELS = (
    "ag/gemini-3.8-flash",
    "ag/gemini-3.8-flash-high",
    "oc/muse-spark-1.2-contributor-free",
    "oc/muse-spark-1.3-contributor-free",
)

CASE_IDS = ("LS-02", "NS-04", "XP-01", "TU-04")


def score(case: dict, result: dict, candidates: list[dict]) -> dict:
    gold = {x["candidate_id"]: x for x in gold_labels(case, candidates)}
    if result["status"] != "complete":
        return {"scorable": False}

    pred = {x["candidate_id"]: x for x in result["assessments"]}
    ids = list(gold)
    strict_gold = {k for k, v in gold.items() if v["task_fit"] != "none"}
    pred_support = {
        k
        for k, v in pred.items()
        if v["task_fit"] in {"direct", "supporting"} and v["provenance_complete"]
    }
    tp = len(strict_gold & pred_support)
    precision = tp / len(pred_support) if pred_support else 0.0
    recall = tp / len(strict_gold) if strict_gold else 1.0
    distractors = {k for k, v in gold.items() if v["task_fit"] == "none"}
    contextual = {
        k
        for k in distractors
        if pred[k]["task_fit"] == "contextual"
        or pred[k]["worthiness_role"] == "contextual"
    }
    return {
        "scorable": True,
        "protocol_compliant": bool(result.get("protocol_compliant")),
        "strict_support_precision": precision,
        "strict_support_recall": recall,
        "temporal_accuracy": sum(
            pred[k]["temporal_state"] == gold[k]["temporal_state"] for k in ids
        ) / len(ids),
        "exact_role_accuracy": sum(
            pred[k]["worthiness_role"] == gold[k]["worthiness_role"] for k in ids
        ) / len(ids),
        "contextual_on_distractor_rate": (
            len(contextual) / len(distractors) if distractors else 0.0
        ),
        "mean_confidence": statistics.mean(
            x["confidence"] for x in pred.values()
        ),
    }


def main() -> None:
    dataset = Path("/tmp/ucg-semantic-run/seed_v0.1.jsonl")
    checkpoint = Path("/tmp/ucg-semantic-run/bakeoff_v0.1.jsonl")
    output = Path("/tmp/ucg-semantic-run/bakeoff_v0.1.json")

    cases = {
        item["case_id"]: item
        for item in (
            json.loads(line)
            for line in dataset.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }

    api_key = Path("/tmp/ucg_semantic_benchmark_key").read_text().strip()
    rows = []

    jobs = []
    for model in MODELS:
        for case_id in CASE_IDS:
            case = cases[case_id]
            candidates = candidate_pool(case)
            jobs.append((model, case, candidates))

    def run(job):
        model, case, candidates = job
        result = call_model(
            base_url="http://127.0.0.1:20128",
            api_key=api_key,
            model=model,
            query=case["query"],
            candidates=candidates,
        )
        row = {
            "model": model,
            "case_id": case["case_id"],
            "candidate_count": len(candidates),
            "gold": gold_labels(case, candidates),
            "result": result,
        }
        row["metrics"] = score(case, result, candidates)
        return row

    checkpoint.write_text("", encoding="utf-8")
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            with checkpoint.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(
                row["model"],
                row["case_id"],
                row["result"]["status"],
                round(row["result"]["latency_ms"], 1),
                flush=True,
            )

    summary = {}
    for model in MODELS:
        complete = [
            row for row in rows
            if row["model"] == model and row["metrics"].get("scorable")
        ]
        if not complete:
            summary[model] = {"complete": 0}
            continue
        summary[model] = {
            "complete": len(complete),
            "protocol_compliance_rate": statistics.mean(
                row["metrics"]["protocol_compliant"] for row in complete
            ),
            "strict_support_precision": statistics.mean(
                row["metrics"]["strict_support_precision"] for row in complete
            ),
            "strict_support_recall": statistics.mean(
                row["metrics"]["strict_support_recall"] for row in complete
            ),
            "temporal_accuracy": statistics.mean(
                row["metrics"]["temporal_accuracy"] for row in complete
            ),
            "exact_role_accuracy": statistics.mean(
                row["metrics"]["exact_role_accuracy"] for row in complete
            ),
            "contextual_on_distractor_rate": statistics.mean(
                row["metrics"]["contextual_on_distractor_rate"] for row in complete
            ),
            "mean_confidence": statistics.mean(
                row["metrics"]["mean_confidence"] for row in complete
            ),
            "mean_latency_ms": statistics.mean(
                row["result"]["latency_ms"] for row in complete
            ),
        }
        print("SUMMARY", model, json.dumps(summary[model]), flush=True)

    output.write_text(
        json.dumps(
            {
                "schema_version": "ucg-semantic-bakeoff.v0.1",
                "candidate_source": "seed_corpus_full",
                "dataset_version": "seed_v0.1",
                "dataset_hash": hashlib.sha256(dataset.read_bytes()).hexdigest(),
                "case_ids": list(CASE_IDS),
                "models": list(MODELS),
                "summary": summary,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
