import json
import logging

import pytest

from app.models import TriageSentiment, TriageUsageOutcome
from app.triage import (
    FakeTriageClient,
    MAX_TRIAGE_ATTEMPTS,
    TriageClientResponse,
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

    def request_triage(self, *, transcript: str) -> TriageClientResponse:
        self.calls += 1
        response = self._responses[min(self.calls, len(self._responses)) - 1]
        if isinstance(response, Exception):
            raise response
        if isinstance(response, TriageClientResponse):
            return response
        return TriageClientResponse(payload=str(response))


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
    assert TRANSCRIPT_MARKER not in first.payload
    assert first.provider == "fake"
    assert first.model == "fake-deterministic"
    assert first.input_tokens is None
    assert first.output_tokens is None


def test_run_triage_succeeds_on_first_attempt() -> None:
    client = ScriptedClient([valid_payload()])
    run = run_triage(client=client, transcript="hello")

    assert run.succeeded
    assert run.result is not None
    assert run.result.summary == "Customer asks about billing"
    assert run.result.intent == "billing_question"
    assert run.result.sentiment is TriageSentiment.NEGATIVE
    assert run.result.next_action == "Send the invoice"
    assert run.outcome is TriageUsageOutcome.SUCCEEDED
    assert run.attempts == 1
    assert run.error is None
    assert run.latency_ms >= 0
    assert client.calls == 1


def test_run_triage_records_content_free_metadata() -> None:
    client = ScriptedClient(
        [
            TriageClientResponse(
                payload=valid_payload(),
                provider="example-provider",
                model="example-model",
                input_tokens=120,
                output_tokens=45,
            )
        ]
    )
    run = run_triage(client=client, transcript="hello")

    assert run.provider == "example-provider"
    assert run.model == "example-model"
    assert run.input_tokens == 120
    assert run.output_tokens == 45


def test_run_triage_clips_oversized_identifiers() -> None:
    client = ScriptedClient(
        [
            TriageClientResponse(
                payload=valid_payload(),
                provider="p" * 500,
                model="m" * 500,
            )
        ]
    )
    run = run_triage(client=client, transcript="hello")

    assert run.provider is not None and len(run.provider) == 64
    assert run.model is not None and len(run.model) == 96


def test_run_triage_retries_malformed_json_once() -> None:
    client = ScriptedClient(["{not json", valid_payload()])
    run = run_triage(client=client, transcript="hello")

    assert run.succeeded
    assert run.result is not None
    assert run.result.intent == "billing_question"
    assert run.attempts == 2
    assert client.calls == 2


def test_run_triage_reports_invalid_response_after_two_malformed_payloads() -> None:
    client = ScriptedClient(["{not json", "still not json"])
    run = run_triage(client=client, transcript="hello")

    assert not run.succeeded
    assert run.result is None
    assert isinstance(run.error, TriageProviderError)
    assert run.outcome is TriageUsageOutcome.INVALID_RESPONSE
    assert run.attempts == MAX_TRIAGE_ATTEMPTS
    assert client.calls == MAX_TRIAGE_ATTEMPTS


def test_run_triage_retries_missing_field_then_succeeds() -> None:
    missing = json.dumps({"summary": "Only a summary"})
    client = ScriptedClient([missing, valid_payload()])
    run = run_triage(client=client, transcript="hello")

    assert run.succeeded
    assert run.attempts == 2
    assert client.calls == 2


def test_run_triage_reports_invalid_enum() -> None:
    invalid = json.dumps(
        {
            "summary": "Too angry",
            "intent": "billing_question",
            "sentiment": "furious",
            "next_action": "Escalate",
        }
    )
    client = ScriptedClient([invalid, invalid])
    run = run_triage(client=client, transcript="hello")

    assert run.outcome is TriageUsageOutcome.INVALID_RESPONSE
    assert run.attempts == MAX_TRIAGE_ATTEMPTS


def test_run_triage_reports_oversized_fields() -> None:
    oversized = json.dumps(
        {
            "summary": "s" * 1001,
            "intent": "billing_question",
            "sentiment": "neutral",
            "next_action": "Escalate",
        }
    )
    client = ScriptedClient([oversized, oversized])
    run = run_triage(client=client, transcript="hello")

    assert run.outcome is TriageUsageOutcome.INVALID_RESPONSE


def test_run_triage_reports_invalid_intent_pattern() -> None:
    invalid = json.dumps(
        {
            "summary": "Fine",
            "intent": "Billing Question!",
            "sentiment": "neutral",
            "next_action": "Reply",
        }
    )
    client = ScriptedClient([invalid, invalid])
    run = run_triage(client=client, transcript="hello")

    assert run.outcome is TriageUsageOutcome.INVALID_RESPONSE


def test_run_triage_retries_timeout_then_succeeds() -> None:
    client = ScriptedClient([TriageTimeoutError("slow"), valid_payload()])
    run = run_triage(client=client, transcript="hello")

    assert run.succeeded
    assert run.outcome is TriageUsageOutcome.SUCCEEDED
    assert run.attempts == 2


def test_run_triage_reports_timeout_after_two_timeouts() -> None:
    client = ScriptedClient(
        [TriageTimeoutError("slow"), TriageTimeoutError("still slow")]
    )
    run = run_triage(client=client, transcript="hello")

    assert not run.succeeded
    assert isinstance(run.error, TriageTimeoutError)
    assert run.outcome is TriageUsageOutcome.TIMEOUT
    assert run.attempts == MAX_TRIAGE_ATTEMPTS


def test_run_triage_reports_provider_error() -> None:
    client = ScriptedClient(
        [TriageProviderError("boom"), TriageProviderError("boom again")]
    )
    run = run_triage(client=client, transcript="hello")

    assert not run.succeeded
    assert run.outcome is TriageUsageOutcome.PROVIDER_ERROR
    assert run.attempts == MAX_TRIAGE_ATTEMPTS


def test_run_triage_never_makes_more_than_two_attempts() -> None:
    attempts: list[int] = []
    client = ScriptedClient([TriageProviderError("boom")])
    run_triage(client=client, transcript="hello", on_attempt=attempts.append)

    assert attempts == [1, 2]
    assert client.calls == MAX_TRIAGE_ATTEMPTS


def test_run_triage_never_returns_the_raw_payload() -> None:
    client = ScriptedClient([valid_payload()])
    run = run_triage(client=client, transcript=TRANSCRIPT_MARKER)

    assert TRANSCRIPT_MARKER not in repr(run)


def test_run_triage_does_not_log_transcript(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = ScriptedClient([TriageProviderError("boom")])
    run_triage(client=client, transcript=TRANSCRIPT_MARKER)

    assert TRANSCRIPT_MARKER not in caplog.text
