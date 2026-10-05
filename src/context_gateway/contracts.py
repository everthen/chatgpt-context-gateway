from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ContextContractError(ValueError):
    pass


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
    max_age_seconds: int | None = None
    allow_live_acquisition: bool = False
    require_fresh: bool = False

    def __post_init__(self) -> None:
        if self.max_age_seconds is not None and self.max_age_seconds < 0:
            raise ContextContractError("freshness.max_age_seconds must be >= 0")
        if self.require_fresh and self.max_age_seconds is None:
            raise ContextContractError(
                "freshness.require_fresh requires freshness.max_age_seconds"
            )

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "FreshnessPolicy":
        value = value or {}
        raw_age = value.get("max_age_seconds")
        return cls(
            max_age_seconds=int(raw_age) if raw_age is not None else None,
            allow_live_acquisition=bool(value.get("allow_live_acquisition", False)),
            require_fresh=bool(value.get("require_fresh", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_age_seconds": self.max_age_seconds,
            "allow_live_acquisition": self.allow_live_acquisition,
            "require_fresh": self.require_fresh,
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

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ContextRequest":
        if not isinstance(value, dict):
            raise ContextContractError("context request must be an object")
        return cls(
            consumer=str(value.get("consumer", "")),
            session_id=str(value.get("session_id", "")),
            query=str(value.get("query", "")),
            scope=ContextScope.from_dict(value.get("scope")),
            freshness=FreshnessPolicy.from_dict(value.get("freshness")),
            budget=ContextBudget.from_dict(value.get("budget")),
            trust=str(value.get("trust", "historical_evidence")),
            exclude_conversation_uids=tuple(
                str(x) for x in (value.get("exclude_conversation_uids") or ())
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "consumer": self.consumer,
            "session_id": self.session_id,
            "query": self.query,
            "scope": self.scope.to_dict(),
            "freshness": self.freshness.to_dict(),
            "budget": self.budget.to_dict(),
            "trust": self.trust,
            "exclude_conversation_uids": list(self.exclude_conversation_uids),
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
