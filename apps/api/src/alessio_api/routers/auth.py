"""Login, sessão, troca de organização e aceite de convite."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from alessio_api.auth import (
    SESSION_COOKIE,
    PrincipalDep,
    csrf_protect,
    end_session,
    start_session,
)
from alessio_api.db import get_session
from alessio_api.models import Membership, Organization, User, UserSession
from alessio_api.permissions import ROLE_PERMISSIONS
from alessio_api.security import hash_password, hash_token, password_problem, verify_password
from alessio_api.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["autenticação"])

SessionDep = Annotated[Session, Depends(get_session)]
INVALID_LOGIN = "E-mail ou senha incorretos."


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(max_length=256)


class OrganizationSwitchIn(BaseModel):
    organization_id: UUID


class MembershipOut(BaseModel):
    organization_id: UUID
    organization_name: str
    role: str


class MeOut(BaseModel):
    id: UUID
    email: str
    name: str
    active_organization_id: UUID | None
    role: str | None
    permissions: list[str]
    is_platform_staff: bool
    memberships: list[MembershipOut]


def _me(db: Session, user: User, organization_id: UUID | None, role: str | None) -> MeOut:
    rows = db.execute(
        select(Membership, Organization.name)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user.id, Organization.status == "active")
        .order_by(Organization.name)
    ).all()
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        active_organization_id=organization_id,
        role=role,
        permissions=sorted(ROLE_PERMISSIONS.get(role or "", frozenset())),
        is_platform_staff=user.is_platform_staff,
        memberships=[
            MembershipOut(organization_id=m.organization_id, organization_name=name, role=m.role)
            for m, name in rows
        ],
    )


@router.post("/auth/login", response_model=MeOut, dependencies=[Depends(csrf_protect)])
def login(body: LoginIn, response: Response, db: SessionDep) -> MeOut:
    settings = get_settings()
    now = datetime.now(UTC)
    user = db.scalar(select(User).where(User.email == body.email.lower()).with_for_update())
    if user is not None and user.locked_until and user.locked_until > now:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Muitas tentativas. Aguarde alguns minutos e tente de novo.",
        )
    password_ok = verify_password(user.password_hash if user else None, body.password)
    if user is None or not password_ok or user.status != "active":
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_login_count = 0
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    user_session = start_session(db, response, user)
    db.commit()
    role = None
    if user_session.active_organization_id:
        role = db.scalar(
            select(Membership.role).where(
                Membership.organization_id == user_session.active_organization_id,
                Membership.user_id == user.id,
            )
        )
    return _me(db, user, user_session.active_organization_id, role)


@router.post(
    "/auth/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(csrf_protect)]
)
def logout(request: Request, db: SessionDep) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
        db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    end_session(response)
    return response


@router.get("/me", response_model=MeOut)
def me(principal: PrincipalDep, db: SessionDep) -> MeOut:
    return _me(db, principal.user, principal.organization_id, principal.role)


@router.post("/session/organization", response_model=MeOut)
def switch_organization(
    body: OrganizationSwitchIn, principal: PrincipalDep, db: SessionDep
) -> MeOut:
    role = db.scalar(
        select(Membership.role).where(
            Membership.organization_id == body.organization_id,
            Membership.user_id == principal.user.id,
        )
    )
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organização não encontrada")
    principal.session.active_organization_id = body.organization_id
    db.commit()
    return _me(db, principal.user, body.organization_id, role)


@router.post("/auth/accept-invite", response_model=MeOut, dependencies=[Depends(csrf_protect)])
def accept_invite(body: AcceptInviteIn, response: Response, db: SessionDep) -> MeOut:
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    user = db.scalar(
        select(User)
        .where(User.invite_token_hash == hash_token(body.token), User.status == "invited")
        .with_for_update()
    )
    if user is None or user.invite_expires_at is None or user.invite_expires_at < datetime.now(UTC):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Convite inválido ou expirado. Peça um novo convite a quem administra a organização.",
        )
    user.name = body.name.strip()
    user.password_hash = hash_password(body.password)
    user.status = "active"
    user.invite_token_hash = None
    user.invite_expires_at = None
    user.last_login_at = datetime.now(UTC)
    user_session = start_session(db, response, user)
    db.commit()
    role = db.scalar(
        select(Membership.role).where(
            Membership.organization_id == user_session.active_organization_id,
            Membership.user_id == user.id,
        )
    )
    return _me(db, user, user_session.active_organization_id, role)
