"""Motor da regra "presença fora do horário".

Máquina de estados por regra:

    ocioso --presença--> pendente --duração mínima--> ativa --sem presença--> ocioso

A ocorrência é uma entidade única do início ao fim: o agente gera o
``occurrence_id`` e envia ``opened``, ``updated`` (só quando o número máximo de
pessoas aumenta) e ``closed``. Uma presença de 20 minutos vira uma ocorrência,
não N eventos.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from alessio_contracts import (
    AfterHoursPresenceRule,
    OccurrenceClosed,
    OccurrenceOpened,
    OccurrenceUpdated,
    ZoneConfig,
)

OccurrencePayload = OccurrenceOpened | OccurrenceUpdated | OccurrenceClosed
CloseReason = Literal["cleared", "schedule", "signal_lost", "shutdown"]


@dataclass
class _Pending:
    first_seen: datetime
    last_seen: datetime
    max_people: int
    max_confidence: float


@dataclass
class _Active:
    occurrence_id: UUID
    last_seen: datetime
    max_people: int


class AfterHoursPresenceEngine:
    def __init__(self, camera_id: UUID, zone: ZoneConfig, rule: AfterHoursPresenceRule) -> None:
        if rule.zone_id != zone.id:
            raise ValueError("a regra não pertence a esta zona")
        self.camera_id = camera_id
        self.zone = zone
        self.rule = rule
        self._state: _Pending | _Active | None = None

    @property
    def active_occurrence_id(self) -> UUID | None:
        return self._state.occurrence_id if isinstance(self._state, _Active) else None

    def observe(
        self, moment: datetime, people_count: int, max_confidence: float
    ) -> list[OccurrencePayload]:
        """Avalia um quadro analisado. ``people_count`` já usa ``rule.min_confidence``."""
        if not self.rule.enabled:
            return []
        after_hours = not self.rule.schedule.is_business_time(moment)
        present = after_hours and people_count > 0
        state = self._state

        if isinstance(state, _Active):
            if present:
                state.last_seen = moment
                if people_count > state.max_people:
                    state.max_people = people_count
                    return [
                        OccurrenceUpdated(
                            occurrence_id=state.occurrence_id,
                            observed_at=moment,
                            people_count=people_count,
                            max_people=people_count,
                        )
                    ]
                return []
            if not after_hours:
                return self._close(moment, "schedule")
            if (moment - state.last_seen).total_seconds() >= self.rule.clear_after_seconds:
                return self._close(state.last_seen, "cleared")
            return []

        if isinstance(state, _Pending):
            if not present:
                gap = (moment - state.last_seen).total_seconds()
                if gap > self.rule.gap_tolerance_seconds:
                    self._state = None
                return []
            state.last_seen = moment
            state.max_people = max(state.max_people, people_count)
            state.max_confidence = max(state.max_confidence, max_confidence)
        elif present:
            state = self._state = _Pending(moment, moment, people_count, max_confidence)
        else:
            return []

        if (moment - state.first_seen).total_seconds() >= self.rule.min_duration_seconds:
            return [self._open(state, moment, people_count)]
        return []

    def close(self, moment: datetime, reason: CloseReason) -> list[OccurrencePayload]:
        """Encerra a ocorrência ativa (perda de sinal, desligamento) e descarta pendências."""
        if isinstance(self._state, _Active):
            return self._close(min(moment, self._state.last_seen), reason)
        self._state = None
        return []

    def _open(self, pending: _Pending, moment: datetime, people_count: int) -> OccurrenceOpened:
        occurrence_id = uuid4()
        self._state = _Active(occurrence_id, moment, pending.max_people)
        return OccurrenceOpened(
            occurrence_id=occurrence_id,
            camera_id=self.camera_id,
            zone_id=self.zone.id,
            rule_id=self.rule.id,
            rule_version=self.rule.version,
            zone_version=self.zone.version,
            event_type=self.rule.rule_type,
            shadow=self.rule.shadow,
            started_at=pending.first_seen,
            confirmed_at=moment,
            people_count=people_count,
            max_confidence=round(pending.max_confidence, 4),
        )

    def _close(self, ended_at: datetime, reason: CloseReason) -> list[OccurrencePayload]:
        state = self._state
        assert isinstance(state, _Active)
        self._state = None
        return [
            OccurrenceClosed(
                occurrence_id=state.occurrence_id,
                ended_at=ended_at,
                max_people=state.max_people,
                reason=reason,
            )
        ]
