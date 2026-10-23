"""Administração da organização ativa: locais, agentes, membros e auditoria."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alessio_api import audit
from alessio_api.auth import Principal, require
from alessio_api.db import get_session
from alessio_api.models import Agent, AuditLog, Membership, Site, User
from alessio_api.permissions import Permission
from alessio_api.security import generate_enrollment_code, generate_invite_token, hash_token
from alessio_api.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["administração"])

SessionDep = Annotated[Session, Depends(get_session)]
Role = Literal["owner", "admin", "operator", "viewer"]


# --- Locais ---------------------------------------------------------------------------------


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = "America/Sao_Paulo"

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("fuso horário desconhecido") from exc
        return value


class SiteOut(BaseModel):
    id: UUID
    name: str
    timezone: str


@router.get("/sites", response_model=list[SiteOut])
def list_sites(
    principal: Annotated[Principal, Depends(require(Permission.CAMERAS_READ))], db: SessionDep
) -> list[SiteOut]:
    sites = db.scalars(
        select(Site).where(Site.organization_id == principal.organization_id).order_by(Site.name)
    )
    return [SiteOut(id=s.id, name=s.name, timezone=s.timezone) for s in sites]


@router.post("/sites", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
def create_site(
    body: SiteIn,
    principal: Annotated[Principal, Depends(require(Permission.SITES_MANAGE))],
    db: SessionDep,
) -> SiteOut:
    site = Site(
        organization_id=principal.organization_id, name=body.name.strip(), timezone=body.timezone
    )
    db.add(site)
    db.flush()
    audit.record(
        db, site.organization_id, principal.user.id, "site.created", "site", site.id, name=site.name
    )
    db.commit()
    return SiteOut(id=site.id, name=site.name, timezone=site.timezone)


# --- Agentes --------------------------------------------------------------------------------


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    site_id: UUID


class AgentOut(BaseModel):
    id: UUID
    name: str
    site_id: UUID
    site_name: str
    status: Literal["pending", "active", "revoked"]
    version: str | None
    hostname: str | None
    enrolled_at: datetime | None
    last_seen_at: datetime | None
    enrollment_pending: bool


class EnrollmentCodeOut(BaseModel):
    agent: AgentOut
    enrollment_code: str
    enrollment_expires_at: datetime


ManageAgents = Annotated[Principal, Depends(require(Permission.AGENTS_MANAGE))]


def _agent_out(agent: Agent, site_name: str) -> AgentOut:
    now = datetime.now(UTC)
    return AgentOut(
        id=agent.id,
        name=agent.name,
        site_id=agent.site_id,
        site_name=site_name,
        status=agent.status,
        version=agent.version,
        hostname=agent.hostname,
        enrolled_at=agent.enrolled_at,
        last_seen_at=agent.last_seen_at,
        enrollment_pending=bool(
            agent.enrollment_code_hash
            and agent.enrollment_expires_at
            and agent.enrollment_expires_at > now
        ),
    )


def _load_agent(db: Session, principal: Principal, agent_id: UUID) -> tuple[Agent, str]:
    row = db.execute(
        select(Agent, Site.name)
        .join(Site, Site.id == Agent.site_id)
        .where(Agent.id == agent_id, Agent.organization_id == principal.organization_id)
        .with_for_update(of=Agent)
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agente não encontrado")
    return row.Agent, row.name


def _new_code(agent: Agent) -> tuple[str, datetime]:
    code = generate_enrollment_code()
    expires = datetime.now(UTC) + timedelta(hours=get_settings().enrollment_hours)
    agent.enrollment_code_hash = hash_token(code)
    agent.enrollment_expires_at = expires
    return code, expires


@router.get("/agents", response_model=list[AgentOut])
def list_agents(principal: ManageAgents, db: SessionDep) -> list[AgentOut]:
    rows = db.execute(
        select(Agent, Site.name)
        .join(Site, Site.id == Agent.site_id)
        .where(Agent.organization_id == principal.organization_id)
        .order_by(Agent.created_at)
    )
    return [_agent_out(agent, site_name) for agent, site_name in rows]


@router.post("/agents", response_model=EnrollmentCodeOut, status_code=status.HTTP_201_CREATED)
def create_agent(body: AgentIn, principal: ManageAgents, db: SessionDep) -> EnrollmentCodeOut:
    site = db.scalar(
        select(Site).where(
            Site.id == body.site_id, Site.organization_id == principal.organization_id
        )
    )
    if site is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "local não encontrado")
    agent = Agent(
        organization_id=principal.organization_id,
        site_id=site.id,
        name=body.name.strip(),
        status="pending",
    )
    db.add(agent)
    code, expires = _new_code(agent)
    db.flush()
    audit.record(
        db,
        agent.organization_id,
        principal.user.id,
        "agent.created",
        "agent",
        agent.id,
        name=agent.name,
    )
    db.commit()
    return EnrollmentCodeOut(
        agent=_agent_out(agent, site.name), enrollment_code=code, enrollment_expires_at=expires
    )


@router.post("/agents/{agent_id}/enrollment-code", response_model=EnrollmentCodeOut)
def new_enrollment_code(
    agent_id: UUID, principal: ManageAgents, db: SessionDep
) -> EnrollmentCodeOut:
    """Novo código de ativação. Num agente ativo, ativar de novo troca o token (rotação)."""
    agent, site_name = _load_agent(db, principal, agent_id)
    code, expires = _new_code(agent)
    audit.record(
        db, agent.organization_id, principal.user.id, "agent.enrollment_code", "agent", agent.id
    )
    db.commit()
    return EnrollmentCodeOut(
        agent=_agent_out(agent, site_name), enrollment_code=code, enrollment_expires_at=expires
    )


@router.post("/agents/{agent_id}/revoke", response_model=AgentOut)
def revoke_agent(agent_id: UUID, principal: ManageAgents, db: SessionDep) -> AgentOut:
    agent, site_name = _load_agent(db, principal, agent_id)
    agent.status = "revoked"
    agent.revoked_at = datetime.now(UTC)
    agent.token_hash = None
    agent.enrollment_code_hash = None
    agent.enrollment_expires_at = None
    audit.record(db, agent.organization_id, principal.user.id, "agent.revoked", "agent", agent.id)
    db.commit()
    return _agent_out(agent, site_name)


# --- Membros --------------------------------------------------------------------------------


class MemberIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    role: Role


class MemberRoleIn(BaseModel):
    role: Role


class MemberOut(BaseModel):
    user_id: UUID
    email: str
    name: str
    role: Role
    status: Literal["active", "invited", "disabled"]
    joined_at: datetime


class MemberCreatedOut(BaseModel):
    member: MemberOut
    # Só presente quando a pessoa ainda não tem conta. Exibido uma única vez.
    invite_token: str | None
    invite_expires_at: datetime | None


ManageMembers = Annotated[Principal, Depends(require(Permission.MEMBERS_MANAGE))]


def _member_out(membership: Membership, user: User) -> MemberOut:
    return MemberOut(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=membership.role,
        status=user.status,
        joined_at=membership.created_at,
    )


def _check_owner_rules(
    principal: Principal, current_role: str | None, new_role: str | None
) -> None:
    touches_owner = "owner" in (current_role, new_role)
    if touches_owner and not principal.can(Permission.OWNERS_MANAGE):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Só proprietários podem gerenciar proprietários."
        )


def _ensure_another_owner(db: Session, organization_id: UUID, user_id: UUID) -> None:
    owners = db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.organization_id == organization_id,
            Membership.role == "owner",
            Membership.user_id != user_id,
        )
    )
    if not owners:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A organização precisa de pelo menos um proprietário."
        )


def _issue_invite(user: User) -> tuple[str, datetime]:
    token = generate_invite_token()
    expires = datetime.now(UTC) + timedelta(hours=get_settings().invite_hours)
    user.invite_token_hash = hash_token(token)
    user.invite_expires_at = expires
    return token, expires


def _load_member(db: Session, principal: Principal, user_id: UUID) -> tuple[Membership, User]:
    row = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == principal.organization_id, Membership.user_id == user_id
        )
        .with_for_update(of=Membership)
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "membro não encontrado")
    return row.Membership, row.User


@router.get("/members", response_model=list[MemberOut])
def list_members(principal: ManageMembers, db: SessionDep) -> list[MemberOut]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == principal.organization_id)
        .order_by(User.name)
    )
    return [_member_out(m, u) for m, u in rows]


@router.post("/members", response_model=MemberCreatedOut, status_code=status.HTTP_201_CREATED)
def add_member(body: MemberIn, principal: ManageMembers, db: SessionDep) -> MemberCreatedOut:
    _check_owner_rules(principal, None, body.role)
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    invite_token = invite_expires = None
    if user is None:
        user = User(email=email, name=body.name.strip(), status="invited")
        db.add(user)
        invite_token, invite_expires = _issue_invite(user)
        db.flush()
    elif db.get(Membership, (principal.organization_id, user.id)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Essa pessoa já é membro da organização.")
    elif user.status == "invited":
        invite_token, invite_expires = _issue_invite(user)
    membership = Membership(
        organization_id=principal.organization_id, user_id=user.id, role=body.role
    )
    db.add(membership)
    db.flush()
    audit.record(
        db,
        principal.organization_id,
        principal.user.id,
        "member.added",
        "user",
        user.id,
        role=body.role,
    )
    db.commit()
    return MemberCreatedOut(
        member=_member_out(membership, user),
        invite_token=invite_token,
        invite_expires_at=invite_expires,
    )


@router.patch("/members/{user_id}", response_model=MemberOut)
def change_member_role(
    user_id: UUID, body: MemberRoleIn, principal: ManageMembers, db: SessionDep
) -> MemberOut:
    membership, user = _load_member(db, principal, user_id)
    _check_owner_rules(principal, membership.role, body.role)
    if membership.role == "owner" and body.role != "owner":
        _ensure_another_owner(db, principal.organization_id, user_id)
    previous = membership.role
    membership.role = body.role
    audit.record(
        db,
        principal.organization_id,
        principal.user.id,
        "member.role_changed",
        "user",
        user.id,
        previous=previous,
        role=body.role,
    )
    db.commit()
    return _member_out(membership, user)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(user_id: UUID, principal: ManageMembers, db: SessionDep) -> None:
    membership, user = _load_member(db, principal, user_id)
    _check_owner_rules(principal, membership.role, None)
    if membership.role == "owner":
        _ensure_another_owner(db, principal.organization_id, user_id)
    db.delete(membership)
    audit.record(
        db, principal.organization_id, principal.user.id, "member.removed", "user", user.id
    )
    db.commit()


@router.post("/members/{user_id}/invite", response_model=MemberCreatedOut)
def reissue_invite(user_id: UUID, principal: ManageMembers, db: SessionDep) -> MemberCreatedOut:
    membership, user = _load_member(db, principal, user_id)
    if user.status != "invited":
        raise HTTPException(status.HTTP_409_CONFLICT, "Essa pessoa já ativou a conta.")
    _check_owner_rules(principal, membership.role, None)
    token, expires = _issue_invite(user)
    audit.record(
        db, principal.organization_id, principal.user.id, "member.invite_reissued", "user", user.id
    )
    db.commit()
    return MemberCreatedOut(
        member=_member_out(membership, user), invite_token=token, invite_expires_at=expires
    )


# --- Auditoria ------------------------------------------------------------------------------


class AuditOut(BaseModel):
    id: UUID
    created_at: datetime
    action: str
    user_email: str | None
    target_type: str | None
    target_id: str | None
    details: dict


@router.get("/audit-logs", response_model=list[AuditOut])
def list_audit_logs(
    principal: Annotated[Principal, Depends(require(Permission.AUDIT_READ))],
    db: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[AuditOut]:
    rows = db.execute(
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(AuditLog.organization_id == principal.organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return [
        AuditOut(
            id=log.id,
            created_at=log.created_at,
            action=log.action,
            user_email=email,
            target_type=log.target_type,
            target_id=log.target_id,
            details=log.details,
        )
        for log, email in rows
    ]
