"""Processamento das mensagens do agente.

Regras de segurança:
- a organização vem da credencial do agente, nunca do payload;
- câmeras, zonas, regras e ocorrências citadas precisam pertencer a esse agente.

Cada mensagem roda em um savepoint: uma mensagem rejeitada não desfaz as outras
do lote, e uma reenviada (mesmo ``message_id``) é reconhecida como duplicata.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from alessio_api.models import (
    Agent,
    Camera,
    EventRule,
    IngestedMessage,
    Occurrence,
    OccurrenceUpdate,
    Zone,
    ZoneMetric1m,
)
from alessio_contracts import (
    AgentMessage,
    BatchResult,
    HeartbeatMessage,
    MessageResult,
    OccurrenceClosedMessage,
    OccurrenceOpenedMessage,
    OccurrenceUpdatedMessage,
    ZoneMetricsMessage,
)


class Rejected(Exception):
    pass


def ingest_batch(session: Session, agent: Agent, messages: list[AgentMessage]) -> BatchResult:
    results = []
    for message in messages:
        try:
            with session.begin_nested():
                if not _claim(session, agent, message):
                    results.append(MessageResult(message_id=message.message_id, status="duplicate"))
                    continue
                _HANDLERS[type(message)](session, agent, message)
            results.append(MessageResult(message_id=message.message_id, status="accepted"))
        except Rejected as exc:
            results.append(
                MessageResult(message_id=message.message_id, status="rejected", reason=str(exc))
            )
    session.commit()
    return BatchResult(results=results)


def _claim(session: Session, agent: Agent, message: AgentMessage) -> bool:
    inserted = session.execute(
        insert(IngestedMessage)
        .values(
            message_id=message.message_id,
            agent_id=agent.id,
            agent_session_id=message.agent_session_id,
            type=message.type,
        )
        .on_conflict_do_nothing(index_elements=["message_id"])
        .returning(IngestedMessage.message_id)
    ).first()
    return inserted is not None


def _camera(session: Session, agent: Agent, camera_id: UUID) -> Camera:
    camera = session.scalar(
        select(Camera).where(Camera.id == camera_id, Camera.agent_id == agent.id)
    )
    if camera is None:
        raise Rejected(f"câmera {camera_id} não pertence a este agente")
    return camera


def _zone(session: Session, camera: Camera, zone_id: UUID) -> Zone:
    zone = session.scalar(select(Zone).where(Zone.id == zone_id, Zone.camera_id == camera.id))
    if zone is None:
        raise Rejected(f"zona {zone_id} não pertence à câmera {camera.id}")
    return zone


def _occurrence(session: Session, agent: Agent, occurrence_id: UUID) -> Occurrence:
    occurrence = session.scalar(
        select(Occurrence)
        .join(Camera, Camera.id == Occurrence.camera_id)
        .where(Occurrence.id == occurrence_id, Camera.agent_id == agent.id)
        .with_for_update(of=Occurrence)
    )
    if occurrence is None:
        raise Rejected(f"ocorrência {occurrence_id} desconhecida para este agente")
    return occurrence


def _record_update(
    session: Session, occurrence: Occurrence, message: AgentMessage, observed_at: datetime
) -> None:
    session.add(
        OccurrenceUpdate(
            message_id=message.message_id,
            organization_id=occurrence.organization_id,
            occurrence_id=occurrence.id,
            type=message.type,
            observed_at=observed_at,
            payload=message.payload.model_dump(mode="json"),
        )
    )


def _opened(session: Session, agent: Agent, message: OccurrenceOpenedMessage) -> None:
    p = message.payload
    camera = _camera(session, agent, p.camera_id)
    _zone(session, camera, p.zone_id)
    rule = session.scalar(
        select(EventRule).where(
            EventRule.id == p.rule_id,
            EventRule.camera_id == camera.id,
            EventRule.zone_id == p.zone_id,
        )
    )
    if rule is None:
        raise Rejected(f"regra {p.rule_id} não pertence a esta câmera e zona")
    inserted = session.execute(
        insert(Occurrence)
        .values(
            id=p.occurrence_id,
            organization_id=camera.organization_id,
            site_id=camera.site_id,
            camera_id=camera.id,
            zone_id=p.zone_id,
            rule_id=rule.id,
            rule_version=p.rule_version,
            zone_version=p.zone_version,
            event_type=p.event_type,
            is_shadow=p.shadow,
            started_at=p.started_at,
            confirmed_at=p.confirmed_at,
            last_observed_at=p.confirmed_at,
            max_people=p.people_count,
            max_confidence=p.max_confidence,
        )
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(Occurrence.id)
    ).first()
    if inserted is None:
        raise Rejected(f"ocorrência {p.occurrence_id} já existe")
    occurrence = session.get(Occurrence, p.occurrence_id)
    assert occurrence is not None
    _record_update(session, occurrence, message, p.confirmed_at)


def _updated(session: Session, agent: Agent, message: OccurrenceUpdatedMessage) -> None:
    p = message.payload
    occurrence = _occurrence(session, agent, p.occurrence_id)
    occurrence.last_observed_at = max(occurrence.last_observed_at, p.observed_at)
    occurrence.max_people = max(occurrence.max_people, p.max_people)
    _record_update(session, occurrence, message, p.observed_at)


def _closed(session: Session, agent: Agent, message: OccurrenceClosedMessage) -> None:
    p = message.payload
    occurrence = _occurrence(session, agent, p.occurrence_id)
    occurrence.state = "closed"
    occurrence.ended_at = p.ended_at
    occurrence.close_reason = p.reason
    occurrence.max_people = max(occurrence.max_people, p.max_people)
    occurrence.last_observed_at = max(occurrence.last_observed_at, p.ended_at)
    _record_update(session, occurrence, message, p.ended_at)


def _zone_metrics(session: Session, agent: Agent, message: ZoneMetricsMessage) -> None:
    p = message.payload
    camera = _camera(session, agent, p.camera_id)
    _zone(session, camera, p.zone_id)
    stmt = insert(ZoneMetric1m).values(
        zone_id=p.zone_id,
        bucket_start=p.bucket_start,
        organization_id=camera.organization_id,
        camera_id=camera.id,
        analyzed_seconds=p.analyzed_seconds,
        occupancy_avg=p.occupancy_avg,
        occupancy_max=p.occupancy_max,
    )
    current, new = ZoneMetric1m.__table__.c, stmt.excluded
    total = current.analyzed_seconds + new.analyzed_seconds
    # Um mesmo minuto pode chegar em partes (ex.: agente reiniciado no meio do minuto):
    # as partes são combinadas com média ponderada pelo tempo analisado.
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["zone_id", "bucket_start"],
            set_={
                "analyzed_seconds": func.least(60.0, total),
                "occupancy_avg": (
                    current.occupancy_avg * current.analyzed_seconds
                    + new.occupancy_avg * new.analyzed_seconds
                )
                / func.nullif(total, 0),
                "occupancy_max": func.greatest(current.occupancy_max, new.occupancy_max),
                "updated_at": func.now(),
            },
        )
    )


def _heartbeat(session: Session, agent: Agent, message: HeartbeatMessage) -> None:
    p = message.payload
    agent.version = p.agent_version
    now = datetime.now(UTC)
    for status in p.cameras:
        camera = session.scalar(
            select(Camera).where(Camera.id == status.camera_id, Camera.agent_id == agent.id)
        )
        if camera is None:
            continue
        camera.status = status.status
        camera.status_detail = status.detail
        camera.last_status_at = now
        if status.last_frame_at is not None:
            camera.last_frame_at = status.last_frame_at


_HANDLERS = {
    OccurrenceOpenedMessage: _opened,
    OccurrenceUpdatedMessage: _updated,
    OccurrenceClosedMessage: _closed,
    ZoneMetricsMessage: _zone_metrics,
    HeartbeatMessage: _heartbeat,
}
