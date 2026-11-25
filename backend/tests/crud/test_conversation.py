from sqlmodel import Session

from app import crud
from app.models import Conversation, ConversationCreate, ConversationUpdate
from tests.utils.user import create_random_user
from tests.utils.utils import random_lower_string


def test_create_conversation(db: Session) -> None:
    user = create_random_user(db)
    title = random_lower_string()
    transcript = random_lower_string()
    conversation_in = ConversationCreate(title=title, transcript=transcript)
    conversation = crud.create_conversation(
        session=db, conversation_in=conversation_in, owner_id=user.id
    )
    assert conversation.title == title
    assert conversation.transcript == transcript
    assert conversation.owner_id == user.id
    assert conversation.created_at is not None
    assert conversation.updated_at is not None


def test_conversation_persists_across_sessions(db: Session) -> None:
    user = create_random_user(db)
    conversation_in = ConversationCreate(
        title=random_lower_string(), transcript=random_lower_string()
    )
    conversation = crud.create_conversation(
        session=db, conversation_in=conversation_in, owner_id=user.id
    )
    conversation_id = conversation.id
    db.expunge_all()

    reloaded = db.get(Conversation, conversation_id)
    assert reloaded is not None
    assert reloaded.transcript == conversation_in.transcript


def test_conversation_update_changes_updated_at(db: Session) -> None:
    user = create_random_user(db)
    conversation = crud.create_conversation(
        session=db,
        conversation_in=ConversationCreate(
            title=random_lower_string(), transcript=random_lower_string()
        ),
        owner_id=user.id,
    )
    before = conversation.updated_at
    from app.models import get_datetime_utc

    conversation.sqlmodel_update(
        ConversationUpdate(title="changed").model_dump(exclude_unset=True)
    )
    conversation.updated_at = get_datetime_utc()
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    assert conversation.updated_at > before
