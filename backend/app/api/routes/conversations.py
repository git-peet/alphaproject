import logging
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
    ConversationTriagePublic,
    ConversationUpdate,
    Message,
    TriageUsage,
    get_datetime_utc,
)
from app.triage import (
    TriageClientDep,
    TriageRun,
    TriageTimeoutError,
    run_triage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _record_triage_usage(session: SessionDep, run: TriageRun) -> None:
    """Record content-free usage metadata without ever blocking triage.

    Only provider/model identifiers, the outcome, the attempt count, local
    latency, and optional token counts are stored. No conversation, user, or
    content identifier is included.
    """
    try:
        session.add(
            TriageUsage(
                provider=run.provider,
                model=run.model,
                outcome=run.outcome,
                attempts=run.attempts,
                latency_ms=run.latency_ms,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
            )
        )
        session.commit()
    except Exception:  # noqa: BLE001 - accounting must never break triage
        session.rollback()
        logger.warning("Could not record triage usage metadata")


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


@router.post("/{id}/triage", response_model=ConversationTriagePublic)
def triage_conversation(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    triage_client: TriageClientDep,
) -> Any:
    """
    Triage a conversation owned by the current user.

    Each successful triage replaces the previous stored result. A failed triage
    stores nothing and leaves any previous result intact.
    """
    conversation = _get_owned_conversation(
        session=session, current_user=current_user, id=id
    )
    run = run_triage(client=triage_client, transcript=conversation.transcript)

    if not run.succeeded:
        _record_triage_usage(session, run)
        if isinstance(run.error, TriageTimeoutError):
            raise HTTPException(status_code=504, detail="Triage timed out")
        raise HTTPException(status_code=502, detail="Triage provider failed")

    result = run.result
    if result is None:  # defensive: succeeded implies a validated result
        _record_triage_usage(session, run)
        raise HTTPException(status_code=502, detail="Triage provider failed")

    triaged_at = get_datetime_utc()
    conversation.sqlmodel_update(
        {
            "triage_summary": result.summary,
            "triage_intent": result.intent,
            "triage_sentiment": result.sentiment.value,
            "triage_next_action": result.next_action,
            "triage_at": triaged_at,
        }
    )
    session.add(conversation)
    session.commit()
    _record_triage_usage(session, run)
    return ConversationTriagePublic(
        summary=result.summary,
        intent=result.intent,
        sentiment=result.sentiment,
        next_action=result.next_action,
        triage_at=triaged_at,
    )


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
