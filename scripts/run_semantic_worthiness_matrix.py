from __future__ import annotations

import hashlib
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from context_gateway.benchmark.semantic_assessor import (
    build_semantic_assessment_prompt,
    normalize_semantic_response,
)


DEFAULT_MODELS = (
    "ag/gemini-3.8-flash",
    "ag/gemini-3.8-flash-high",
    "oc/muse-spark-1.2-contributor-free",
    "oc/muse-spark-1.3-contributor-free",
)


def candidate_pool(case: dict) -> list[dict]:
    candidates = []
    for conversation in case["corpus"]["conversations"]:
        for message in conversation.get("messages", []):
            candidates.append(
                {
                    "evidence_key": message["evidence_key"],
                    "excerpt": message.get("text", ""),
                    "provider": conversation.get("provider", ""),
                    "account_id": conversation.get("account_id", ""),
                    "conversation_id": conversation.get("conversation_id", ""),
                    "message_id": message.get("message_id", ""),
                    "observed_at": message.get(
                        "create_time", conversation.get("create_time")
                    ),
                }
            )
    return candidates


def blind_candidates(candidates: list[dict]) -> list[dict]:
    return [
        {
            "candidate_id": f"C{index}",
            "text": candidate["excerpt"],
            "provider": candidate["provider"],
            "account_id": candidate["account_id"],
            "conversation_id": candidate["conversation_id"],
            "message_id": candidate["message_id"],
            "observed_at": candidate["observed_at"],
        }
        for index, candidate in enumerate(candidates, 1)
    ]


def gold_labels(case: dict, candidates: list[dict]) -> list[dict]:
    direct = {item["evidence_key"] for item in case["gold_evidence"]}
    supporting = {item["evidence_key"] for item in case["supporting_evidence"]}
    obsolete = set(case.get("temporal_state", {}).get("obsolete", []))
    current = set(case.get("temporal_state", {}).get("current", []))
    proposed = set(case.get("temporal_state", {}).get("proposed", []))

    labels = []
    for index, candidate in enumerate(candidates, 1):
        key = candidate["evidence_key"]
        if key in direct:
            task_fit, role = "direct", "direct_support"
        elif key in supporting:
            task_fit, role = "supporting", "supporting"
        else:
            task_fit, role = "none", "none"

        if key in obsolete:
            temporal = "obsolete"
        elif key in current:
            temporal = "current"
        elif key in proposed:
            temporal = "proposed"
        else:
            temporal = "unknown"

        labels.append(
            {
                "candidate_id": f"C{index}",
                "evidence_key": key,
                "task_fit": task_fit,
                "worthiness_role": role,
                "temporal_state": temporal,
            }
        )
    return labels


