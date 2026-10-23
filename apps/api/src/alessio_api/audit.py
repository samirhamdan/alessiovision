from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from alessio_api.models import AuditLog


def record(
    db: Session,
    organization_id: UUID,
    user_id: UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: object | None = None,
    **details: Any,
) -> None:
    """Registra uma ação administrativa. Nunca inclua segredos em ``details``."""
    db.add(
        AuditLog(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details,
        )
    )
