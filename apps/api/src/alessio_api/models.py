"""Modelo de dados.

Toda tabela de dados de cliente carrega ``organization_id`` diretamente e é
protegida por Row-Level Security no PostgreSQL (ver ``tenancy.py`` e a migração
0002). As tabelas de identidade (organizações, usuários, vínculos e sessões)
não têm RLS: o acesso a elas é controlado pela aplicação.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
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
    """Agente ALESSIO. Nasce ``pending`` com um código de ativação de uso único;
    ao ativar, recebe um token próprio (guardado só como SHA-256) e fica ``active``."""

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk()
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    enrollment_code_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    enrollment_expires_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(20), default="pending")
    version: Mapped[str | None] = mapped_column(String(32))
    hostname: Mapped[str | None] = mapped_column(String(255))
    enrolled_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    last_seen_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'active', 'revoked')", name="agent_status"),
    )


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
    reviewed_at: Mapped[datetime | None]
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
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


class User(Base):
    """Conta de acesso ao painel. ``password_hash`` fica vazio até o convite ser aceito."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    invite_expires_at: Mapped[datetime | None]
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None]
    last_login_at: Mapped[datetime | None]
    # Equipe Alessio: acessa a área Plataforma (contratos de comodato e equipamentos
    # de todos os clientes). Concedido só por linha de comando.
    is_platform_staff: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        CheckConstraint("status IN ('active', 'invited', 'disabled')", name="user_status"),
        CheckConstraint("email = lower(email)", name="user_email_lowercase"),
    )


class Membership(Base):
    __tablename__ = "memberships"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        CheckConstraint("role IN ('owner', 'admin', 'operator', 'viewer')", name="membership_role"),
    )


class UserSession(Base):
    """Sessão do painel. O cookie leva o token; o banco guarda só o SHA-256."""

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    active_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(index=True)
    last_seen_at: Mapped[datetime | None]


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk(index=False)  # coberto por ix_audit_org_created
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_audit_org_created", "organization_id", text("created_at DESC")),)


class ComodatoContract(Base):
    """Contrato de comodato: equipamentos da Alessio emprestados ao cliente."""

    __tablename__ = "comodato_contracts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk(index=False)  # coberto pelo único (org, número)
    number: Mapped[str] = mapped_column(String(64))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")
    notes: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        CheckConstraint("status IN ('active', 'ended')", name="contract_status"),
        UniqueConstraint("organization_id", "number"),
    )


class Equipment(Base):
    """Equipamento instalado no cliente: dele próprio ou da Alessio em comodato.

    Valores em centavos. ``monthly_fee_cents`` (quanto o comodato soma à
    mensalidade) só existe em comodato; a cobrança em si ainda não está no sistema.
    """

    __tablename__ = "equipment"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _org_fk(index=False)  # coberto por ix_equipment_org_kind
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20))
    brand: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(100))
    ownership: Mapped[str] = mapped_column(String(20))
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comodato_contracts.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="in_use")
    camera_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cameras.id", ondelete="SET NULL")
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    reference_value_cents: Mapped[int | None]
    monthly_fee_cents: Mapped[int | None]
    delivered_on: Mapped[date | None] = mapped_column(Date)
    returned_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "kind IN ('camera', 'agent_host', 'recorder', 'switch', 'ups', 'other')",
            name="equipment_kind",
        ),
        CheckConstraint("ownership IN ('client', 'comodato')", name="equipment_ownership"),
        CheckConstraint(
            "status IN ('in_use', 'maintenance', 'returned', 'retired')", name="equipment_status"
        ),
        # Comodato sempre tem contrato; equipamento do cliente nunca tem contrato nem mensalidade.
        CheckConstraint(
            "(ownership = 'comodato' AND contract_id IS NOT NULL) OR "
            "(ownership = 'client' AND contract_id IS NULL AND monthly_fee_cents IS NULL)",
            name="equipment_ownership_contract",
        ),
        CheckConstraint(
            "(reference_value_cents IS NULL OR reference_value_cents >= 0) AND "
            "(monthly_fee_cents IS NULL OR monthly_fee_cents >= 0)",
            name="equipment_values_positive",
        ),
        Index("ix_equipment_org_kind", "organization_id", "kind"),
    )
