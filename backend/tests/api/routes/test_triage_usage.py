from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

from app.core.config import settings
from app.models import TriageUsage, TriageUsageOutcome


def _clear_usage(db: Session) -> None:
    db.exec(delete(TriageUsage))
    db.commit()


def _usage(
    db: Session,
    *,
    provider: str | None,
    model: str | None,
    outcome: TriageUsageOutcome,
    latency_ms: int,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> TriageUsage:
    usage = TriageUsage(
        provider=provider,
        model=model,
        outcome=outcome,
        attempts=1,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


def test_triage_usage_requires_superuser(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/triage-usage/",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 403


def test_triage_usage_requires_authentication(client: TestClient) -> None:
    response = client.get(f"{settings.API_V1_STR}/triage-usage/")
    assert response.status_code == 401


def test_triage_usage_aggregates_metadata_only(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    _clear_usage(db)
    _usage(
        db,
        provider="example-provider",
        model="example-model",
        outcome=TriageUsageOutcome.SUCCEEDED,
        latency_ms=100,
        input_tokens=10,
        output_tokens=5,
    )
    _usage(
        db,
        provider="example-provider",
        model="example-model",
        outcome=TriageUsageOutcome.SUCCEEDED,
        latency_ms=200,
    )
    _usage(
        db,
        provider="example-provider",
        model="example-model",
        outcome=TriageUsageOutcome.TIMEOUT,
        latency_ms=300,
    )

    response = client.get(
        f"{settings.API_V1_STR}/triage-usage/", headers=superuser_token_headers
    )
    assert response.status_code == 200
    body = response.json()

    assert body["total"] == 3
    buckets = {
        (bucket["provider"], bucket["model"], bucket["outcome"]): bucket
        for bucket in body["buckets"]
    }

    succeeded = buckets[("example-provider", "example-model", "succeeded")]
    assert succeeded["count"] == 2
    assert succeeded["avg_latency_ms"] == 150.0
    assert succeeded["max_latency_ms"] == 200
    assert succeeded["input_tokens_total"] == 10
    assert succeeded["output_tokens_total"] == 5
    assert succeeded["unknown_token_count"] == 1

    timed_out = buckets[("example-provider", "example-model", "timeout")]
    assert timed_out["count"] == 1
    assert timed_out["max_latency_ms"] == 300
    assert timed_out["input_tokens_total"] is None
    assert timed_out["output_tokens_total"] is None
    assert timed_out["unknown_token_count"] == 1


def test_triage_usage_response_has_no_content_fields(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    _clear_usage(db)
    _usage(
        db,
        provider="fake",
        model="fake-deterministic",
        outcome=TriageUsageOutcome.SUCCEEDED,
        latency_ms=5,
    )

    response = client.get(
        f"{settings.API_V1_STR}/triage-usage/", headers=superuser_token_headers
    )
    assert response.status_code == 200
    body = response.json()

    assert set(body) == {"total", "buckets"}
    for bucket in body["buckets"]:
        assert set(bucket) == {
            "provider",
            "model",
            "outcome",
            "count",
            "avg_latency_ms",
            "max_latency_ms",
            "input_tokens_total",
            "output_tokens_total",
            "unknown_token_count",
        }
    assert "transcript" not in response.text
    assert "summary" not in response.text


def test_triage_usage_records_triage_outcomes_end_to_end(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    _clear_usage(db)
    created = client.post(
        f"{settings.API_V1_STR}/conversations/",
        headers=superuser_token_headers,
        json={"title": "Usage flow", "transcript": "Hello there"},
    )
    assert created.status_code == 200
    conversation_id = created.json()["id"]

    triaged = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation_id}/triage",
        headers=superuser_token_headers,
    )
    assert triaged.status_code == 200

    response = client.get(
        f"{settings.API_V1_STR}/triage-usage/", headers=superuser_token_headers
    )
    assert response.status_code == 200
    buckets = [
        bucket
        for bucket in response.json()["buckets"]
        if bucket["provider"] == "fake"
        and bucket["model"] == "fake-deterministic"
        and bucket["outcome"] == "succeeded"
    ]
    assert buckets
    assert buckets[0]["unknown_token_count"] >= 1
