"""API do painel: ocorrências, câmeras e métricas da organização ativa.

Além do filtro explícito por ``organization_id``, o banco aplica Row-Level
Security com a organização da sessão (``auth.current_principal``).
"""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from alessio_api import audit
from alessio_api.auth import Principal, require
from alessio_api.db import get_session
from alessio_api.models import Agent, Camera, Occurrence, Zone, ZoneMetric1m
from alessio_api.permissions import Permission
from alessio_api.services import active_services, hidden_cameras, history_status

router = APIRouter(prefix="/api/v1", tags=["painel"])

SessionDep = Annotated[Session, Depends(get_session)]


def _org(permission: Permission):
    def dependency(principal: Annotated[Principal, Depends(require(permission))]) -> UUID:
        return principal.organization_id

    return dependency


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
    reviewed_at: datetime | None
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
    services: list[str]
    # Modalidades encerradas ainda consultáveis: {"security": fim da consulta}.
    history_until: dict[str, datetime]


class ZoneMetricOut(BaseModel):
    bucket_start: datetime
    analyzed_seconds: float
    occupancy_avg: float
    occupancy_max: int


@router.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    return {"status": "ok"}


def _occurrence_out(o: Occurrence, camera_name: str, zone_name: str) -> OccurrenceOut:
    return OccurrenceOut(
        id=o.id,
        camera_id=o.camera_id,
        camera_name=camera_name,
        zone_id=o.zone_id,
        zone_name=zone_name,
        event_type=o.event_type,
        is_shadow=o.is_shadow,
        state=o.state,
        review_status=o.review_status,
        reviewed_at=o.reviewed_at,
        started_at=o.started_at,
        ended_at=o.ended_at,
        last_observed_at=o.last_observed_at,
        close_reason=o.close_reason,
        max_people=o.max_people,
        max_confidence=o.max_confidence,
    )


class ReviewIn(BaseModel):
    review_status: Literal["acknowledged", "resolved"]


@router.patch("/occurrences/{occurrence_id}/review", response_model=OccurrenceOut)
def review_occurrence(
    occurrence_id: UUID,
    body: ReviewIn,
    principal: Annotated[Principal, Depends(require(Permission.OCCURRENCES_REVIEW))],
    session: SessionDep,
) -> OccurrenceOut:
    row = session.execute(
        select(Occurrence, Camera.name, Zone.name)
        .join(Camera, Camera.id == Occurrence.camera_id)
        .join(Zone, Zone.id == Occurrence.zone_id)
        .where(
            Occurrence.id == occurrence_id,
            Occurrence.organization_id == principal.organization_id,
        )
        .with_for_update(of=Occurrence)
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ocorrência não encontrada")
    occurrence = row[0]
    occurrence.review_status = body.review_status
    occurrence.reviewed_at = datetime.now(UTC)
    occurrence.reviewed_by = principal.user.id
    audit.record(
        session,
        occurrence.organization_id,
        principal.user.id,
        f"occurrence.{body.review_status}",
        "occurrence",
        occurrence.id,
    )
    session.commit()
    return _occurrence_out(occurrence, row[1], row[2])


@router.get("/occurrences", response_model=list[OccurrenceOut])
def list_occurrences(
    org_id: Annotated[UUID, Depends(_org(Permission.OCCURRENCES_READ))],
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
    # Serviço encerrado há mais de 30 dias: o histórico de ocorrências some do painel.
    hidden = hidden_cameras(session, org_id, "security")
    if hidden:
        query = query.where(Occurrence.camera_id.not_in(hidden))
    if state:
        query = query.where(Occurrence.state == state)
    if not include_shadow:
        query = query.where(Occurrence.is_shadow.is_(False))
    if before:
        query = query.where(Occurrence.started_at < before)
    return [
        _occurrence_out(o, camera_name, zone_name)
        for o, camera_name, zone_name in session.execute(query)
    ]


@router.get("/cameras", response_model=list[CameraOut])
def list_cameras(
    org_id: Annotated[UUID, Depends(_org(Permission.CAMERAS_READ))], session: SessionDep
) -> list[CameraOut]:
    active = active_services(session, org_id)
    history = history_status(session, org_id)
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
            services=sorted(active.get(camera.id, set())),
            history_until={
                service: status.visible_until
                for (camera_id, service), status in history.items()
                if camera_id == camera.id and status.state == "grace"
            },
        )
        for camera, last_seen in rows
    ]


@router.get("/zones/{zone_id}/metrics", response_model=list[ZoneMetricOut])
def zone_metrics(
    zone_id: UUID,
    org_id: Annotated[UUID, Depends(_org(Permission.METRICS_READ))],
    session: SessionDep,
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
) -> list[ZoneMetricOut]:
    hidden = hidden_cameras(session, org_id, "operation")
    rows = session.scalars(
        select(ZoneMetric1m)
        .where(
            ZoneMetric1m.organization_id == org_id,
            ZoneMetric1m.zone_id == zone_id,
            ZoneMetric1m.bucket_start >= start,
            ZoneMetric1m.bucket_start < end,
            ZoneMetric1m.camera_id.not_in(hidden) if hidden else True,
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
