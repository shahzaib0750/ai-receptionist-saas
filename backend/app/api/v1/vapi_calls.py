from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_business_permission
from app.db.session import get_db
from app.models.business import Business
from app.models.vapi_call import VapiCall
from app.schemas.vapi_call import (
    VapiCallPage,
    VapiCallRead,
    VapiCallStatusFilter,
    VapiCallSummary,
)
from app.services.business_authorization import BusinessPermission

router = APIRouter(prefix="/businesses/{business_id}/calls", tags=["Vapi calls"])


@router.get("", response_model=VapiCallPage)
def list_business_calls(
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.READ_CALLS)),
    ],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    call_status: Annotated[
        VapiCallStatusFilter | None,
        Query(alias="status"),
    ] = None,
    sort_by: Literal["created_at", "updated_at"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    created_after: AwareDatetime | None = None,
    created_before: AwareDatetime | None = None,
    caller: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> VapiCallPage:
    if (
        created_after is not None
        and created_before is not None
        and created_after >= created_before
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid call date range",
        )

    filters = [VapiCall.business_id == business.id]
    if call_status is not None:
        filters.append(VapiCall.status == call_status)
    if created_after is not None:
        filters.append(VapiCall.created_at >= created_after)
    if created_before is not None:
        filters.append(VapiCall.created_at < created_before)
    if caller is not None:
        caller = caller.strip()
        if not caller:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Caller search must not be empty",
            )
        filters.append(VapiCall.caller_number.ilike(f"%{caller}%"))

    total = db.scalar(select(func.count()).select_from(VapiCall).where(*filters)) or 0
    sort_column = (
        VapiCall.created_at if sort_by == "created_at" else VapiCall.updated_at
    )
    order_by = sort_column.asc() if sort_order == "asc" else sort_column.desc()
    calls = db.scalars(
        select(VapiCall)
        .where(*filters)
        .order_by(order_by, VapiCall.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return VapiCallPage(
        items=[VapiCallSummary.model_validate(call) for call in calls],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{call_id}", response_model=VapiCallRead)
def get_business_call(
    call_id: UUID,
    business: Annotated[
        Business,
        Depends(require_business_permission(BusinessPermission.READ_CALLS)),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> VapiCall:
    call = db.scalar(
        select(VapiCall).where(
            VapiCall.id == call_id,
            VapiCall.business_id == business.id,
        )
    )
    if call is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found",
        )
    return call
