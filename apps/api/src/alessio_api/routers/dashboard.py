"""API do painel web.

Fase 0: sem login; tudo é filtrado pela organização ``ALESSIO_DASHBOARD_ORG_ID``.
A Fase 1 troca ``current_organization`` por autenticação de usuários e RLS.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from alessio_api.db import get_session
from alessio_api.models import Agent, Camera, Occurrence, Zone, ZoneMetric1m
from alessio_api.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["painel"])

SessionDep = Annotated[Session, Depends(get_session)]


def current_organization() -> UUID:
    org_id = get_settings().dashboard_org_id
    if org_id is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "ALESSIO_DASHBOARD_ORG_ID não configurado"
        )
    return org_id


OrgDep = Annotated[UUID, Depends(current_organization)]


class OccurrenceOut(BaseModel):
    id: UUID
    camera_id: UUID
    camera_name: str
    zone_id: UUID
    zone_name: str
    event_type: str
    is_shadow: bool
    state: str
    review_status: str
    started_at: datetime
    ended_at: datetime | None
    last_observed_at: datetime
    close_reason: str | None
    max_people: int
    max_confidence: float


class CameraOut(BaseModel):
    id: UUID
    name: str
    status: str
    status_detail: str | None
    last_frame_at: datetime | None
    last_status_at: datetime | None
    agent_last_seen_at: datetime | None


class ZoneMetricOut(BaseModel):
    bucket_start: datetime
    analyzed_seconds: float
    occupancy_avg: float
    occupancy_max: int


@router.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/occurrences", response_model=list[OccurrenceOut])
def list_occurrences(
    org_id: OrgDep,
    session: SessionDep,
    state: Literal["open", "closed"] | None = None,
    include_shadow: bool = False,
    before: Annotated[
        datetime | None, Query(description="cursor: started_at do último item")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[OccurrenceOut]:
    query = (
        select(Occurrence, Camera.name, Zone.name)
        .join(Camera, Camera.id == Occurrence.camera_id)
        .join(Zone, Zone.id == Occurrence.zone_id)
        .where(Occurrence.organization_id == org_id)
        .order_by(Occurrence.started_at.desc())
        .limit(limit)
    )
    if state:
        query = query.where(Occurrence.state == state)
    if not include_shadow:
        query = query.where(Occurrence.is_shadow.is_(False))
    if before:
        query = query.where(Occurrence.started_at < before)
    return [
        OccurrenceOut(
            id=o.id,
            camera_id=o.camera_id,
            camera_name=camera_name,
            zone_id=o.zone_id,
            zone_name=zone_name,
            event_type=o.event_type,
            is_shadow=o.is_shadow,
            state=o.state,
            review_status=o.review_status,
            started_at=o.started_at,
            ended_at=o.ended_at,
            last_observed_at=o.last_observed_at,
            close_reason=o.close_reason,
            max_people=o.max_people,
            max_confidence=o.max_confidence,
        )
        for o, camera_name, zone_name in session.execute(query)
    ]


@router.get("/cameras", response_model=list[CameraOut])
def list_cameras(org_id: OrgDep, session: SessionDep) -> list[CameraOut]:
    rows = session.execute(
        select(Camera, Agent.last_seen_at)
        .join(Agent, Agent.id == Camera.agent_id)
        .where(Camera.organization_id == org_id)
        .order_by(Camera.name)
    )
    return [
        CameraOut(
            id=camera.id,
            name=camera.name,
            status=camera.status,
            status_detail=camera.status_detail,
            last_frame_at=camera.last_frame_at,
            last_status_at=camera.last_status_at,
            agent_last_seen_at=last_seen,
        )
        for camera, last_seen in rows
    ]


@router.get("/zones/{zone_id}/metrics", response_model=list[ZoneMetricOut])
def zone_metrics(
    zone_id: UUID,
    org_id: OrgDep,
    session: SessionDep,
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
) -> list[ZoneMetricOut]:
    rows = session.scalars(
        select(ZoneMetric1m)
        .where(
            ZoneMetric1m.organization_id == org_id,
            ZoneMetric1m.zone_id == zone_id,
            ZoneMetric1m.bucket_start >= start,
            ZoneMetric1m.bucket_start < end,
        )
        .order_by(ZoneMetric1m.bucket_start)
        .limit(1440)
    )
    return [
        ZoneMetricOut(
            bucket_start=m.bucket_start,
            analyzed_seconds=m.analyzed_seconds,
            occupancy_avg=m.occupancy_avg,
            occupancy_max=m.occupancy_max,
        )
        for m in rows
    ]
