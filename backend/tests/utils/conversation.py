from sqlmodel import Session

from app import crud
from app.models import Conversation, ConversationCreate
from tests.utils.user import create_random_user
from tests.utils.utils import random_lower_string


def create_random_conversation(db: Session) -> Conversation:
    user = create_random_user(db)
    owner_id = user.id
    assert owner_id is not None
    title = random_lower_string()
    transcript = random_lower_string()
    conversation_in = ConversationCreate(title=title, transcript=transcript)
    return crud.create_conversation(
        session=db, conversation_in=conversation_in, owner_id=owner_id
    )
