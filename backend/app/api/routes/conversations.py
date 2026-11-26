import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    CONVERSATION_TRANSCRIPT_MAX_LENGTH,
    Conversation,
    ConversationCreate,
    ConversationPublic,
    ConversationsPublic,
    ConversationSummary,
    ConversationTriageFeedbackPublic,
    ConversationTriagePublic,
    ConversationUpdate,
    Message,
    TriageFeedbackUpdate,
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

MAX_CONVERSATION_PAGE_SIZE = 100
CONVERSATION_SEARCH_MAX_LENGTH = 100

EXPORT_FORMAT = "conversation-export"
EXPORT_VERSION = 1
MAX_EXPORT_BYTES = 64 * 1024

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
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=MAX_CONVERSATION_PAGE_SIZE, ge=1, le=MAX_CONVERSATION_PAGE_SIZE),
    search: str | None = Query(
        default=None, max_length=CONVERSATION_SEARCH_MAX_LENGTH
    ),
) -> Any:
    """
    Retrieve conversations owned by the current user.

    `search` is a bounded, case-insensitive title match. It is never logged.
    The returned `count` is the filtered total for the owner.
    """
    filters = [Conversation.owner_id == current_user.id]
    term = (search or "").strip()
    if term:
        filters.append(col(Conversation.title).icontains(term, autoescape=True))

    count_statement = select(func.count()).select_from(Conversation).where(*filters)
    count = session.exec(count_statement).one()

    statement = (
        select(Conversation)
        .where(*filters)
        .order_by(col(Conversation.created_at).desc(), col(Conversation.id).desc())
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


@router.get("/{id}/export")
def export_conversation(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Response:
    """
    Export one owned conversation as a downloadable JSON document.

    The document includes only explicitly selected fields: the conversation id,
    title, transcript and timestamps plus the current triage metadata. The owner
    id is deliberately excluded. Export never mutates the stored conversation and
    never logs its content.
    """
    conversation = _get_owned_conversation(
        session=session, current_user=current_user, id=id
    )

    triage: dict[str, Any] | None = None
    if conversation.triage_at is not None:
        triage = {
            "summary": conversation.triage_summary,
            "intent": conversation.triage_intent,
            "sentiment": conversation.triage_sentiment,
            "next_action": conversation.triage_next_action,
            "triage_at": conversation.triage_at.isoformat(),
        }

    document = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": get_datetime_utc().isoformat(),
        "conversation": {
            "id": str(conversation.id),
            "title": conversation.title,
            "transcript": conversation.transcript,
            "created_at": conversation.created_at.isoformat()
            if conversation.created_at
            else None,
            "updated_at": conversation.updated_at.isoformat()
            if conversation.updated_at
            else None,
        },
        "triage": triage,
    }

    body = json.dumps(document, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_EXPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail="This conversation is too large to export",
        )

    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="conversation-{conversation.id}.json"'
            )
        },
    )


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
            # Feedback rated a result that no longer exists after re-triage.
            "triage_feedback": None,
            "triage_feedback_at": None,
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


@router.put(
    "/{id}/triage/feedback", response_model=ConversationTriageFeedbackPublic
)
def set_triage_feedback(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    feedback_in: TriageFeedbackUpdate,
) -> Any:
    """
    Rate the current triage result of a conversation owned by the current user.

    Feedback never changes the triage result itself.
    """
    conversation = _get_owned_conversation(
        session=session, current_user=current_user, id=id
    )
    if conversation.triage_at is None:
        raise HTTPException(status_code=409, detail="No triage result to rate")

    feedback_at = get_datetime_utc()
    conversation.sqlmodel_update(
        {
            "triage_feedback": feedback_in.feedback.value,
            "triage_feedback_at": feedback_at,
        }
    )
    session.add(conversation)
    session.commit()
    return ConversationTriageFeedbackPublic(
        feedback=feedback_in.feedback, feedback_at=feedback_at
    )


@router.delete(
    "/{id}/triage/feedback", response_model=ConversationTriageFeedbackPublic
)
def clear_triage_feedback(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Any:
    """
    Clear the feedback on the current triage result. Safe to repeat.
    """
    conversation = _get_owned_conversation(
        session=session, current_user=current_user, id=id
    )
    conversation.sqlmodel_update(
        {"triage_feedback": None, "triage_feedback_at": None}
    )
    session.add(conversation)
    session.commit()
    return ConversationTriageFeedbackPublic(feedback=None, feedback_at=None)


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
