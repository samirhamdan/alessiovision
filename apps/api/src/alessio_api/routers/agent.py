"""Endpoints usados pelo Agente ALESSIO (conexões sempre iniciadas pelo agente)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from alessio_api.agent_config import build_agent_config
from alessio_api.db import get_session
from alessio_api.ingestion import ingest_batch
from alessio_api.models import Agent
from alessio_api.security import current_agent
from alessio_contracts import AgentConfig, BatchResult, MessageBatch

router = APIRouter(prefix="/agent/v1", tags=["agente"])

AgentDep = Annotated[Agent, Depends(current_agent)]
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/messages", response_model=BatchResult)
def post_messages(batch: MessageBatch, agent: AgentDep, session: SessionDep) -> BatchResult:
    return ingest_batch(session, agent, batch.messages)


@router.get("/config", response_model=AgentConfig, responses={304: {"description": "Sem mudanças"}})
def get_config(
    agent: AgentDep,
    session: SessionDep,
    response: Response,
    if_none_match: Annotated[str | None, Header()] = None,
):
    config = build_agent_config(session, agent)
    etag = f'"{config.config_version}"'
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return config
