"""Dependências de autenticação do painel (cookie de sessão) e do agente (token).

Proteção contra CSRF: o cookie é ``SameSite=Lax`` e toda requisição que altera
dados precisa do cabeçalho ``X-Alessio-Client``. Um site de terceiros só
conseguiria enviá-lo após um preflight CORS, que recusamos para origens fora de
``ALESSIO_CORS_ORIGINS``.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from alessio_api.db import get_session
from alessio_api.models import Agent, Membership, User, UserSession
from alessio_api.permissions import ROLE_PERMISSIONS, Permission
from alessio_api.security import generate_session_token, hash_token
from alessio_api.settings import get_settings
from alessio_api.tenancy import set_agent_lookup, set_tenant

SESSION_COOKIE = "alessio_session"
CLIENT_HEADER = "X-Alessio-Client"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

SessionDep = Annotated[Session, Depends(get_session)]


@dataclass
class Principal:
    user: User
    session: UserSession
    organization_id: UUID | None
    role: str | None

    @property
    def permissions(self) -> frozenset[Permission]:
        return ROLE_PERMISSIONS.get(self.role or "", frozenset())

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions


def start_session(db: Session, response: Response, user: User) -> UserSession:
    settings = get_settings()
    token = generate_session_token()
    first_membership = db.scalar(
        select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at)
    )
    user_session = UserSession(
        token_hash=hash_token(token),
        user_id=user.id,
        active_organization_id=first_membership.organization_id if first_membership else None,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_hours),
    )
    db.add(user_session)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user_session


def end_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def csrf_protect(request: Request) -> None:
    if request.method in UNSAFE_METHODS and not request.headers.get(CLIENT_HEADER):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "cabeçalho X-Alessio-Client ausente")


def current_principal(request: Request, db: SessionDep) -> Principal:
    csrf_protect(request)
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sessão ausente")
    now = datetime.now(UTC)
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == hash_token(token), UserSession.expires_at > now)
    ).first()
    if row is None or row.User.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sessão expirada ou encerrada")
    user_session, user = row.UserSession, row.User

    role = None
    organization_id = user_session.active_organization_id
    if organization_id is not None:
        role = db.scalar(
            select(Membership.role).where(
                Membership.organization_id == organization_id, Membership.user_id == user.id
            )
        )
        if role is None:  # o vínculo foi removido depois do login
            organization_id = user_session.active_organization_id = None
    if user_session.last_seen_at is None or now - user_session.last_seen_at > timedelta(minutes=5):
        user_session.last_seen_at = now
    if organization_id is not None:
        set_tenant(db, organization_id)
    db.commit()
    return Principal(user=user, session=user_session, organization_id=organization_id, role=role)


PrincipalDep = Annotated[Principal, Depends(current_principal)]


def require(permission: Permission):
    """Exige organização ativa e a permissão. Retorna o ``Principal``."""

    def dependency(principal: PrincipalDep) -> Principal:
        if principal.organization_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "nenhuma organização selecionada")
        if not principal.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "seu papel não permite esta ação")
        return principal

    return dependency


_bearer = HTTPBearer(auto_error=False)


def current_agent(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: SessionDep,
) -> Agent:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "credencial ausente")
    token_hash = hash_token(credentials.credentials)
    set_agent_lookup(db, token_hash)
    agent = db.scalar(select(Agent).where(Agent.token_hash == token_hash, Agent.status == "active"))
    if agent is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "credencial inválida ou revogada")
    set_tenant(db, agent.organization_id)
    agent.last_seen_at = datetime.now(UTC)
    db.commit()
    return agent
