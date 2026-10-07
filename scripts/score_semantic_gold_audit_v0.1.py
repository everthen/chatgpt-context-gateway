from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from context_gateway.benchmark.semantic_gold import derive_admission


def load_gold(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        case["case_id"]: case
        for case in payload["cases"]
    }


def score_row(
    *,
    gold_case: dict[str, Any],
    model_row: dict[str, Any],
) -> dict[str, Any]:
    labels = {
        item["evidence_key"]: item
        for item in gold_case["labels"]
    }
    predicted_by_key = {}
    for prediction, gold_label in zip(
        model_row["result"].get("assessments", []),
        [
            item
            for item in gold_case["labels"]
        ],
    ):
        predicted_by_key[gold_label["evidence_key"]] = prediction

    if len(predicted_by_key) != len(labels):
        return {"scorable": False, "reason": "assessment coverage mismatch"}

    role_correct = 0
    fit_correct = 0
    temporal_scored = 0
    temporal_correct = 0
    predicted_admission_correct = 0
    required_recall_hits = 0

    contradiction_gold = set()
    contradiction_pred = set()

    for evidence_key, gold in labels.items():
        pred = predicted_by_key[evidence_key]
        fit_correct += pred["task_fit"] == gold["task_fit"]
        role_correct += pred["worthiness_role"] == gold["worthiness_role"]

        if gold["temporal_state"] != "unknown":
            temporal_scored += 1
            temporal_correct += pred["temporal_state"] == gold["temporal_state"]

        expected_admission = gold["admission"]
        predicted_admission = derive_admission(
            task_fit=pred["task_fit"],
            worthiness_role=pred["worthiness_role"],
            temporal_state=pred["temporal_state"],
            query_mode=gold_case["query_mode"],
        )
        predicted_admission_correct += predicted_admission == expected_admission

        if gold["worthiness_role"] == "contradiction":
            contradiction_gold.add(evidence_key)
        if pred["worthiness_role"] == "contradiction":
            contradiction_pred.add(evidence_key)

        if gold["sufficiency_role"] == "required":
            if pred["task_fit"] in {"direct", "supporting"}:
                required_recall_hits += 1

    contradiction_tp = len(contradiction_gold & contradiction_pred)

    return {
        "scorable": True,
        "task_fit_accuracy": fit_correct / len(labels),
        "worthiness_role_accuracy": role_correct / len(labels),
        "temporal_accuracy": (
            temporal_correct / temporal_scored if temporal_scored else None
        ),
        "admission_accuracy": predicted_admission_correct / len(labels),
        "required_evidence_recall": (
            required_recall_hits
            / sum(
                label["sufficiency_role"] == "required"
                for label in labels.values()
            )
        ),
        "contradiction_precision": (
            contradiction_tp / len(contradiction_pred)
            if contradiction_pred
            else 1.0 if not contradiction_gold else 0.0
        ),
        "contradiction_recall": (
            contradiction_tp / len(contradiction_gold)
            if contradiction_gold
            else 1.0
        ),
    }


def main(
    *,
    gold_path: Path,
    results_path: Path,
    output_path: Path,
) -> None:
    gold = load_gold(gold_path)
    rows = [
        json.loads(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    scored = []
    for row in rows:
        case_id = row["case_id"]
        gold_case = gold[case_id]
        result = score_row(gold_case=gold_case, model_row=row)
        scored.append(
            {
                "model": row["model"],
                "case_id": case_id,
                "status": row["result"]["status"],
                "metrics": result,
            }
        )

    summary = {}
    for model in sorted({row["model"] for row in scored}):
        complete = [
            row for row in scored
            if row["model"] == model and row["metrics"].get("scorable")
        ]
        def avg(name: str) -> float | None:
            values = [
                row["metrics"][name]
                for row in complete
                if row["metrics"].get(name) is not None
            ]
            return statistics.mean(values) if values else None
        summary[model] = {
            "cases_scored": len(complete),
            "task_fit_accuracy": avg("task_fit_accuracy"),
            "worthiness_role_accuracy": avg("worthiness_role_accuracy"),
            "temporal_accuracy": avg("temporal_accuracy"),
            "admission_accuracy": avg("admission_accuracy"),
            "required_evidence_recall": avg("required_evidence_recall"),
            "contradiction_precision": avg("contradiction_precision"),
            "contradiction_recall": avg("contradiction_recall"),
        }

    output_path.write_text(
        json.dumps(
            {
                "schema_version": "ucg-semantic-gold-score.v0.1",
                "gold_path": str(gold_path),
                "results_path": str(results_path),
                "summary": summary,
                "case_results": scored,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    main(
        gold_path=args.gold,
        results_path=args.results,
        output_path=args.output,
    )
