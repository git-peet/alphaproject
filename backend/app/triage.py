"""Synchronous conversation triage boundary.

The only implementation in this PBI is a deterministic fake client. It ignores
the transcript entirely and performs no network call. A live provider requires a
separate PBI with explicit provider, privacy, and cost approval.

Never log a transcript, prompt, raw payload, triage output, or credential from
this module. Usage accounting keeps only content-free metadata: provider, model,
outcome, attempts, locally measured latency, and token counts when supplied.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends
from pydantic import ValidationError

from app.models import (
    TRIAGE_USAGE_MODEL_MAX_LENGTH,
    TRIAGE_USAGE_PROVIDER_MAX_LENGTH,
    ConversationTriage,
    TriageUsageOutcome,
)


class TriageError(Exception):
    """Base class for triage failures that must not be retried indefinitely."""


class TriageTimeoutError(TriageError):
    """The client did not answer in time."""


class TriageProviderError(TriageError):
    """The client failed to answer."""


class TriageInvalidResponseError(TriageProviderError):
    """The client answered, but the payload was malformed or invalid."""


@dataclass(frozen=True)
class TriageClientResponse:
    """A raw client answer plus optional content-free metadata."""

    payload: str
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class TriageClient(Protocol):
    def request_triage(self, *, transcript: str) -> TriageClientResponse:
        """Return a raw JSON triage payload and optional metadata."""
        ...


_FAKE_PAYLOAD = {
    "summary": "Fake triage summary",
    "intent": "general",
    "sentiment": "neutral",
    "next_action": "Review the conversation",
}


class FakeTriageClient:
    """Deterministic client used by this PBI.

    Deliberately ignores the transcript: the fake provably reads nothing and
    cannot leak conversation content. Token counts are intentionally unavailable.
    """

    def request_triage(self, *, transcript: str) -> TriageClientResponse:
        return TriageClientResponse(
            payload=json.dumps(_FAKE_PAYLOAD),
            provider="fake",
            model="fake-deterministic",
        )


def get_triage_client() -> TriageClient:
    return FakeTriageClient()


TriageClientDep = Annotated[TriageClient, Depends(get_triage_client)]

MAX_TRIAGE_ATTEMPTS = 2


@dataclass(frozen=True)
class TriageRun:
    """Content-free report of one triage request."""

    result: ConversationTriage | None
    error: TriageError | None
    outcome: TriageUsageOutcome
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    attempts: int
    latency_ms: int

    @property
    def succeeded(self) -> bool:
        return self.result is not None


def _validate_payload(raw: str) -> ConversationTriage:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise TriageInvalidResponseError("Triage payload was not valid JSON") from exc
    try:
        return ConversationTriage.model_validate(payload)
    except ValidationError as exc:
        raise TriageInvalidResponseError(
            "Triage payload failed validation"
        ) from exc


def _outcome_for(error: TriageError | None) -> TriageUsageOutcome:
    if error is None:
        return TriageUsageOutcome.SUCCEEDED
    if isinstance(error, TriageTimeoutError):
        return TriageUsageOutcome.TIMEOUT
    if isinstance(error, TriageInvalidResponseError):
        return TriageUsageOutcome.INVALID_RESPONSE
    return TriageUsageOutcome.PROVIDER_ERROR


def _clipped(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


def run_triage(
    *,
    client: TriageClient,
    transcript: str,
    on_attempt: Callable[[int], None] | None = None,
) -> TriageRun:
    """Run triage with at most one retry and return a content-free report.

    The report never contains the transcript, the prompt, or the raw payload.
    `on_attempt` is a test hook so callers can observe the attempt count without
    this module logging anything about the conversation.
    """
    started = time.perf_counter()
    last_error: TriageError | None = None
    result: ConversationTriage | None = None
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    attempts = 0

    for attempt in range(1, MAX_TRIAGE_ATTEMPTS + 1):
        attempts = attempt
        if on_attempt is not None:
            on_attempt(attempt)
        try:
            response = client.request_triage(transcript=transcript)
            # Metadata from the failing attempt is superseded by the next one.
            provider = _clipped(response.provider, TRIAGE_USAGE_PROVIDER_MAX_LENGTH)
            model = _clipped(response.model, TRIAGE_USAGE_MODEL_MAX_LENGTH)
            input_tokens = response.input_tokens
            output_tokens = response.output_tokens
            result = _validate_payload(response.payload)
            last_error = None
            break
        except TriageError as exc:
            last_error = exc
            result = None

    latency_ms = int((time.perf_counter() - started) * 1000)
    return TriageRun(
        result=result,
        error=last_error,
        outcome=_outcome_for(last_error),
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        attempts=attempts,
        latency_ms=latency_ms,
    )
