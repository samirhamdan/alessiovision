"""Ativação do agente (POST /agent/v1/enroll).

O painel gera um código de ativação de uso único, válido por algumas horas. O
agente troca esse código por um token próprio, que só é mostrado nesta resposta
e fica guardado no próprio agente.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EnrollmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=8, max_length=64)
    hostname: str | None = Field(default=None, max_length=255)
    agent_version: str = Field(max_length=32)


class EnrollmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: UUID
    organization_name: str
    agent_name: str
    token: str
