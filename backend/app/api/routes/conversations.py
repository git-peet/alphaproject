import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    CONVERSATION_TRANSCRIPT_MAX_LENGTH,
    Conversation,
    ConversationCreate,
    ConversationPublic,
    ConversationsPublic,
    ConversationSummary,
    ConversationUpdate,
    Message,
    get_datetime_utc,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _validate_transcript_length(transcript: str | None) -> None:
    """Reject oversized transcripts without echoing their contents.

    The schema deliberately has no max_length so FastAPI's validation handler
    cannot return the submitted text in the 422 body.
    """
    if transcript is None:
        return
    if len(transcript) > CONVERSATION_TRANSCRIPT_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=(
                "Transcript exceeds the maximum length of "
                f"{CONVERSATION_TRANSCRIPT_MAX_LENGTH} characters"
            ),
        )


def _get_owned_conversation(
    *, session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Conversation:
    """Return the conversation only if the caller owns it.

    Conversations are private: superuser status does not grant cross-user access.
    """
    conversation = session.get(Conversation, id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return conversation


@router.get("/", response_model=ConversationsPublic)
def read_conversations(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    """
    Retrieve conversations owned by the current user.
    """
    count_statement = (
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.owner_id == current_user.id)
    )
    count = session.exec(count_statement).one()
    statement = (
        select(Conversation)
        .where(Conversation.owner_id == current_user.id)
        .order_by(col(Conversation.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    conversations = session.exec(statement).all()
    return ConversationsPublic(
        data=[ConversationSummary.model_validate(item) for item in conversations],
        count=count,
    )


@router.get("/{id}", response_model=ConversationPublic)
def read_conversation(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Any:
    """
    Get one conversation owned by the current user.
    """
    return _get_owned_conversation(
        session=session, current_user=current_user, id=id
    )


@router.post("/", response_model=ConversationPublic)
def create_conversation(
    *, session: SessionDep, current_user: CurrentUser, conversation_in: ConversationCreate
) -> Any:
    """
    Create a conversation owned by the current user.
    """
    _validate_transcript_length(conversation_in.transcript)
    conversation = Conversation.model_validate(
        conversation_in, update={"owner_id": current_user.id}
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


@router.put("/{id}", response_model=ConversationPublic)
def update_conversation(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    conversation_in: ConversationUpdate,
) -> Any:
    """
    Update a conversation owned by the current user.
    """
    conversation = _get_owned_conversation(
        session=session, current_user=current_user, id=id
    )
    update_dict = conversation_in.model_dump(exclude_unset=True)
    _validate_transcript_length(update_dict.get("transcript"))
    conversation.sqlmodel_update(update_dict)
    conversation.updated_at = get_datetime_utc()
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


@router.delete("/{id}")
def delete_conversation(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Message:
    """
    Delete a conversation owned by the current user.
    """
    conversation = _get_owned_conversation(
        session=session, current_user=current_user, id=id
    )
    session.delete(conversation)
    session.commit()
    return Message(message="Conversation deleted successfully")
