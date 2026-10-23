"""Modelo de dados da Fase 0.

Toda tabela de negócio carrega ``organization_id`` diretamente, para filtros
simples e para as políticas de Row-Level Security previstas na Fase 1.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), dict[str, Any]: JSONB}


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _org_fk(index: bool = True) -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=index)


def _created_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = _created_at()


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created_at()


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    # SHA-256 do token: o token em si só é exibido uma vez, no cadastro.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    version: Mapped[str | None] = mapped_column(String(32))
    last_seen_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (CheckConstraint("status IN ('active', 'revoked')", name="agent_status"),)


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    # Apelido resolvido pelo agente em arquivo local: a nuvem não guarda credenciais RTSP.
    source_ref: Mapped[str] = mapped_column(String(128))
    analysis_fps: Mapped[float] = mapped_column(Float, default=5.0)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.35)
    status: Mapped[str] = mapped_column(String(20), default="unknown")
    status_detail: Mapped[str | None] = mapped_column(String(500))
    last_frame_at: Mapped[datetime | None]
    last_status_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (UniqueConstraint("agent_id", "source_ref"),)


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    camera_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    # Lista de pontos [x, y] normalizados (0-1).
    polygon: Mapped[list[list[float]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class EventRule(Base):
    __tablename__ = "event_rules"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    camera_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), index=True
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"))
    rule_type: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(default=True)
    shadow: Mapped[bool] = mapped_column(default=False)
    # Parâmetros específicos do tipo de regra, validados pelo contrato correspondente.
    config: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = _created_at()


class Occurrence(Base):
    """Ocorrência de segurança. O ``id`` é gerado pelo agente.

    ``state`` é o ciclo de vida observado pelo agente (aberta/encerrada);
    ``review_status`` é o atendimento do operador. São dimensões independentes.
    """

    __tablename__ = "occurrences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = _org_fk(index=False)  # coberto pelos índices compostos
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"))
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"))
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event_rules.id", ondelete="CASCADE"))
    rule_version: Mapped[int]
    zone_version: Mapped[int]
    event_type: Mapped[str] = mapped_column(String(64))
    is_shadow: Mapped[bool] = mapped_column(default=False)
    state: Mapped[str] = mapped_column(String(20), default="open")
    review_status: Mapped[str] = mapped_column(String(20), default="new")
    started_at: Mapped[datetime]
    confirmed_at: Mapped[datetime]
    last_observed_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]
    close_reason: Mapped[str | None] = mapped_column(String(20))
    max_people: Mapped[int]
    max_confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("state IN ('open', 'closed')", name="occurrence_state"),
        CheckConstraint(
            "review_status IN ('new', 'acknowledged', 'resolved')", name="occurrence_review_status"
        ),
        Index("ix_occurrences_org_started", "organization_id", text("started_at DESC")),
        Index(
            "ix_occurrences_org_camera_started",
            "organization_id",
            "camera_id",
            text("started_at DESC"),
        ),
        Index(
            "ix_occurrences_open",
            "organization_id",
            postgresql_where=text("state = 'open'"),
        ),
    )


class OccurrenceUpdate(Base):
    """Histórico imutável das mensagens que compõem cada ocorrência."""

    __tablename__ = "occurrence_updates"

    message_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = _org_fk()
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("occurrences.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime]
    payload: Mapped[dict[str, Any]]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ZoneMetric1m(Base):
    __tablename__ = "zone_metrics_1m"

    zone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("zones.id", ondelete="CASCADE"), primary_key=True
    )
    bucket_start: Mapped[datetime] = mapped_column(primary_key=True)
    # Índice próprio dispensado: coberto por ix_zone_metrics_org_bucket.
    organization_id: Mapped[uuid.UUID] = _org_fk(index=False)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"))
    analyzed_seconds: Mapped[float] = mapped_column(Float)
    occupancy_avg: Mapped[float] = mapped_column(Float)
    occupancy_max: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_zone_metrics_org_bucket", "organization_id", "bucket_start"),)


class IngestedMessage(Base):
    """Registro de idempotência: cada ``message_id`` é processado uma única vez."""

    __tablename__ = "ingested_messages"

    message_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    agent_session_id: Mapped[uuid.UUID]
    type: Mapped[str] = mapped_column(String(32))
    received_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
