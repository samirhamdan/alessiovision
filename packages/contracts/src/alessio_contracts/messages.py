"""Mensagens que o agente envia à nuvem (POST /agent/v1/messages).

Toda mensagem tem um ``message_id`` gerado no agente: a nuvem usa esse ID para
descartar reenvios, então o agente pode repetir um lote sem criar duplicatas.

A organização nunca vem no payload: a nuvem a obtém da credencial do agente.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0"
MAX_BATCH_SIZE = 500


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Payloads -------------------------------------------------------------------------------


class OccurrenceOpened(_Strict):
    occurrence_id: UUID
    camera_id: UUID
    zone_id: UUID
    rule_id: UUID
    rule_version: int = Field(ge=1)
    zone_version: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=64)
    shadow: bool = False
    started_at: AwareDatetime
    confirmed_at: AwareDatetime
    people_count: int = Field(ge=0)
    max_confidence: float = Field(ge=0.0, le=1.0)


class OccurrenceUpdated(_Strict):
    occurrence_id: UUID
    observed_at: AwareDatetime
    people_count: int = Field(ge=0)
    max_people: int = Field(ge=0)


class OccurrenceClosed(_Strict):
    occurrence_id: UUID
    ended_at: AwareDatetime
    max_people: int = Field(ge=0)
    reason: Literal["cleared", "schedule", "signal_lost", "shutdown"]


class ZoneMetrics1m(_Strict):
    """Ocupação de uma zona em um minuto (``bucket_start`` alinhado ao minuto, UTC).

    ``analyzed_seconds`` diz quanto do minuto foi efetivamente analisado: uma
    câmera fora do ar aparece como lacuna, não como "zero pessoas".
    """

    camera_id: UUID
    zone_id: UUID
    bucket_start: AwareDatetime
    analyzed_seconds: float = Field(ge=0.0, le=60.0)
    occupancy_avg: float = Field(ge=0.0)
    occupancy_max: int = Field(ge=0)

    @field_validator("bucket_start")
    @classmethod
    def _aligned_to_minute(cls, value):
        if value.second or value.microsecond:
            raise ValueError("bucket_start precisa estar alinhado ao minuto")
        return value


class CameraStatus(_Strict):
    camera_id: UUID
    status: Literal["connected", "disconnected", "error"]
    last_frame_at: AwareDatetime | None = None
    analysis_fps: float | None = Field(default=None, ge=0.0)
    detail: str | None = Field(default=None, max_length=500)


class Heartbeat(_Strict):
    agent_version: str = Field(max_length=32)
    cameras: list[CameraStatus] = Field(default_factory=list)


# --- Envelopes ------------------------------------------------------------------------------


class _Envelope(_Strict):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    message_id: UUID
    agent_session_id: UUID
    sent_at: AwareDatetime


class OccurrenceOpenedMessage(_Envelope):
    type: Literal["occurrence.opened"] = "occurrence.opened"
    payload: OccurrenceOpened


class OccurrenceUpdatedMessage(_Envelope):
    type: Literal["occurrence.updated"] = "occurrence.updated"
    payload: OccurrenceUpdated


class OccurrenceClosedMessage(_Envelope):
    type: Literal["occurrence.closed"] = "occurrence.closed"
    payload: OccurrenceClosed


class ZoneMetricsMessage(_Envelope):
    type: Literal["metrics.zone_1m"] = "metrics.zone_1m"
    payload: ZoneMetrics1m


class HeartbeatMessage(_Envelope):
    type: Literal["heartbeat"] = "heartbeat"
    payload: Heartbeat


AgentMessage = Annotated[
    OccurrenceOpenedMessage
    | OccurrenceUpdatedMessage
    | OccurrenceClosedMessage
    | ZoneMetricsMessage
    | HeartbeatMessage,
    Field(discriminator="type"),
]


class MessageBatch(_Strict):
    messages: list[AgentMessage] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


class MessageResult(_Strict):
    message_id: UUID
    status: Literal["accepted", "duplicate", "rejected"]
    reason: str | None = None


class BatchResult(_Strict):
    results: list[MessageResult]
