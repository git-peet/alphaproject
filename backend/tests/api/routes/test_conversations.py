import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

from app import crud
from app.core.config import settings
from app.main import app
from app.models import (
    CONVERSATION_TRANSCRIPT_MAX_LENGTH,
    Conversation,
    ConversationTriagePublic,
    TriageUsage,
    TriageUsageOutcome,
    User,
    UserUpdate,
)
from app.triage import (
    TriageClientResponse,
    TriageProviderError,
    TriageTimeoutError,
    get_triage_client,
)
from tests.utils.conversation import create_random_conversation
from tests.utils.user import create_random_user, user_authentication_headers
from tests.utils.utils import random_lower_string


def _headers_for(client: TestClient, db: Session) -> dict[str, str]:
    user = create_random_user(db)
    password = random_lower_string()
    crud.update_user(session=db, db_user=user, user_in=UserUpdate(password=password))
    return user_authentication_headers(
        client=client, email=str(user.email), password=password
    )


def _create_owned(
    client: TestClient, headers: dict[str, str], title: str = "Owned chat"
) -> dict[str, str]:
    response = client.post(
        f"{settings.API_V1_STR}/conversations/",
        headers=headers,
        json={"title": title, "transcript": "Hello there"},
    )
    assert response.status_code == 200
    return response.json()


