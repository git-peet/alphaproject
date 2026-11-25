import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models import (
    CONVERSATION_TRANSCRIPT_MAX_LENGTH,
    Conversation,
    User,
    UserUpdate,
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
