from __future__ import annotations

from typing import Any

from .context_bundle_lanes_v0_1 import (
    ContextBundle,
    ContextBundleValidationError,
    build_context_bundle,
)
from .selection_assessment_v0_1 import normalize_selection_assessment


class SelectionContextMaterializationError(ValueError):
    """Raised when a real selection plan cannot be materialized safely."""


_WORTHINESS_TO_ROLE = {
    "direct_support": "supporting",
    "supporting": "supporting",
    "contradiction": "contrastive",
    "contextual": "contextual",
    "none": "distractor",
}


def _messages(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for conversation in case["corpus"]["conversations"]:
        for message in conversation.get("messages", []):
            key = message.get("evidence_key")
            if key:
                out[key] = {
                    "key": key,
                    "text": message.get("text"),
                    "provenance": {
                        "provider": conversation.get("provider"),
                        "account": conversation.get("account_id"),
                        "conversation": conversation.get("conversation_id"),
                        "message": message.get("message_id"),
                    },
                }
    return out


def _semantic_by_id(
    semantic_assessment: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if isinstance(semantic_assessment, dict):
        rows = semantic_assessment.get("assessments") or []
    else:
        rows = semantic_assessment
    return {
        row["candidate_id"]: row
        for row in rows
        if isinstance(row, dict) and row.get("candidate_id")
    }


def prepare_selection_candidates(
    case: dict[str, Any],
    semantic_assessment: dict[str, Any] | list[dict[str, Any]],
    selection_assessment: dict[str, Any],
) -> list[dict[str, Any]]:
    """Adapt a canonical selection plan into lane-materializer candidates."""

    candidate_pool = []
    message_by_key = _messages(case)
    semantic_by_id = _semantic_by_id(semantic_assessment)
    candidate_ids = {
        row["candidate_id"]
        for row in semantic_by_id.values()
        if row.get("candidate_id")
    }

    normalized = normalize_selection_assessment(
        selection_assessment,
        candidate_ids,
    )

    selected_ids = set(normalized["selected_candidate_ids"])
    if not selected_ids:
        return []

    candidate_to_key: dict[str, str] = {}
    for evidence_key, provenance in case.get("provenance_map", {}).items():
        candidate_id = None
        for cid, sem in semantic_by_id.items():
            if sem.get("evidence_key") == evidence_key:
                candidate_id = cid
                break
        if candidate_id:
            candidate_to_key[candidate_id] = evidence_key

    # Fallback to corpus scan when semantic output does not repeat evidence_key.
    if len(candidate_to_key) < len(candidate_ids):
        corpus_keys = list(message_by_key)
        unresolved = [cid for cid in candidate_ids if cid not in candidate_to_key]
        if unresolved and len(unresolved) == len(corpus_keys):
            for cid, key in zip(sorted(unresolved), corpus_keys):
                candidate_to_key[cid] = key

    missing_mapping = sorted(selected_ids - set(candidate_to_key))
    if missing_mapping:
        raise SelectionContextMaterializationError(
            f"selected candidates lack evidence mapping: {missing_mapping}"
        )

    relations_by_source: dict[str, list[dict[str, Any]]] = {}
    for relation in normalized["relations"]:
        source = relation["source"]
        target = relation["target"]
        if relation["when_selected"] and target not in selected_ids:
            raise SelectionContextMaterializationError(
                f"required relation target {target!r} is not selected"
            )
        if source in selected_ids:
            if target not in candidate_to_key:
                raise SelectionContextMaterializationError(
                    f"relation target lacks evidence mapping: {target}"
                )
            relations_by_source.setdefault(source, []).append(
                {
                    "target": candidate_to_key[target],
                    "type": relation["type"],
                    "when_selected": relation["when_selected"],
                }
            )

    for candidate_id in normalized["selected_candidate_ids"]:
        evidence_key = candidate_to_key[candidate_id]
        message = message_by_key.get(evidence_key)
        if message is None:
            raise SelectionContextMaterializationError(
                f"evidence key not found in corpus: {evidence_key}"
            )

        semantic = semantic_by_id.get(candidate_id) or {}
        role = _WORTHINESS_TO_ROLE.get(
            semantic.get("worthiness_role", "none"),
            "distractor",
        )

        candidate_pool.append(
            {
                "key": evidence_key,
                "candidate_id": candidate_id,
                "text": message["text"],
                "provenance": message["provenance"],
                "role": role,
                "semantic_assessment": semantic,
                "admission": "accepted",
                "selection": {
                    "primary": role == "supporting",
                    "claim_ids": list(semantic.get("claim_ids") or []),
                    "optional_noise": False,
                    "relations": relations_by_source.get(candidate_id, []),
                    "coverage_mode": "best",
                },
            }
        )

    return candidate_pool


def materialize_selection_assessment(
    case: dict[str, Any],
    semantic_assessment: dict[str, Any] | list[dict[str, Any]],
    selection_assessment: dict[str, Any],
) -> dict[str, Any]:
    """Turn real selection-assessment output into a governed serialized bundle."""

    candidates = prepare_selection_candidates(
        case,
        semantic_assessment,
        selection_assessment,
    )
    normalized = normalize_selection_assessment(
        selection_assessment,
        {row["candidate_id"] for row in candidates}
        | {
            row["candidate_id"]
            for row in (
                semantic_assessment.get("assessments", [])
                if isinstance(semantic_assessment, dict)
                else semantic_assessment
            )
            if isinstance(row, dict) and row.get("candidate_id")
        },
    )

    selected_key_order = [
        row["key"]
        for row in candidates
        if row["candidate_id"] in normalized["selected_candidate_ids"]
    ]
    bundle: ContextBundle = build_context_bundle(candidates, selected_key_order)

    return {
        "schema_version": "ucg-context-bundle.v0.1",
        "case_id": case["case_id"],
        "selection": normalized,
        "candidate_ids": [row["candidate_id"] for row in candidates],
        "selected_candidate_ids": normalized["selected_candidate_ids"],
        "candidate_to_evidence_key": {
            row["candidate_id"]: row["key"] for row in candidates
        },
        "bundle": bundle.as_dict(),
    }