def call_model(
    *,
    base_url: str,
    api_key: str,
    model: str,
    query: str,
    candidates: list[dict],
    timeout_seconds: float = 90.0,
) -> dict:
    blind = blind_candidates(candidates)
    request = build_semantic_assessment_prompt(query, tuple(
        type("_Blind", (), {"candidate_id": item["candidate_id"],
                            "text": item["text"],
                            "provider": item["provider"],
                            "account_id": item["account_id"],
                            "conversation_id": item["conversation_id"],
                            "message_id": item["message_id"],
                            "observed_at": item["observed_at"],
                            "as_dict": lambda self: {
                                "candidate_id": self.candidate_id,
                                "text": self.text,
                                "provider": self.provider,
                                "account_id": self.account_id,
                                "conversation_id": self.conversation_id,
                                "message_id": self.message_id,
                                "observed_at": self.observed_at,
                            }})()
        for item in blind
    ))
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 2048,
        "stream": False,
        "messages": [{"role": "user", "content": request.prompt}],
    }
    started = time.perf_counter()
    http_request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    result = {
        "model": model,
        "prompt_hash": request.prompt_hash,
        "request": payload,
        "latency_ms": 0.0,
    }
    try:
        with urllib.request.urlopen(http_request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        result["raw_response"] = raw
        content = json.loads(raw)["choices"][0]["message"]["content"]
        result["model_content"] = str(content)
        assessments, protocol_compliant = normalize_semantic_response(
            str(content), request
        )
        result.update(
            {
                "status": "complete",
                "protocol_compliant": protocol_compliant,
                "assessments": [
                    {
                        "candidate_id": item.candidate_id,
                        "task_fit": item.task_fit,
                        "worthiness_role": item.worthiness_role,
                        "temporal_state": item.temporal_state,
                        "claim_ids": list(item.claim_ids),
                        "conflict_group": item.conflict_group,
                        "redundancy_group": item.redundancy_group,
                        "provenance_complete": item.provenance_complete,
                        "confidence": item.confidence,
                    }
                    for item in assessments
                ],
            }
        )
    except urllib.error.HTTPError as exc:
        result.update(
            {
                "status": "http_error",
                "error": f"HTTP {exc.code}",
                "raw_response": exc.read().decode("utf-8", "replace")[:3000],
            }
        )
    except Exception as exc:
        result.update(
            {
                "status": "parse_or_runtime_error",
                "error": str(exc),
                "raw_response": None,
            }
        )
    result["latency_ms"] = (time.perf_counter() - started) * 1000
    return result


def score_case(case: dict, result: dict, candidates: list[dict]) -> dict:
    gold = {item["candidate_id"]: item for item in gold_labels(case, candidates)}
    if result["status"] != "complete":
        return {
            "scorable": False,
            "protocol_compliant": False,
        }

    predicted = {item["candidate_id"]: item for item in result["assessments"]}
    ids = list(gold)

    strict_gold = {key for key, value in gold.items() if value["task_fit"] != "none"}
    predicted_support = {
        key
        for key, value in predicted.items()
        if value["task_fit"] in {"direct", "supporting"}
        and value["provenance_complete"]
    }
    true_support = strict_gold & predicted_support

    strict_precision = (
        len(true_support) / len(predicted_support)
        if predicted_support
        else 0.0
    )
    strict_recall = (
        len(true_support) / len(strict_gold)
        if strict_gold
        else 1.0
    )

    distractors = {
        key for key, value in gold.items() if value["task_fit"] == "none"
    }
    contextual_on_distractors = {
        key
        for key in distractors
        if predicted[key]["task_fit"] == "contextual"
        or predicted[key]["worthiness_role"] == "contextual"
    }
    protocol = bool(result.get("protocol_compliant"))

    return {
        "scorable": True,
        "protocol_compliant": protocol,
        "strict_support_precision": strict_precision,
        "strict_support_recall": strict_recall,
        "temporal_accuracy": sum(
            predicted[key]["temporal_state"] == gold[key]["temporal_state"]
            for key in ids
        ) / len(ids),
        "exact_role_accuracy": sum(
            predicted[key]["worthiness_role"] == gold[key]["worthiness_role"]
            for key in ids
        ) / len(ids),
        "contextual_on_distractor_rate": (
            len(contextual_on_distractors) / len(distractors)
            if distractors
            else 0.0
        ),
        "mean_confidence": statistics.mean(
            item["confidence"] for item in predicted.values()
        ),
    }


def run_matrix(
    *,
    dataset_path: Path,
    output_path: Path,
    base_url: str,
    api_key: str,
    models: tuple[str, ...] = DEFAULT_MODELS,
) -> None:
    cases = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    dataset_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()

    def one(model: str, case: dict) -> dict:
        candidates = candidate_pool(case)
        result = call_model(
            base_url=base_url,
            api_key=api_key,
            model=model,
            query=case["query"],
            candidates=candidates,
        )
        result.update(
            {
                "case_id": case["case_id"],
                "query": case["query"],
                "candidate_count": len(candidates),
                "gold": gold_labels(case, candidates),
            }
        )
        metrics = score_case(case, result, candidates)
        result["metrics"] = metrics
        return result

    results = []
    with ThreadPoolExecutor(max_workers=min(2, len(models))) as executor:
        futures = {
            executor.submit(one, model, case): (model, case["case_id"])
            for model in models
            for case in cases
        }
        for future in as_completed(futures):
            model, case_id = futures[future]
            result = future.result()
            results.append(result)
            print(
                model,
                case_id,
                result["status"],
                round(result["latency_ms"], 1),
                flush=True,
            )

    summary = {}
    for model in models:
        rows = [item for item in results if item["model"] == model]
        complete = [item for item in rows if item["metrics"].get("scorable")]
        def avg(name: str) -> float:
            return (
                statistics.mean(item["metrics"][name] for item in complete)
                if complete
                else 0.0
            )
        summary[model] = {
            "cases_total": len(rows),
            "complete": len(complete),
            "protocol_compliance_rate": (
                statistics.mean(
                    item["metrics"]["protocol_compliant"] for item in complete
                )
                if complete
                else 0.0
            ),
            "strict_support_precision": avg("strict_support_precision"),
            "strict_support_recall": avg("strict_support_recall"),
            "temporal_accuracy": avg("temporal_accuracy"),
            "exact_role_accuracy": avg("exact_role_accuracy"),
            "contextual_on_distractor_rate": avg("contextual_on_distractor_rate"),
            "mean_confidence": avg("mean_confidence"),
            "mean_latency_ms": (
                statistics.mean(item["latency_ms"] for item in complete)
                if complete
                else 0.0
            ),
            "median_latency_ms": (
                statistics.median(item["latency_ms"] for item in complete)
                if complete
                else 0.0
            ),
        }
        print("SUMMARY", model, json.dumps(summary[model]), flush=True)

    output_path.write_text(
        json.dumps(
            {
                "schema_version": "ucg-semantic-worthiness-run.v0.1",
                "candidate_source": "seed_corpus_full",
                "dataset_version": "seed_v0.1",
                "dataset_hash": dataset_hash,
                "endpoint": base_url,
                "models": list(models),
                "temperature": 0,
                "max_tokens": 2048,
                "case_count": len(cases),
                "summary": summary,
                "case_results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
