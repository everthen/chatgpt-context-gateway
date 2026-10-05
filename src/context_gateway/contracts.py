from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


class ContextContractError(ValueError):
    pass


FreshnessMode = Literal["accept_stale", "prefer_fresh", "require_fresh"]


@dataclass(frozen=True)
class ContextScope:
    providers: tuple[str, ...] = ()
    accounts: str | tuple[str, ...] = "all"
    project: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "ContextScope":
        value = value or {}
        providers = tuple(str(x) for x in (value.get("providers") or ()))
        accounts = value.get("accounts", "all")
        if accounts != "all":
            if isinstance(accounts, str):
                accounts = (accounts,)
            else:
                accounts = tuple(str(x) for x in accounts)
        project = value.get("project")
        return cls(providers=providers, accounts=accounts, project=project)

    def to_dict(self) -> dict[str, Any]:
        return {
            "providers": list(self.providers),
            "accounts": self.accounts if self.accounts == "all" else list(self.accounts),
            "project": self.project,
        }


@dataclass(frozen=True)
class ContextBudget:
    max_messages: int = 30
    max_bytes: int = 120_000

    def __post_init__(self) -> None:
        if self.max_messages < 1:
            raise ContextContractError("budget.max_messages must be >= 1")
        if self.max_bytes < 1024:
            raise ContextContractError("budget.max_bytes must be >= 1024")

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "ContextBudget":
        value = value or {}
        return cls(
            max_messages=int(value.get("max_messages", 30)),
            max_bytes=int(value.get("max_bytes", 120_000)),
        )

    def to_dict(self) -> dict[str, int]:
        return {"max_messages": self.max_messages, "max_bytes": self.max_bytes}


