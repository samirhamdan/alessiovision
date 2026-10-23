"""Configuração que a nuvem entrega ao agente (GET /agent/v1/config).

As credenciais das câmeras nunca fazem parte deste contrato: a nuvem conhece
apenas um ``source_ref`` (apelido), e o agente resolve o endereço real a partir
de um arquivo local que não sai da rede do cliente.
"""

from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

NormalizedCoord = Annotated[float, Field(ge=0.0, le=1.0)]
Point = tuple[NormalizedCoord, NormalizedCoord]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScheduleWindow(_Strict):
    """Janela de expediente. ``days`` usa 0 = segunda ... 6 = domingo.

    Se ``end`` for menor que ``start`` a janela atravessa a meia-noite e
    termina no dia seguinte (ex.: turno noturno 22:00-06:00).
    """

    days: list[Annotated[int, Field(ge=0, le=6)]] = Field(min_length=1)
    start: time
    end: time

    @model_validator(mode="after")
    def _non_empty(self) -> "ScheduleWindow":
        if self.start == self.end:
            raise ValueError("start e end não podem ser iguais")
        return self

    def contains(self, local: datetime) -> bool:
        t = local.time()
        if self.start < self.end:
            return local.weekday() in self.days and self.start <= t < self.end
        previous_day = (local - timedelta(days=1)).weekday()
        return (local.weekday() in self.days and t >= self.start) or (
            previous_day in self.days and t < self.end
        )


class Schedule(_Strict):
    """Expediente de um local. Fora destas janelas (ou em feriados) é "fora do horário"."""

    timezone: str
    windows: list[ScheduleWindow] = Field(default_factory=list)
    holidays: list[date] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuso horário desconhecido: {value}") from exc
        return value

    def is_business_time(self, moment: datetime) -> bool:
        if moment.tzinfo is None:
            raise ValueError("moment precisa ter fuso horário")
        local = moment.astimezone(ZoneInfo(self.timezone))
        if local.date() in self.holidays:
            return False
        return any(window.contains(local) for window in self.windows)


class ZoneConfig(_Strict):
    """Polígono em coordenadas normalizadas (0-1) relativas à imagem."""

    id: UUID
    name: str
    version: int = Field(ge=1)
    polygon: list[Point] = Field(min_length=3, max_length=64)


class AfterHoursPresenceRule(_Strict):
    """Pessoa presente na zona fora do expediente.

    A regra observa o estado da zona (quantas pessoas estão nela), não um
    ``track_id`` individual, para não depender da estabilidade do rastreamento.
    """

    rule_type: Literal["person.after_hours"] = "person.after_hours"
    id: UUID
    version: int = Field(ge=1)
    zone_id: UUID
    enabled: bool = True
    shadow: bool = Field(
        default=False,
        description="Modo sombra: gera ocorrências marcadas, mas sem notificar ninguém.",
    )
    min_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    min_duration_seconds: float = Field(default=3.0, ge=0.0, le=3600.0)
    gap_tolerance_seconds: float = Field(
        default=2.0,
        ge=0.0,
        le=60.0,
        description="Falhas curtas de detecção que não reiniciam a contagem de duração.",
    )
    clear_after_seconds: float = Field(
        default=10.0,
        ge=0.0,
        le=3600.0,
        description="Tempo sem presença até a ocorrência ser encerrada.",
    )
    schedule: Schedule


# Quando houver mais tipos de regra, isto vira uma união discriminada por ``rule_type``.
RuleConfig = AfterHoursPresenceRule


Service = Literal["security", "operation"]


class CameraConfig(_Strict):
    """Uma câmera e o que o agente deve fazer com ela.

    ``services`` é o que o cliente contratou (ou está testando) para a câmera:
    ``security`` liga as regras de ocorrência, ``operation`` liga as métricas.
    A nuvem só envia câmeras com algum serviço ativo.
    """

    id: UUID
    name: str
    source_ref: str = Field(min_length=1, max_length=128)
    services: list[Service] = Field(default_factory=lambda: ["security", "operation"])
    analysis_fps: float = Field(default=5.0, gt=0.0, le=30.0)
    min_confidence: float = Field(
        default=0.35, ge=0.0, le=1.0, description="Limiar usado nas métricas de ocupação."
    )
    zones: list[ZoneConfig] = Field(default_factory=list)
    rules: list[RuleConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rules_reference_own_zones(self) -> "CameraConfig":
        zone_ids = {zone.id for zone in self.zones}
        for rule in self.rules:
            if rule.zone_id not in zone_ids:
                raise ValueError(f"regra {rule.id} aponta para zona de outra câmera")
        return self


class AgentConfig(_Strict):
    agent_id: UUID
    config_version: str
    generated_at: AwareDatetime
    cameras: list[CameraConfig] = Field(default_factory=list)
