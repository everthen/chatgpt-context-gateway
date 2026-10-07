from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time
from tempfile import TemporaryDirectory
from typing import Any, Callable

from ..db import ArchiveDB
from ..normalize import make_record
from ..continuity import continuity
from .metrics import aggregate, score_context_quality, score_retrieval
from .schema import BenchmarkCase
from .selection import (
    ContextWorthinessPolicy,
    EvidenceAdmissionConfig,
    admit_rrf_candidates,
    select_context_worthy,
)


@dataclass(frozen=True)
class ArmDefinition:
    name: str
    description: str
    status: str


EXPERIMENT_ARMS = (
    ArmDefinition("oracle", "Gold evidence supplied directly to the model.", "interface"),
    ArmDefinition("native", "Native model context/memory without UCG.", "interface"),
    ArmDefinition("ucg", "Native context plus explicit UCG retrieval.", "runnable"),
)


@dataclass
class CaseResult:
    case_id: str
    task_family: str
    difficulty: str
    arm: str
    query: str
    returned: list[dict[str, Any]]
    retrieval: dict[str, float]
    context: dict[str, float]
    latency_ms: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _conversation_payload(conv: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    previous_node: str | None = None
    messages = conv.get("messages") or []
    for index, message in enumerate(messages):
        node_id = f"node-{conv['conversation_id']}-{index}"
        msg_id = str(message["message_id"])
        nodes[node_id] = {
            "id": node_id,
            "parent": previous_node,
            "children": [],
            "message": {
                "id": msg_id,
                "author": {"role": message.get("role", "user")},
                "content": {"content_type": "text", "parts": [message["text"]]},
                "create_time": message.get("create_time"),
            },
        }
        if previous_node:
            nodes[previous_node]["children"] = [node_id]
        previous_node = node_id

    return {
        "id": conv["conversation_id"],
        "title": conv.get("title") or conv["conversation_id"],
        "create_time": conv.get("create_time"),
        "update_time": conv.get("update_time"),
        "mapping": nodes,
        "current_node": previous_node,
    }


def seed_case_db(db: ArchiveDB, case: BenchmarkCase) -> dict[str, dict[str, Any]]:
    resolved: dict[str, dict[str, Any]] = {}
    corpus = case.corpus
    for conv in corpus.get("conversations", []):
        payload = _conversation_payload(conv)
        record = make_record(
            payload,
            project_id=str(conv.get("project_id", "benchmark")),
            project_name=str(conv.get("project_name", "UCG Benchmark")),
            raw_path=(
                f"benchmark://{conv.get('provider','chatgpt')}/"
                f"{conv.get('account_id','default')}/{conv['conversation_id']}/snapshot-001.json"
            ),
            provider=str(conv.get("provider", "chatgpt")),
            account_id=str(conv.get("account_id", "default")),
            source="benchmark",
            captured_at=float(conv.get("update_time") or time.time()),
        )
        db.upsert_conversation(record)

        for message in conv.get("messages", []):
            key = str(message["evidence_key"])
            resolved[key] = {
                "provider": record["provider"],
                "account_id": record["account_id"],
                "id": record["id"],
                "conversation_uid": record["conversation_uid"] if "conversation_uid" in record else None,
                "message_id": str(message["message_id"]),
            }
    return resolved


def _returned_with_keys(
    hits: list[dict[str, Any]],
    case: BenchmarkCase,
) -> list[dict[str, Any]]:
    reverse = {
        (ref.provider, ref.account_id, ref.conversation_id, ref.message_id): ref.evidence_key
        for ref in case.gold_evidence + case.supporting_evidence + case.distractors
    }
    output = []
    for hit in hits:
        key = reverse.get(
            (
                hit["provider"],
                hit["account_id"],
                hit["id"],
                hit["message_id"],
            )
        )
        item = dict(hit)
        item["evidence_key"] = key or f"unmapped:{hit['evidence_id']}"
        output.append(item)
    return output




_DECOMPOSE_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in",
    "is", "of", "on", "or", "the", "to", "who", "what", "when", "why",
    "with", "after", "before", "current", "latest", "preferred",
}


