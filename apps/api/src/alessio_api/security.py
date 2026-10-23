import hashlib
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from alessio_api.db import get_session
from alessio_api.models import Agent

_bearer = HTTPBearer(auto_error=False)


def generate_agent_token() -> str:
    return "alg_" + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_agent(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> Agent:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "credencial ausente")
    agent = session.scalar(
        select(Agent).where(
            Agent.token_hash == hash_token(credentials.credentials), Agent.status == "active"
        )
    )
    if agent is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "credencial inválida ou revogada")
    agent.last_seen_at = datetime.now(UTC)
    session.commit()
    return agent
