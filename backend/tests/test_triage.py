import json
import logging

import pytest

from app.models import TriageSentiment
from app.triage import (
    FakeTriageClient,
    MAX_TRIAGE_ATTEMPTS,
    TriageProviderError,
    TriageTimeoutError,
    run_triage,
)

TRANSCRIPT_MARKER = "do-not-log-this-transcript"


class ScriptedClient:
    """Returns scripted responses and records how often it was called."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls = 0

    def request_triage(self, *, transcript: str) -> str:
        self.calls += 1
        response = self._responses[min(self.calls, len(self._responses)) - 1]
        if isinstance(response, Exception):
            raise response
        return str(response)


def valid_payload() -> str:
    return json.dumps(
        {
            "summary": "Customer asks about billing",
            "intent": "billing_question",
            "sentiment": "negative",
            "next_action": "Send the invoice",
        }
    )


def test_fake_client_is_deterministic_and_ignores_transcript() -> None:
    client = FakeTriageClient()
    first = client.request_triage(transcript="one transcript")
    second = client.request_triage(transcript="a completely different transcript")
    assert first == second
    assert TRANSCRIPT_MARKER not in first


def test_run_triage_succeeds_on_first_attempt() -> None:
    client = ScriptedClient([valid_payload()])
    result = run_triage(client=client, transcript="hello")
    assert result.summary == "Customer asks about billing"
    assert result.intent == "billing_question"
    assert result.sentiment is TriageSentiment.NEGATIVE
    assert result.next_action == "Send the invoice"
    assert client.calls == 1


def test_run_triage_retries_malformed_json_once() -> None:
    client = ScriptedClient(["{not json", valid_payload()])
    result = run_triage(client=client, transcript="hello")
    assert result.intent == "billing_question"
    assert client.calls == 2


def test_run_triage_raises_after_two_malformed_payloads() -> None:
    client = ScriptedClient(["{not json", "still not json"])
    with pytest.raises(TriageProviderError):
        run_triage(client=client, transcript="hello")
    assert client.calls == MAX_TRIAGE_ATTEMPTS


def test_run_triage_retries_missing_field_then_succeeds() -> None:
    missing = json.dumps({"summary": "Only a summary"})
    client = ScriptedClient([missing, valid_payload()])
    assert run_triage(client=client, transcript="hello").intent == "billing_question"
    assert client.calls == 2


def test_run_triage_rejects_invalid_enum() -> None:
    invalid = json.dumps(
        {
            "summary": "Too angry",
            "intent": "billing_question",
            "sentiment": "furious",
            "next_action": "Escalate",
        }
    )
    client = ScriptedClient([invalid, invalid])
    with pytest.raises(TriageProviderError):
        run_triage(client=client, transcript="hello")
    assert client.calls == MAX_TRIAGE_ATTEMPTS


def test_run_triage_rejects_oversized_fields() -> None:
    oversized = json.dumps(
        {
            "summary": "s" * 1001,
            "intent": "billing_question",
            "sentiment": "neutral",
            "next_action": "Escalate",
        }
    )
    client = ScriptedClient([oversized, oversized])
    with pytest.raises(TriageProviderError):
        run_triage(client=client, transcript="hello")


def test_run_triage_rejects_invalid_intent_pattern() -> None:
    invalid = json.dumps(
        {
            "summary": "Fine",
            "intent": "Billing Question!",
            "sentiment": "neutral",
            "next_action": "Reply",
        }
    )
    client = ScriptedClient([invalid, invalid])
    with pytest.raises(TriageProviderError):
        run_triage(client=client, transcript="hello")


def test_run_triage_retries_timeout_then_succeeds() -> None:
    client = ScriptedClient([TriageTimeoutError("slow"), valid_payload()])
    assert run_triage(client=client, transcript="hello").summary
    assert client.calls == 2


def test_run_triage_raises_after_two_timeouts() -> None:
    client = ScriptedClient(
        [TriageTimeoutError("slow"), TriageTimeoutError("still slow")]
    )
    with pytest.raises(TriageTimeoutError):
        run_triage(client=client, transcript="hello")
    assert client.calls == MAX_TRIAGE_ATTEMPTS


def test_run_triage_raises_after_two_provider_errors() -> None:
    client = ScriptedClient(
        [TriageProviderError("boom"), TriageProviderError("boom again")]
    )
    with pytest.raises(TriageProviderError):
        run_triage(client=client, transcript="hello")
    assert client.calls == MAX_TRIAGE_ATTEMPTS


def test_run_triage_never_makes_more_than_two_attempts() -> None:
    attempts: list[int] = []
    client = ScriptedClient([TriageProviderError("boom")])
    with pytest.raises(TriageProviderError):
        run_triage(
            client=client, transcript="hello", on_attempt=attempts.append
        )
    assert attempts == [1, 2]
    assert client.calls == MAX_TRIAGE_ATTEMPTS


def test_run_triage_does_not_log_transcript(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = ScriptedClient([TriageProviderError("boom")])
    with pytest.raises(TriageProviderError):
        run_triage(client=client, transcript=TRANSCRIPT_MARKER)
    assert TRANSCRIPT_MARKER not in caplog.text