def lexical_decompose_query(query: str, max_subqueries: int = 3) -> tuple[str, ...]:
    """Cheap deterministic decomposition control; not semantic query planning."""
    tokens = [token.strip(".,:;!?()[]{}").lower() for token in query.split()]
    content = [token for token in tokens if token and token not in _DECOMPOSE_STOPWORDS]
    candidates = [query.strip()]
    if len(content) >= 2:
        candidates.append(" ".join(content[:2]))
        candidates.append(" ".join(content[-2:]))
    elif content:
        candidates.append(content[0])
    seen: set[str] = set()
    output: list[str] = []
    for item in candidates:
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            output.append(item)
        if len(output) >= max_subqueries:
            break
    return tuple(output)


def _automatic_multi_query_returned(
    db: ArchiveDB,
    case: BenchmarkCase,
    limit: int,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    by_evidence: dict[str, dict[str, Any]] = {}
    rrf_scores: dict[str, float] = {}
    subqueries = lexical_decompose_query(case.query)
    for query_index, subquery in enumerate(subqueries):
        hits = db.search_detailed(subquery, limit=limit)
        for rank, hit in enumerate(hits, start=1):
            key = (
                f"{hit['provider']}|{hit['account_id']}|"
                f"{hit['id']}|{hit['message_id']}"
            )
            item = by_evidence.setdefault(key, dict(hit))
            support = item.setdefault("query_support", [])
            support.append({"query_index": query_index, "query": subquery, "rank": rank})
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (60 + rank))
    ranked = sorted(
        by_evidence.values(),
        key=lambda item: (-rrf_scores[
            f"{item['provider']}|{item['account_id']}|{item['id']}|{item['message_id']}"
        ], item.get("score", 0)),
    )[:limit]
    return _returned_with_keys(ranked, case), (time.perf_counter() - started) * 1000


def run_ucg_auto_assembly_case(
    db: ArchiveDB, case: BenchmarkCase, limit: int = 8
) -> CaseResult:
    returned, latency_ms = _automatic_multi_query_returned(db, case, limit)
    gold = {ref.evidence_key for ref in case.gold_evidence}
    allowed = gold | {ref.evidence_key for ref in case.supporting_evidence}
    return CaseResult(
        case_id=case.case_id,
        task_family=case.task_family,
        difficulty=case.difficulty,
        arm="ucg_auto_assembly",
        query=case.query,
        returned=returned,
        retrieval=score_retrieval(returned, gold, k=limit),
        context=score_context_quality(returned, allowed_keys=allowed),
        latency_ms=latency_ms,
    )

def _multi_query_returned(
    db: ArchiveDB,
    case: BenchmarkCase,
    limit: int,
) -> tuple[list[dict[str, Any]], float]:
    """Retrieve per sub-query, then union/dedupe while preserving best rank."""
    started = time.perf_counter()
    by_evidence: dict[str, dict[str, Any]] = {}
    rrf_scores: dict[str, float] = {}

    for query_index, subquery in enumerate(case.retrieval_queries):
        hits = db.search_detailed(subquery, limit=limit)
        for rank, hit in enumerate(hits, start=1):
            key = (
                f"{hit['provider']}|{hit['account_id']}|"
                f"{hit['id']}|{hit['message_id']}"
            )
            item = by_evidence.setdefault(key, dict(hit))
            support = item.setdefault("query_support", [])
            support.append({"query_index": query_index, "query": subquery, "rank": rank})
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (60 + rank))

    ranked = sorted(
        by_evidence.values(),
        key=lambda item: (-rrf_scores[
            f"{item['provider']}|{item['account_id']}|{item['id']}|{item['message_id']}"
        ], item.get("score", 0)),
    )[:limit]
    return _returned_with_keys(ranked, case), (time.perf_counter() - started) * 1000


def run_ucg_assembly_case(db: ArchiveDB, case: BenchmarkCase, limit: int = 8) -> CaseResult:
    returned, latency_ms = _multi_query_returned(db, case, limit)
    gold = {ref.evidence_key for ref in case.gold_evidence}
    allowed = gold | {ref.evidence_key for ref in case.supporting_evidence}
    return CaseResult(
        case_id=case.case_id,
        task_family=case.task_family,
        difficulty=case.difficulty,
        arm="ucg_assembly",
        query=case.query,
        returned=returned,
        retrieval=score_retrieval(returned, gold, k=limit),
        context=score_context_quality(returned, allowed_keys=allowed),
        latency_ms=latency_ms,
    )