@dataclass(frozen=True)
class FreshnessPolicy:
    mode: FreshnessMode = "accept_stale"
    max_age_seconds: int | None = None
    max_observation_age_seconds: int | None = None
    max_source_age_seconds: int | None = None
    allow_live_acquisition: bool = False
    allow_partial: bool = False
    require_fresh: bool = False

    def __post_init__(self) -> None:
        if self.mode not in {"accept_stale", "prefer_fresh", "require_fresh"}:
            raise ContextContractError("freshness.mode is invalid")

        for name, value in (
            ("max_age_seconds", self.max_age_seconds),
            ("max_observation_age_seconds", self.max_observation_age_seconds),
            ("max_source_age_seconds", self.max_source_age_seconds),
        ):
            if value is not None and value < 0:
                raise ContextContractError(f"freshness.{name} must be >= 0")

        if self.require_fresh and self.mode == "accept_stale":
            object.__setattr__(self, "mode", "require_fresh")

        if self.mode == "require_fresh" and self.max_age_seconds is None and self.max_observation_age_seconds is None and self.max_source_age_seconds is None:
            raise ContextContractError(
                "freshness.mode=require_fresh requires an age threshold"
            )

        if self.require_fresh and self.max_age_seconds is None and self.max_observation_age_seconds is None:
            raise ContextContractError(
                "freshness.require_fresh requires a freshness age threshold"
            )

        if self.max_age_seconds is not None and self.max_observation_age_seconds is None:
            object.__setattr__(
                self,
                "max_observation_age_seconds",
                self.max_age_seconds,
            )

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "FreshnessPolicy":
        value = value or {}
        return cls(
            mode=str(value.get("mode", "accept_stale")),
            max_age_seconds=(
                int(value["max_age_seconds"])
                if value.get("max_age_seconds") is not None
                else None
            ),
            max_observation_age_seconds=(
                int(value["max_observation_age_seconds"])
                if value.get("max_observation_age_seconds") is not None
                else None
            ),
            max_source_age_seconds=(
                int(value["max_source_age_seconds"])
                if value.get("max_source_age_seconds") is not None
                else None
            ),
            allow_live_acquisition=bool(value.get("allow_live_acquisition", False)),
            allow_partial=bool(value.get("allow_partial", False)),
            require_fresh=bool(value.get("require_fresh", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "max_age_seconds": self.max_age_seconds,
            "max_observation_age_seconds": self.max_observation_age_seconds,
            "max_source_age_seconds": self.max_source_age_seconds,
            "allow_live_acquisition": self.allow_live_acquisition,
            "allow_partial": self.allow_partial,
            "require_fresh": self.require_fresh,
        }


@dataclass(frozen=True)
class CurrentSessionContext:
    session_id: str
    current_conversation_uid: str | None = None
    current_conversation_id: str | None = None
    current_turn_id: str | None = None
    previous_turn_id: str | None = None
    last_user_request: str | None = None
    last_assistant_commitment: str | None = None
    pending_action: str | None = None
    continuation_requested: bool = False
    observed_at: float | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None, session_id: str) -> "CurrentSessionContext | None":
        if not value:
            return None
        return cls(
            session_id=session_id,
            current_conversation_uid=(
                str(value["current_conversation_uid"])
                if value.get("current_conversation_uid")
                else None
            ),
            current_conversation_id=(
                str(value["current_conversation_id"])
                if value.get("current_conversation_id")
                else None
            ),
            current_turn_id=(
                str(value["current_turn_id"])
                if value.get("current_turn_id")
                else None
            ),
            previous_turn_id=(
                str(value["previous_turn_id"])
                if value.get("previous_turn_id")
                else None
            ),
            last_user_request=(
                str(value["last_user_request"])
                if value.get("last_user_request")
                else None
            ),
            last_assistant_commitment=(
                str(value["last_assistant_commitment"])
                if value.get("last_assistant_commitment")
                else None
            ),
            pending_action=(
                str(value["pending_action"])
                if value.get("pending_action")
                else None
            ),
            continuation_requested=bool(value.get("continuation_requested", False)),
            observed_at=(
                float(value["observed_at"])
                if value.get("observed_at") is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "current_conversation_uid": self.current_conversation_uid,
            "current_conversation_id": self.current_conversation_id,
            "current_turn_id": self.current_turn_id,
            "previous_turn_id": self.previous_turn_id,
            "last_user_request": self.last_user_request,
            "last_assistant_commitment": self.last_assistant_commitment,
            "pending_action": self.pending_action,
            "continuation_requested": self.continuation_requested,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True)
class ContextRequest:
    consumer: str
    session_id: str
    query: str
    scope: ContextScope = field(default_factory=ContextScope)
    freshness: FreshnessPolicy = field(default_factory=FreshnessPolicy)
    budget: ContextBudget = field(default_factory=ContextBudget)
    trust: str = "historical_evidence"
    exclude_conversation_uids: tuple[str, ...] = ()
    current_session: CurrentSessionContext | None = None

    def __post_init__(self) -> None:
        if not self.consumer.strip():
            raise ContextContractError("consumer is required")
        if not self.session_id.strip():
            raise ContextContractError("session_id is required")
        if not self.query.strip():
            raise ContextContractError("query is required")
        if self.trust != "historical_evidence":
            raise ContextContractError("trust must be 'historical_evidence'")
        if len(self.query) > 500:
            raise ContextContractError("query exceeds 500 characters")
        if self.current_session and self.current_session.session_id != self.session_id:
            raise ContextContractError(
                "current_session.session_id must match request.session_id"
            )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ContextRequest":
        if not isinstance(value, dict):
            raise ContextContractError("context request must be an object")
        session_id = str(value.get("session_id", ""))
        return cls(
            consumer=str(value.get("consumer", "")),
            session_id=session_id,
            query=str(value.get("query", "")),
            scope=ContextScope.from_dict(value.get("scope")),
            freshness=FreshnessPolicy.from_dict(value.get("freshness")),
            budget=ContextBudget.from_dict(value.get("budget")),
            trust=str(value.get("trust", "historical_evidence")),
            exclude_conversation_uids=tuple(
                str(x) for x in (value.get("exclude_conversation_uids") or ())
            ),
            current_session=CurrentSessionContext.from_dict(
                value.get("current_session"),
                session_id=session_id,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        excluded = list(self.exclude_conversation_uids)
        if (
            self.current_session
            and self.current_session.current_conversation_uid
            and not self.current_session.continuation_requested
        ):
            if self.current_session.current_conversation_uid not in excluded:
                excluded.append(self.current_session.current_conversation_uid)
        return {
            "consumer": self.consumer,
            "session_id": self.session_id,
            "query": self.query,
            "scope": self.scope.to_dict(),
            "freshness": self.freshness.to_dict(),
            "budget": self.budget.to_dict(),
            "trust": self.trust,
            "exclude_conversation_uids": excluded,
            "current_session": (
                self.current_session.to_dict() if self.current_session else None
            ),
        }


@dataclass(frozen=True)
class AcquisitionCheckpoint:
    provider: str
    account_id: str
    scope_type: str
    scope_id: str
    method: str
    status: str
    cursor: str | None = None
    last_success_at: float | None = None
    last_seen_remote_at: float | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "account_id": self.account_id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "method": self.method,
            "status": self.status,
            "cursor": self.cursor,
            "last_success_at": self.last_success_at,
            "last_seen_remote_at": self.last_seen_remote_at,
            "last_error": self.last_error,
        }
