from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import case, or_
from sqlmodel import func, select

from app.api.deps import SessionDep, get_current_active_superuser
from app.models import (
    TriageUsage,
    TriageUsageBucket,
    TriageUsageOutcome,
    TriageUsageSummary,
)

router = APIRouter(
    prefix="/triage-usage",
    tags=["triage-usage"],
    dependencies=[Depends(get_current_active_superuser)],
)


@router.get("/", response_model=TriageUsageSummary)
def read_triage_usage(session: SessionDep) -> Any:
    """
    Read aggregate triage usage metadata.

    Content-free by construction: only provider/model identifiers, outcomes,
    attempts, latency, and optional token counts are stored. Admin only.
    """
    total = session.exec(select(func.count()).select_from(TriageUsage)).one()

    unknown_tokens = func.sum(
        case(
            (
                or_(
                    TriageUsage.input_tokens.is_(None),
                    TriageUsage.output_tokens.is_(None),
                ),
                1,
            ),
            else_=0,
        )
    ).label("unknown_token_count")

    statement = (
        select(
            TriageUsage.provider,
            TriageUsage.model,
            TriageUsage.outcome,
            func.count().label("count"),
            func.avg(TriageUsage.latency_ms).label("avg_latency_ms"),
            func.max(TriageUsage.latency_ms).label("max_latency_ms"),
            func.sum(TriageUsage.input_tokens).label("input_tokens_total"),
            func.sum(TriageUsage.output_tokens).label("output_tokens_total"),
            unknown_tokens,
        )
        .group_by(TriageUsage.provider, TriageUsage.model, TriageUsage.outcome)
        .order_by(TriageUsage.provider, TriageUsage.model, TriageUsage.outcome)
    )

    buckets = [
        TriageUsageBucket(
            provider=row[0],
            model=row[1],
            outcome=TriageUsageOutcome(row[2]),
            count=row[3],
            avg_latency_ms=float(row[4] or 0),
            max_latency_ms=int(row[5] or 0),
            input_tokens_total=row[6],
            output_tokens_total=row[7],
            unknown_token_count=int(row[8] or 0),
        )
        for row in session.exec(statement).all()
    ]

    return TriageUsageSummary(total=total, buckets=buckets)
