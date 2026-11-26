import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import EmailStr, StringConstraints
from sqlalchemy import String
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    items: list[Item] = Relationship(back_populates="owner", cascade_delete=True)
    conversations: list[Conversation] = Relationship(
        back_populates="owner", cascade_delete=True
    )


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


class ItemPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    priority: ItemPriority = Field(
        default=ItemPriority.NORMAL, sa_type=String(16), max_length=16
    )


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    priority: ItemPriority | None = None


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


CONVERSATION_TITLE_MAX_LENGTH = 255
CONVERSATION_TRANSCRIPT_MAX_LENGTH = 20_000

TRIAGE_SUMMARY_MAX_LENGTH = 1000
TRIAGE_INTENT_MAX_LENGTH = 64
TRIAGE_NEXT_ACTION_MAX_LENGTH = 500

TRIAGE_USAGE_PROVIDER_MAX_LENGTH = 64
TRIAGE_USAGE_MODEL_MAX_LENGTH = 96


class TriageUsageOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    INVALID_RESPONSE = "invalid_response"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"


class TriageSentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


# Shared properties
class ConversationBase(SQLModel):
    title: str = Field(min_length=1, max_length=CONVERSATION_TITLE_MAX_LENGTH)
    # No Pydantic max_length: enforced in the route so the 422 body never echoes
    # the transcript. The database column is the backstop.
    transcript: str = Field(
        min_length=1,
        sa_type=String(CONVERSATION_TRANSCRIPT_MAX_LENGTH),
        description=(
            f"Up to {CONVERSATION_TRANSCRIPT_MAX_LENGTH} characters. "
            "Longer transcripts are rejected without echoing the text."
        ),
    )


# Properties to receive on conversation creation
class ConversationCreate(ConversationBase):
    pass


# Properties to receive on conversation update
class ConversationUpdate(SQLModel):
    title: str | None = Field(
        default=None, min_length=1, max_length=CONVERSATION_TITLE_MAX_LENGTH
    )
    transcript: str | None = Field(default=None, min_length=1)


# Database model, database table inferred from class name
class Conversation(ConversationBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    updated_at: datetime | None = Field(default_factory=get_datetime_utc)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="conversations")
    triage_summary: str | None = Field(
        default=None,
        max_length=TRIAGE_SUMMARY_MAX_LENGTH,
        sa_type=String(TRIAGE_SUMMARY_MAX_LENGTH),
    )
    triage_intent: str | None = Field(
        default=None,
        max_length=TRIAGE_INTENT_MAX_LENGTH,
        sa_type=String(TRIAGE_INTENT_MAX_LENGTH),
    )
    triage_sentiment: str | None = Field(
        default=None, max_length=16, sa_type=String(16)
    )
    triage_next_action: str | None = Field(
        default=None,
        max_length=TRIAGE_NEXT_ACTION_MAX_LENGTH,
        sa_type=String(TRIAGE_NEXT_ACTION_MAX_LENGTH),
    )
    triage_at: datetime | None = Field(default=None)


# List projection, deliberately without the transcript
class ConversationSummary(SQLModel):
    id: uuid.UUID
    title: str
    owner_id: uuid.UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None


# Properties to return via API, id is always required
class ConversationPublic(ConversationBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None
    triage_summary: str | None = None
    triage_intent: str | None = None
    triage_sentiment: TriageSentiment | None = None
    triage_next_action: str | None = None
    triage_at: datetime | None = None


class ConversationTriage(SQLModel):
    """The validated triage result contract."""

    summary: str = Field(min_length=1, max_length=TRIAGE_SUMMARY_MAX_LENGTH)
    intent: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=TRIAGE_INTENT_MAX_LENGTH,
            pattern=r"^[a-z][a-z0-9_-]*$",
        ),
    ]
    sentiment: TriageSentiment
    next_action: str = Field(min_length=1, max_length=TRIAGE_NEXT_ACTION_MAX_LENGTH)


class ConversationTriagePublic(ConversationTriage):
    triage_at: datetime


class ConversationsPublic(SQLModel):
    data: list[ConversationSummary]
    count: int


# Content-free triage usage accounting. Deliberately stores no conversation or
# user identifier, and no transcript, prompt, model output, or credential.
class TriageUsage(SQLModel, table=True):
    __tablename__ = "triage_usage"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=get_datetime_utc, index=True, nullable=False
    )
    provider: str | None = Field(
        default=None,
        max_length=TRIAGE_USAGE_PROVIDER_MAX_LENGTH,
        sa_type=String(TRIAGE_USAGE_PROVIDER_MAX_LENGTH),
    )
    model: str | None = Field(
        default=None,
        max_length=TRIAGE_USAGE_MODEL_MAX_LENGTH,
        sa_type=String(TRIAGE_USAGE_MODEL_MAX_LENGTH),
    )
    outcome: TriageUsageOutcome = Field(sa_type=String(32), max_length=32)
    attempts: int
    latency_ms: int
    # NULL means the client did not supply the count; values are never estimated.
    input_tokens: int | None = Field(default=None)
    output_tokens: int | None = Field(default=None)


class TriageUsageBucket(SQLModel):
    provider: str | None = None
    model: str | None = None
    outcome: TriageUsageOutcome
    count: int
    avg_latency_ms: float
    max_latency_ms: int
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None
    unknown_token_count: int


class TriageUsageSummary(SQLModel):
    total: int
    buckets: list[TriageUsageBucket]


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