def test_create_conversation(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    data = {"title": "First chat", "transcript": "Hello there"}
    response = client.post(
        f"{settings.API_V1_STR}/conversations/",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["title"] == data["title"]
    assert content["transcript"] == data["transcript"]
    assert content["owner_id"]
    assert content["created_at"]
    assert content["updated_at"]


def test_create_conversation_requires_auth(client: TestClient) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/conversations/",
        json={"title": "No auth", "transcript": "text"},
    )
    assert response.status_code == 401


def test_create_conversation_rejects_empty_fields(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/conversations/",
        headers=superuser_token_headers,
        json={"title": "", "transcript": ""},
    )
    assert response.status_code == 422


def test_create_conversation_rejects_long_transcript_without_echo(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    secret_marker = "private-transcript-marker"
    transcript = secret_marker * (CONVERSATION_TRANSCRIPT_MAX_LENGTH // 10 + 50)
    assert len(transcript) > CONVERSATION_TRANSCRIPT_MAX_LENGTH
    response = client.post(
        f"{settings.API_V1_STR}/conversations/",
        headers=superuser_token_headers,
        json={"title": "Too long", "transcript": transcript},
    )
    assert response.status_code == 422
    assert secret_marker not in response.text
    assert str(CONVERSATION_TRANSCRIPT_MAX_LENGTH) in response.json()["detail"]


def test_read_conversation(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    created = _create_owned(client, superuser_token_headers)
    response = client.get(
        f"{settings.API_V1_STR}/conversations/{created['id']}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["title"] == created["title"]
    assert content["transcript"] == created["transcript"]
    assert content["id"] == created["id"]


def test_read_conversation_not_found(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/conversations/{uuid.uuid4()}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_read_conversation_not_enough_permissions(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    conversation = create_random_conversation(db)
    response = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation.id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"


def test_superuser_cannot_read_other_users_conversation(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    conversation = create_random_conversation(db)
    response = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation.id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 403


def test_read_conversations_scoped_to_owner(
    client: TestClient, db: Session
) -> None:
    owner_headers = _headers_for(client, db)
    created = client.post(
        f"{settings.API_V1_STR}/conversations/",
        headers=owner_headers,
        json={"title": "Mine", "transcript": "Only mine"},
    )
    assert created.status_code == 200

    other_headers = _headers_for(client, db)
    other = client.get(
        f"{settings.API_V1_STR}/conversations/", headers=other_headers
    )
    assert other.status_code == 200
    assert other.json()["count"] == 0
    assert other.json()["data"] == []

    mine = client.get(f"{settings.API_V1_STR}/conversations/", headers=owner_headers)
    assert mine.status_code == 200
    assert mine.json()["count"] == 1
    assert mine.json()["data"][0]["title"] == "Mine"
    assert "transcript" not in mine.json()["data"][0]


def test_update_conversation(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    created = _create_owned(client, superuser_token_headers)
    response = client.put(
        f"{settings.API_V1_STR}/conversations/{created['id']}",
        headers=superuser_token_headers,
        json={"title": "Updated title"},
    )
    assert response.status_code == 200
    content = response.json()
    assert content["title"] == "Updated title"
    assert content["transcript"] == created["transcript"]
    assert content["updated_at"] >= content["created_at"]


def test_update_conversation_rejects_long_transcript_without_echo(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    created = _create_owned(client, superuser_token_headers)
    secret_marker = "private-transcript-marker"
    transcript = secret_marker * (CONVERSATION_TRANSCRIPT_MAX_LENGTH // 10 + 50)
    response = client.put(
        f"{settings.API_V1_STR}/conversations/{created['id']}",
        headers=superuser_token_headers,
        json={"transcript": transcript},
    )
    assert response.status_code == 422
    assert secret_marker not in response.text


def test_update_conversation_not_enough_permissions(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    conversation = create_random_conversation(db)
    response = client.put(
        f"{settings.API_V1_STR}/conversations/{conversation.id}",
        headers=normal_user_token_headers,
        json={"title": "Stolen"},
    )
    assert response.status_code == 403


def test_delete_conversation(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    created = _create_owned(client, superuser_token_headers)
    response = client.delete(
        f"{settings.API_V1_STR}/conversations/{created['id']}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Conversation deleted successfully"
    assert db.get(Conversation, created["id"]) is None


def test_delete_conversation_not_enough_permissions(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    conversation = create_random_conversation(db)
    response = client.delete(
        f"{settings.API_V1_STR}/conversations/{conversation.id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 403


def test_conversations_deleted_with_owner(db: Session) -> None:
    conversation = create_random_conversation(db)
    conversation_id = conversation.id
    owner = db.get(User, conversation.owner_id)
    assert owner is not None

    db.delete(owner)
    db.commit()

    assert db.get(Conversation, conversation_id) is None


# ---------------------------------------------------------------------------
# Triage endpoint
# ---------------------------------------------------------------------------

TRIAGE_TRANSCRIPT_MARKER = "do-not-leak-this-transcript"


class ScriptedTriageClient:
    def __init__(
        self,
        responses: list[object],
        *,
        provider: str | None = None,
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        self._responses = responses
        self._metadata = {
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        self.calls = 0

    def request_triage(self, *, transcript: str) -> TriageClientResponse:
        self.calls += 1
        response = self._responses[min(self.calls, len(self._responses)) - 1]
        if isinstance(response, Exception):
            raise response
        return TriageClientResponse(payload=str(response), **self._metadata)


def _triage_payload(**overrides: str) -> str:
    data = {
        "summary": "Customer asks about an invoice",
        "intent": "billing_question",
        "sentiment": "negative",
        "next_action": "Send the invoice",
    }
    data.update(overrides)
    return json.dumps(data)


def _owned_conversation(
    client: TestClient, headers: dict[str, str], transcript: str
) -> dict[str, str]:
    response = client.post(
        f"{settings.API_V1_STR}/conversations/",
        headers=headers,
        json={"title": "Triage me", "transcript": transcript},
    )
    assert response.status_code == 200
    return response.json()


def _use_triage_client(triage_client: object) -> None:
    app.dependency_overrides[get_triage_client] = lambda: triage_client


def _clear_triage_override() -> None:
    app.dependency_overrides.pop(get_triage_client, None)


def test_triage_stores_result_and_timestamp(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    conversation = _owned_conversation(client, superuser_token_headers, "Hello there")
    updated_at_before = conversation["updated_at"]
    _use_triage_client(ScriptedTriageClient([_triage_payload()]))
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Customer asks about an invoice"
    assert body["intent"] == "billing_question"
    assert body["sentiment"] == "negative"
    assert body["next_action"] == "Send the invoice"
    assert body["triage_at"]
    ConversationTriagePublic.model_validate(body)

    stored = db.get(Conversation, conversation["id"])
    assert stored is not None
    db.refresh(stored)
    assert stored.triage_summary == "Customer asks about an invoice"
    assert stored.triage_intent == "billing_question"
    assert stored.triage_sentiment == "negative"
    assert stored.triage_next_action == "Send the invoice"
    assert stored.triage_at is not None
    assert stored.updated_at is not None
    assert stored.updated_at.isoformat().replace("+00:00", "Z") == updated_at_before


def test_triage_result_is_readable_on_conversation(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    conversation = _owned_conversation(client, superuser_token_headers, "Hello there")
    _use_triage_client(ScriptedTriageClient([_triage_payload()]))
    try:
        client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()

    response = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["triage_summary"] == "Customer asks about an invoice"
    assert body["triage_sentiment"] == "negative"
    assert body["triage_at"]


def test_second_triage_replaces_the_first(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    conversation = _owned_conversation(client, superuser_token_headers, "Hello there")
    _use_triage_client(ScriptedTriageClient([_triage_payload()]))
    try:
        first = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        ).json()

        _use_triage_client(
            ScriptedTriageClient(
                [_triage_payload(summary="A newer summary", sentiment="positive")]
            )
        )
        second = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        ).json()
    finally:
        _clear_triage_override()

    assert second["summary"] == "A newer summary"
    assert second["sentiment"] == "positive"
    assert second["triage_at"] >= first["triage_at"]

    detail = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}",
        headers=superuser_token_headers,
    ).json()
    assert detail["triage_summary"] == "A newer summary"


def test_triage_retries_once_then_succeeds(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    conversation = _owned_conversation(client, superuser_token_headers, "Hello there")
    scripted = ScriptedTriageClient([TriageProviderError("boom"), _triage_payload()])
    _use_triage_client(scripted)
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()

    assert response.status_code == 200
    assert scripted.calls == 2


def test_triage_timeout_returns_504_and_stores_nothing(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    conversation = _owned_conversation(
        client, superuser_token_headers, TRIAGE_TRANSCRIPT_MARKER
    )
    _use_triage_client(ScriptedTriageClient([TriageTimeoutError("slow")]))
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()

    assert response.status_code == 504
    assert response.json()["detail"] == "Triage timed out"
    assert TRIAGE_TRANSCRIPT_MARKER not in response.text

    stored = db.get(Conversation, conversation["id"])
    assert stored is not None
    db.refresh(stored)
    assert stored.triage_summary is None
    assert stored.triage_at is None


def test_triage_invalid_payload_returns_502_and_stores_nothing(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    conversation = _owned_conversation(
        client, superuser_token_headers, TRIAGE_TRANSCRIPT_MARKER
    )
    _use_triage_client(ScriptedTriageClient([_triage_payload(sentiment="furious")]))
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()

    assert response.status_code == 502
    assert response.json()["detail"] == "Triage provider failed"
    assert TRIAGE_TRANSCRIPT_MARKER not in response.text

    stored = db.get(Conversation, conversation["id"])
    assert stored is not None
    db.refresh(stored)
    assert stored.triage_summary is None


def test_failed_triage_preserves_previous_result(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    conversation = _owned_conversation(client, superuser_token_headers, "Hello there")
    _use_triage_client(ScriptedTriageClient([_triage_payload()]))
    try:
        client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
        _use_triage_client(ScriptedTriageClient([TriageProviderError("boom")]))
        failed = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()

    assert failed.status_code == 502

    detail = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}",
        headers=superuser_token_headers,
    ).json()
    assert detail["triage_summary"] == "Customer asks about an invoice"


def test_triage_requires_owner(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    conversation = create_random_conversation(db)
    _use_triage_client(ScriptedTriageClient([_triage_payload()]))
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation.id}/triage",
            headers=normal_user_token_headers,
        )
    finally:
        _clear_triage_override()

    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"


def test_triage_denies_superuser_on_other_users_conversation(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    conversation = create_random_conversation(db)
    _use_triage_client(ScriptedTriageClient([_triage_payload()]))
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation.id}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()

    assert response.status_code == 403


def test_triage_unknown_conversation_returns_404(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    _use_triage_client(ScriptedTriageClient([_triage_payload()]))
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{uuid.uuid4()}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_triage_requires_auth(client: TestClient) -> None:
    _use_triage_client(ScriptedTriageClient([_triage_payload()]))
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{uuid.uuid4()}/triage"
        )
    finally:
        _clear_triage_override()

    assert response.status_code == 401


def test_default_fake_triage_client_is_used(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    conversation = _owned_conversation(client, superuser_token_headers, "Hello there")
    response = client.post(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    assert response.json()["summary"] == "Fake triage summary"


@pytest.fixture(autouse=True)
def _clear_triage_client_override():
    yield
    _clear_triage_override()


# ---------------------------------------------------------------------------
# Usage accounting
# ---------------------------------------------------------------------------


def _usage_rows(db: Session) -> list[TriageUsage]:
    return list(db.exec(select(TriageUsage)).all())


def _clear_usage(db: Session) -> None:
    """Usage rows outlive the shared session fixture, so start clean."""
    db.exec(delete(TriageUsage))
    db.commit()


def test_triage_success_records_content_free_usage(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    conversation = _owned_conversation(
        client, superuser_token_headers, TRIAGE_TRANSCRIPT_MARKER
    )
    _clear_usage(db)
    _use_triage_client(
        ScriptedTriageClient(
            [_triage_payload()], provider="example-provider", model="example-model"
        )
    )
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()
    assert response.status_code == 200

    db.expire_all()
    rows = _usage_rows(db)
    assert len(rows) == 1
    usage = rows[0]
    assert TriageUsageOutcome(usage.outcome) is TriageUsageOutcome.SUCCEEDED
    assert usage.provider == "example-provider"
    assert usage.model == "example-model"
    assert usage.attempts == 1
    assert usage.latency_ms >= 0
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.created_at is not None
    assert TRIAGE_TRANSCRIPT_MARKER not in repr(usage.__dict__)
    assert conversation["id"] not in repr(usage.__dict__)


def test_usage_row_has_only_content_free_fields() -> None:
    assert set(TriageUsage.model_fields) == {
        "id",
        "created_at",
        "provider",
        "model",
        "outcome",
        "attempts",
        "latency_ms",
        "input_tokens",
        "output_tokens",
    }


def test_triage_timeout_records_timeout_usage(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    conversation = _owned_conversation(
        client, superuser_token_headers, TRIAGE_TRANSCRIPT_MARKER
    )
    _clear_usage(db)
    _use_triage_client(ScriptedTriageClient([TriageTimeoutError("slow")]))
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()
    assert response.status_code == 504

    db.expire_all()
    rows = _usage_rows(db)
    assert len(rows) == 1
    assert TriageUsageOutcome(rows[0].outcome) is TriageUsageOutcome.TIMEOUT
    assert rows[0].attempts == 2
    assert rows[0].input_tokens is None
    assert rows[0].output_tokens is None


def test_triage_invalid_payload_records_invalid_response_usage(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    conversation = _owned_conversation(client, superuser_token_headers, "Hello there")
    _clear_usage(db)
    _use_triage_client(ScriptedTriageClient(["{not json"]))
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()
    assert response.status_code == 502

    db.expire_all()
    rows = _usage_rows(db)
    assert len(rows) == 1
    assert TriageUsageOutcome(rows[0].outcome) is TriageUsageOutcome.INVALID_RESPONSE


def test_triage_provider_error_records_provider_error_usage(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    conversation = _owned_conversation(client, superuser_token_headers, "Hello there")
    _clear_usage(db)
    _use_triage_client(ScriptedTriageClient([TriageProviderError("boom")]))
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()
    assert response.status_code == 502

    db.expire_all()
    rows = _usage_rows(db)
    assert len(rows) == 1
    assert TriageUsageOutcome(rows[0].outcome) is TriageUsageOutcome.PROVIDER_ERROR


def test_usage_recording_failure_does_not_block_triage(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import conversations as conversations_module

    class ExplodingUsage:
        def __init__(self, **kwargs: object) -> None:
            raise RuntimeError("usage store unavailable")

    monkeypatch.setattr(conversations_module, "TriageUsage", ExplodingUsage)

    conversation = _owned_conversation(client, superuser_token_headers, "Hello there")
    _clear_usage(db)
    _use_triage_client(ScriptedTriageClient([_triage_payload()]))
    try:
        response = client.post(
            f"{settings.API_V1_STR}/conversations/{conversation['id']}/triage",
            headers=superuser_token_headers,
        )
    finally:
        _clear_triage_override()

    assert response.status_code == 200
    assert response.json()["summary"] == "Customer asks about an invoice"

    stored = db.get(Conversation, conversation["id"])
    assert stored is not None
    db.refresh(stored)
    assert stored.triage_summary == "Customer asks about an invoice"

    db.expire_all()
    assert _usage_rows(db) == []
