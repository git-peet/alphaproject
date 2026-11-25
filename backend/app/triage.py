"""Synchronous conversation triage boundary.

The only implementation in this PBI is a deterministic fake client. It ignores
the transcript entirely and performs no network call. A live provider requires a
separate PBI with explicit provider, privacy, and cost approval.

Never log a transcript, prompt, raw payload, triage output, or credential from
this module.
"""

import json
from collections.abc import Callable
from typing import Annotated, Protocol

from fastapi import Depends
from pydantic import ValidationError

from app.models import ConversationTriage


class TriageError(Exception):
    """Base class for triage failures that must not be retried indefinitely."""


class TriageTimeoutError(TriageError):
    """The client did not answer in time."""


class TriageProviderError(TriageError):
    """The client failed, or its payload was malformed or invalid."""


class TriageClient(Protocol):
    def request_triage(self, *, transcript: str) -> str:
        """Return a raw JSON triage payload for the transcript."""
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
    cannot leak conversation content.
    """

    def request_triage(self, *, transcript: str) -> str:
        return json.dumps(_FAKE_PAYLOAD)


def get_triage_client() -> TriageClient:
    return FakeTriageClient()


TriageClientDep = Annotated[TriageClient, Depends(get_triage_client)]

MAX_TRIAGE_ATTEMPTS = 2


def _validate_payload(raw: str) -> ConversationTriage:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise TriageProviderError("Triage payload was not valid JSON") from exc
    try:
        return ConversationTriage.model_validate(payload)
    except ValidationError as exc:
        raise TriageProviderError("Triage payload failed validation") from exc


def run_triage(
    *,
    client: TriageClient,
    transcript: str,
    on_attempt: Callable[[int], None] | None = None,
) -> ConversationTriage:
    """Return a validated triage result, retrying at most once.

    `on_attempt` is a test hook so callers can observe the attempt count without
    this module logging anything about the conversation.
    """
    last_error: TriageError | None = None
    for attempt in range(1, MAX_TRIAGE_ATTEMPTS + 1):
        if on_attempt is not None:
            on_attempt(attempt)
        try:
            return _validate_payload(client.request_triage(transcript=transcript))
        except TriageError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error