def _annotate_with_benchmark_oracle(
    items: list[dict[str, Any]],
    case: BenchmarkCase,
) -> list[dict[str, Any]]:
    gold = {ref.evidence_key for ref in case.gold_evidence}
    supporting = {ref.evidence_key for ref in case.supporting_evidence}
    obsolete = set(case.temporal_state.get("obsolete", []))
    current = set(case.temporal_state.get("current", []))
    annotated: list[dict[str, Any]] = []

    for item in items:
        key = item.get("evidence_key")
        output = dict(item)
        if key in gold:
            output["task_fit"] = "direct"
            output["worthiness_role"] = "direct_support"
        elif key in supporting:
            output["task_fit"] = "supporting"
            output["worthiness_role"] = "supporting"
        else:
            output["task_fit"] = "none"
            output["worthiness_role"] = "none"

        if key in obsolete:
            output["temporal_state"] = "obsolete"
        elif key in current:
            output["temporal_state"] = "current"
        else:
            output["temporal_state"] = "current"
        output["provenance_complete"] = True
        annotated.append(output)

    return annotated


def run_ucg_worthiness_oracle_case(
    db: ArchiveDB,
    case: BenchmarkCase,
    *,
    candidate_limit: int = 8,
    config: ContextWorthinessPolicy = ContextWorthinessPolicy(final_limit=4),
) -> CaseResult:
    candidates, latency_ms = _automatic_multi_query_returned(db, case, candidate_limit)
    annotated = _annotate_with_benchmark_oracle(candidates, case)
    returned = select_context_worthy(annotated, policy=config)
    gold = {ref.evidence_key for ref in case.gold_evidence}
    allowed = gold | {ref.evidence_key for ref in case.supporting_evidence}
    return CaseResult(
        case_id=case.case_id,
        task_family=case.task_family,
        difficulty=case.difficulty,
        arm="ucg_worthiness_oracle",
        query=case.query,
        returned=returned,
        retrieval=score_retrieval(returned, gold, k=config.final_limit),
        context=score_context_quality(returned, allowed_keys=allowed),
        latency_ms=latency_ms,
    )


def run_ucg_admission_case(
    db: ArchiveDB,
    case: BenchmarkCase,
    *,
    candidate_limit: int = 8,
    config: EvidenceAdmissionConfig = EvidenceAdmissionConfig(),
) -> CaseResult:
    candidates, latency_ms = _automatic_multi_query_returned(db, case, candidate_limit)
    returned = admit_rrf_candidates(candidates, config=config)
    gold = {ref.evidence_key for ref in case.gold_evidence}
    allowed = gold | {ref.evidence_key for ref in case.supporting_evidence}
    return CaseResult(
        case_id=case.case_id,
        task_family=case.task_family,
        difficulty=case.difficulty,
        arm="ucg_admission",
        query=case.query,
        returned=returned,
        retrieval=score_retrieval(returned, gold, k=config.final_limit),
        context=score_context_quality(returned, allowed_keys=allowed),
        latency_ms=latency_ms,
    )


def run_ucg_case(db: ArchiveDB, case: BenchmarkCase, limit: int = 8) -> CaseResult:
    started = time.perf_counter()
    bundle = continuity(db, case.query, limit=limit)
    returned = _returned_with_keys(bundle["evidence"], case)
    gold = {ref.evidence_key for ref in case.gold_evidence}
    allowed = gold | {ref.evidence_key for ref in case.supporting_evidence}
    retrieval = score_retrieval(returned, gold, k=limit)
    context = score_context_quality(returned, allowed_keys=allowed)
    latency_ms = (time.perf_counter() - started) * 1000
    return CaseResult(
        case_id=case.case_id,
        task_family=case.task_family,
        difficulty=case.difficulty,
        arm="ucg",
        query=case.query,
        returned=returned,
        retrieval=retrieval,
        context=context,
        latency_ms=latency_ms,
    )


