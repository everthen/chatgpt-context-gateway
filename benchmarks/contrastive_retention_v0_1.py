from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .selection_policy_v0_1 import select_context
except ImportError:
    from benchmarks.selection_policy_v0_1 import select_context


def load_suite(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def candidates(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in case["candidates"]}


def select_for_vector(case: dict[str, Any], vector: str) -> tuple[list[str], list[str], str]:
    items = candidates(case)

    if vector == "gold_only":
        selected = [k for k, v in items.items() if v["role"] == "supporting"]
        admitted = list(items)
        return admitted, selected, "EVALUATED"

    if vector == "score_greedy_2":
        admitted = list(items)
        selected = [
            item["key"]
            for item in sorted(
                case["candidates"],
                key=lambda x: (-x["semantic_score"], x["key"]),
            )[:2]
        ]
        return admitted, selected, "EVALUATED"

    if vector == "all_admitted":
        admitted = [
            item["key"]
            for item in case["candidates"]
            if item["admission"] in {"required", "optional"}
        ]
        return admitted, admitted.copy(), "EVALUATED"

    if vector == "contrastive_aware":
        admitted = [
            item["key"]
            for item in case["candidates"]
            if item["admission"] in {"required", "optional"}
        ]
        return admitted, list(case["minimal_sufficient_keys"]), "EVALUATED"

    if vector == "reference_selector":
        admitted = [
            item["key"]
            for item in case["candidates"]
            if item["admission"] in {"required", "optional"}
        ]
        decision = select_context(case["candidates"])
        return admitted, list(decision.selected_keys), "EVALUATED"

    if vector == "empty_admission_tu04":
        if case["case_id"] != "TU-04":
            return [], [], "NOT_APPLICABLE"
        return [], [], "UPSTREAM_ADMISSION_FAILURE"

    raise ValueError(f"unknown attack vector: {vector}")


def evaluate_case(
    case: dict[str, Any],
    admitted: list[str],
    selected: list[str],
    status: str,
) -> dict[str, Any]:
    expected = set(case["minimal_sufficient_keys"])
    selected_set = set(selected)
    must_drop = set(case.get("must_drop_keys", []))
    contrastive_required = {
        item["key"]
        for item in case["candidates"]
        if item["role"] == "contrastive" and item["key"] in expected
    }
    distractors = {
        item["key"]
        for item in case["candidates"]
        if item["role"] == "distractor"
    }

    if status == "UPSTREAM_ADMISSION_FAILURE":
        return {
            "case_id": case["case_id"],
            "status": status,
            "passed": (
                case.get("admission_attack", {}).get("empty_admission_expected_status")
                == status
            ),
            "selection_evaluable": False,
            "failure_owner": "admission",
            "selected_keys": selected,
            "admitted_keys": admitted,
        }

    if status == "NOT_APPLICABLE":
        return {
            "case_id": case["case_id"],
            "status": status,
            "passed": None,
            "selection_evaluable": False,
            "failure_owner": None,
            "selected_keys": selected,
            "admitted_keys": admitted,
        }

    required_recall = len(expected & selected_set) / len(expected) if expected else 1.0
    contrastive_retention = (
        len(contrastive_required & selected_set) / len(contrastive_required)
        if contrastive_required
        else 1.0
    )
    distractor_rejection = (
        len(distractors - selected_set) / len(distractors)
        if distractors
        else 1.0
    )
    selected_required_precision = (
        len(expected & selected_set) / len(selected_set) if selected_set else 0.0
    )
    passed = expected.issubset(selected_set) and must_drop.isdisjoint(selected_set)

    return {
        "case_id": case["case_id"],
        "status": status,
        "passed": passed,
        "selection_evaluable": True,
        "failure_owner": None if passed else "selection",
        "selected_keys": selected,
        "admitted_keys": admitted,
        "required_recall": round(required_recall, 4),
        "contrastive_retention": round(contrastive_retention, 4),
        "distractor_rejection": round(distractor_rejection, 4),
        "selected_required_precision": round(selected_required_precision, 4),
    }


def run_suite(suite: dict[str, Any], vector: str) -> dict[str, Any]:
    results = []
    for case in suite["cases"]:
        admitted, selected, status = select_for_vector(case, vector)
        results.append(evaluate_case(case, admitted, selected, status))

    applicable = [r for r in results if r["passed"] is not None]
    evaluable = [r for r in results if r["selection_evaluable"]]
    passed = sum(1 for r in applicable if r["passed"])
    contrastive = [
        r["contrastive_retention"]
        for r in evaluable
        if "contrastive_retention" in r
    ]
    required_recall = [
        r["required_recall"] for r in evaluable if "required_recall" in r
    ]
    distractor_rejection = [
        r["distractor_rejection"]
        for r in evaluable
        if "distractor_rejection" in r
    ]

    return {
        "schema_version": "ucg-contrastive-retention-result.v0.1",
        "suite_id": suite["suite_id"],
        "attack_vector": vector,
        "n_cases": len(results),
        "n_applicable": len(applicable),
        "n_passed": passed,
        "pass_rate": round(passed / len(applicable), 4) if applicable else None,
        "selection_evaluable_cases": len(evaluable),
        "mean_required_recall": (
            round(sum(required_recall) / len(required_recall), 4)
            if required_recall
            else None
        ),
        "mean_contrastive_retention": (
            round(sum(contrastive) / len(contrastive), 4)
            if contrastive
            else None
        ),
        "mean_distractor_rejection": (
            round(sum(distractor_rejection) / len(distractor_rejection), 4)
            if distractor_rejection
            else None
        ),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        type=Path,
        default=Path(__file__).resolve().parent
        / "attack_suites"
        / "contrastive_retention_v0_1.json",
    )
    parser.add_argument(
        "--vector",
        action="append",
        choices=[
            "gold_only",
            "score_greedy_2",
            "all_admitted",
            "contrastive_aware",
            "reference_selector",
            "empty_admission_tu04",
        ],
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    suite = load_suite(args.suite)
    vectors = args.vector or list(suite["attack_vectors"])
    report = {
        "schema_version": "ucg-contrastive-retention-benchmark.v0.1",
        "suite_id": suite["suite_id"],
        "vectors": [run_suite(suite, vector) for vector in vectors],
    }

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
