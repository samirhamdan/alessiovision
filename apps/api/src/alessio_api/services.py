"""Serviços Vision por câmera (regra R2).

- Cada câmera pode ter Vision Segurança, Vision Operação, as duas ou nenhuma.
- Um serviço vem de um contrato (valor negociado) ou de um teste grátis de
  ``trial_days`` dias, liberado pela equipe Alessio uma única vez por câmera e
  modalidade.
- Ativo enquanto ``starts_at <= agora < ends_at``. Quando termina, o agente para
  de analisar (a nuvem deixa de enviar a modalidade e recusa dados novos). O
  que acontece com o histórico depois do fim ainda está em decisão: por ora ele
  continua visível.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from alessio_api.models import Camera, CameraService, Site

SERVICES = ("security", "operation")


def now() -> datetime:
    return datetime.now(UTC)


def is_active(line: CameraService, moment: datetime) -> bool:
    return line.starts_at <= moment and (line.ends_at is None or line.ends_at > moment)


def active_services(
    db: Session, organization_id: UUID, moment: datetime | None = None
) -> dict[UUID, set[str]]:
    """{camera_id: {"security", "operation"}} com o que está ativo agora."""
    moment = moment or now()
    lines = db.scalars(
        select(CameraService).where(
            CameraService.organization_id == organization_id,
            CameraService.starts_at <= moment,
            (CameraService.ends_at.is_(None)) | (CameraService.ends_at > moment),
        )
    )
    result: dict[UUID, set[str]] = defaultdict(set)
    for line in lines:
        result[line.camera_id].add(line.service)
    return result


def camera_has(db: Session, camera: Camera, service: str, moment: datetime | None = None) -> bool:
    return service in active_services(db, camera.organization_id, moment).get(camera.id, set())


def end_of_day(db: Session, camera_id: UUID, day: date) -> datetime:
    """Fim do dia ``day`` no fuso do local da câmera (o serviço vale o dia inteiro)."""
    timezone = db.scalar(
        select(Site.timezone).join(Camera, Camera.site_id == Site.id).where(Camera.id == camera_id)
    )
    local = ZoneInfo(timezone or "America/Sao_Paulo")
    return datetime.combine(day + timedelta(days=1), time(0), local).astimezone(UTC)


def start_of_day(db: Session, camera_id: UUID, day: date) -> datetime:
    return end_of_day(db, camera_id, day - timedelta(days=1))