def run_ucg_retrieval_benchmark(
    cases: list[BenchmarkCase],
    *,
    limit: int = 8,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    results: list[CaseResult] = []
    with TemporaryDirectory(prefix="ucg-benchmark-") as tmp:
        db = ArchiveDB(Path(tmp) / "benchmark.sqlite3")
        for case in cases:
            seed_case_db(db, case)
            results.append(run_ucg_case(db, case, limit=limit))
        db.close()

    result_payload = {
        "schema_version": "ucg-benchmark-run.v0.1",
        "dataset_cases": len(cases),
        "arms": [asdict(arm) for arm in EXPERIMENT_ARMS],
        "runnable_arms": ["ucg"],
        "case_results": [result.as_dict() for result in results],
        "aggregate": aggregate(
            [
                {**result.retrieval, **result.context, "latency_ms": result.latency_ms}
                for result in results
            ]
        ),
    }

    assembly_results: list[CaseResult] = []
    with TemporaryDirectory(prefix="ucg-assembly-") as tmp:
        db = ArchiveDB(Path(tmp) / "benchmark.sqlite3")
        for case in cases:
            seed_case_db(db, case)
            assembly_results.append(run_ucg_assembly_case(db, case, limit=limit))
        db.close()


    auto_results: list[CaseResult] = []
    with TemporaryDirectory(prefix="ucg-auto-assembly-") as tmp:
        db = ArchiveDB(Path(tmp) / "benchmark.sqlite3")
        for case in cases:
            seed_case_db(db, case)
            auto_results.append(run_ucg_auto_assembly_case(db, case, limit=limit))
        db.close()

    result_payload["auto_assembly"] = {
        "arm": "ucg_auto_assembly",
        "case_results": [result.as_dict() for result in auto_results],
        "aggregate": aggregate([
            {**result.retrieval, **result.context, "latency_ms": result.latency_ms}
            for result in auto_results
        ]),
    }

    result_payload["assembly"] = {
        "arm": "ucg_assembly",
        "subquery_counts": aggregate(
            [{"count": float(len(case.retrieval_queries))} for case in cases]
        ),
        "case_results": [result.as_dict() for result in assembly_results],
        "aggregate": aggregate([
            {**result.retrieval, **result.context, "latency_ms": result.latency_ms}
            for result in assembly_results
        ]),
    }


    admission_results: list[CaseResult] = []
    admission_config = EvidenceAdmissionConfig(per_query_cap=2, final_limit=4)
    with TemporaryDirectory(prefix="ucg-admission-") as tmp:
        db = ArchiveDB(Path(tmp) / "benchmark.sqlite3")
        for case in cases:
            seed_case_db(db, case)
            admission_results.append(
                run_ucg_admission_case(
                    db,
                    case,
                    candidate_limit=limit,
                    config=admission_config,
                )
            )
        db.close()

    worthiness_oracle_results: list[CaseResult] = []
    worthiness_policy = ContextWorthinessPolicy(final_limit=4)
    with TemporaryDirectory(prefix="ucg-worthiness-oracle-") as tmp:
        db = ArchiveDB(Path(tmp) / "benchmark.sqlite3")
        for case in cases:
            seed_case_db(db, case)
            worthiness_oracle_results.append(
                run_ucg_worthiness_oracle_case(
                    db,
                    case,
                    candidate_limit=limit,
                    config=worthiness_policy,
                )
            )
        db.close()

    result_payload["worthiness_oracle"] = {
        "arm": "ucg_worthiness_oracle",
        "policy": {
            "final_limit": worthiness_policy.final_limit,
            "annotations": "benchmark_gold_oracle",
        },
        "case_results": [result.as_dict() for result in worthiness_oracle_results],
        "aggregate": aggregate([
            {**result.retrieval, **result.context, "latency_ms": result.latency_ms}
            for result in worthiness_oracle_results
        ]),
    }

    result_payload["admission"] = {
        "arm": "ucg_admission",
        "policy": {
            "per_query_cap": admission_config.per_query_cap,
            "final_limit": admission_config.final_limit,
            "candidate_limit": limit,
        },
        "case_results": [result.as_dict() for result in admission_results],
        "aggregate": aggregate([
            {**result.retrieval, **result.context, "latency_ms": result.latency_ms}
            for result in admission_results
        ]),
    }

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "ucg-benchmark-run.v0.1",
                    "dataset_cases": len(cases),
                    "arms": result_payload["arms"],
                    "runnable_arms": result_payload["runnable_arms"],
                    "assembly_arm": "ucg_assembly",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (out / "results.json").write_text(
            json.dumps(result_payload, indent=2),
            encoding="utf-8",
        )

    return result_payload
