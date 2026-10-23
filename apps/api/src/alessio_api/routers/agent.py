"""Endpoints usados pelo Agente ALESSIO (conexões sempre iniciadas pelo agente)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from alessio_api import audit
from alessio_api.agent_config import build_agent_config
from alessio_api.auth import current_agent
from alessio_api.db import get_session
from alessio_api.ingestion import ingest_batch
from alessio_api.models import Agent, Organization
from alessio_api.security import generate_agent_token, hash_token, normalize_enrollment_code
from alessio_api.tenancy import set_agent_lookup, set_tenant
from alessio_contracts import (
    AgentConfig,
    BatchResult,
    EnrollmentRequest,
    EnrollmentResult,
    MessageBatch,
)

router = APIRouter(prefix="/agent/v1", tags=["agente"])

AgentDep = Annotated[Agent, Depends(current_agent)]
SessionDep = Annotated[Session, Depends(get_session)]

INVALID_CODE = "Código de ativação inválido ou expirado. Gere um novo código no painel, em Agentes."


@router.post("/enroll", response_model=EnrollmentResult)
def enroll(body: EnrollmentRequest, db: SessionDep) -> EnrollmentResult:
    code_hash = hash_token(normalize_enrollment_code(body.code))
    set_agent_lookup(db, code_hash)
    found = db.scalar(select(Agent).where(Agent.enrollment_code_hash == code_hash))
    if found is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_CODE)
    set_tenant(db, found.organization_id)
    agent = db.scalar(
        select(Agent)
        .where(Agent.id == found.id, Agent.enrollment_code_hash == code_hash)
        .with_for_update()
    )
    now = datetime.now(UTC)
    if agent is None or agent.enrollment_expires_at is None or agent.enrollment_expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_CODE)

    token = generate_agent_token()
    # Trocar o hash invalida o token anterior: ativar de novo é a forma de rotacionar a credencial.
    agent.token_hash = hash_token(token)
    agent.enrollment_code_hash = None
    agent.enrollment_expires_at = None
    agent.status = "active"
    agent.enrolled_at = now
    agent.revoked_at = None
    agent.hostname = body.hostname
    agent.version = body.agent_version
    audit.record(
        db, agent.organization_id, None, "agent.enrolled", "agent", agent.id, hostname=body.hostname
    )
    organization = db.get(Organization, agent.organization_id)
    db.commit()
    return EnrollmentResult(
        agent_id=agent.id,
        organization_name=organization.name if organization else "",
        agent_name=agent.name,
        token=token,
    )


@router.post("/messages", response_model=BatchResult)
def post_messages(batch: MessageBatch, agent: AgentDep, db: SessionDep) -> BatchResult:
    return ingest_batch(db, agent, batch.messages)


@router.get("/config", response_model=AgentConfig, responses={304: {"description": "Sem mudanças"}})
def get_config(
    agent: AgentDep,
    db: SessionDep,
    response: Response,
    if_none_match: Annotated[str | None, Header()] = None,
):
    config = build_agent_config(db, agent)
    etag = f'"{config.config_version}"'
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return config
