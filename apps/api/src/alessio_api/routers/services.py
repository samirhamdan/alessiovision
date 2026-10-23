"""Serviços Vision por câmera: contratação, teste grátis e encerramento (regra R2).

A equipe Alessio gerencia na área Plataforma; o administrador do cliente consulta.
"""

from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from alessio_api import audit
from alessio_api.auth import Principal, require, require_staff
from alessio_api.db import get_session
from alessio_api.models import Camera, CameraService, Contract, Organization
from alessio_api.permissions import Permission
from alessio_api.services import end_of_day, is_active, now, start_of_day
from alessio_api.settings import get_settings
from alessio_api.tenancy import set_tenant

router = APIRouter(prefix="/api/v1", tags=["serviços Vision"])

SessionDep = Annotated[Session, Depends(get_session)]
StaffDep = Annotated[Principal, Depends(require_staff)]
ServiceName = Literal["security", "operation"]


class ServiceLineOut(BaseModel):
    id: UUID
    camera_id: UUID
    service: ServiceName
    source: Literal["contract", "trial"]
    contract_id: UUID | None
    contract_number: str | None
    monthly_fee_cents: int | None
    starts_at: datetime
    ends_at: datetime | None
    state: Literal["active", "scheduled", "ended"]


class CameraServicesOut(BaseModel):
    camera_id: UUID
    camera_name: str
    security: ServiceLineOut | None
    operation: ServiceLineOut | None
    # Modalidades que já tiveram teste grátis nesta câmera (não pode repetir).
    trials_used: list[ServiceName]


class ServicesOut(BaseModel):
    cameras: list[CameraServicesOut]
    history: list[ServiceLineOut]
    services_monthly_cents: int


class ContractServiceIn(BaseModel):
    camera_id: UUID
    service: ServiceName
    contract_id: UUID
    monthly_fee_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    starts_on: date | None = None


class TrialIn(BaseModel):
    camera_id: UUID
    service: ServiceName


class EndServiceIn(BaseModel):
    # Último dia com serviço; vazio = encerra agora.
    ends_on: date | None = None


def _state(line: CameraService, moment: datetime) -> str:
    if is_active(line, moment):
        return "active"
    return "scheduled" if line.starts_at > moment else "ended"


def services_overview(db: Session, organization_id: UUID) -> ServicesOut:
    moment = now()
    cameras = db.scalars(
        select(Camera).where(Camera.organization_id == organization_id).order_by(Camera.name)
    ).all()
    rows = db.execute(
        select(CameraService, Contract.number)
        .outerjoin(Contract, Contract.id == CameraService.contract_id)
        .where(CameraService.organization_id == organization_id)
        .order_by(CameraService.starts_at.desc())
    ).all()
    lines = [
        ServiceLineOut(
            id=line.id,
            camera_id=line.camera_id,
            service=line.service,
            source=line.source,
            contract_id=line.contract_id,
            contract_number=number,
            monthly_fee_cents=line.monthly_fee_cents,
            starts_at=line.starts_at,
            ends_at=line.ends_at,
            state=_state(line, moment),
        )
        for line, number in rows
    ]
    by_camera = []
    for camera in cameras:
        mine = [line for line in lines if line.camera_id == camera.id]

        def current(service: str, mine=mine):
            # Ativo agora; senão o próximo agendado.
            for state in ("active", "scheduled"):
                for line in mine:
                    if line.service == service and line.state == state:
                        return line
            return None

        by_camera.append(
            CameraServicesOut(
                camera_id=camera.id,
                camera_name=camera.name,
                security=current("security"),
                operation=current("operation"),
                trials_used=sorted({line.service for line in mine if line.source == "trial"}),
            )
        )
    return ServicesOut(
        cameras=by_camera,
        history=lines,
        services_monthly_cents=services_monthly_cents(lines),
    )


def services_monthly_cents(lines: list[ServiceLineOut], contract_id: UUID | None = None) -> int:
    return sum(
        line.monthly_fee_cents or 0
        for line in lines
        if line.state == "active"
        and line.source == "contract"
        and (contract_id is None or line.contract_id == contract_id)
    )


def _organization(db: Session, organization_id: UUID) -> Organization:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cliente não encontrado")
    set_tenant(db, organization.id)
    return organization


def _camera(db: Session, organization_id: UUID, camera_id: UUID) -> Camera:
    camera = db.scalar(
        select(Camera)
        .where(Camera.id == camera_id, Camera.organization_id == organization_id)
        .with_for_update()
    )
    if camera is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "câmera não encontrada")
    return camera


def _current_lines(db: Session, camera: Camera, service: str) -> list[CameraService]:
    moment = now()
    return [
        line
        for line in db.scalars(
            select(CameraService).where(
                CameraService.camera_id == camera.id, CameraService.service == service
            )
        )
        if line.ends_at is None or line.ends_at > moment
    ]


LABEL = {"security": "Vision Segurança", "operation": "Vision Operação"}


# --- Cliente --------------------------------------------------------------------------------


@router.get("/services", response_model=ServicesOut)
def client_services(
    principal: Annotated[Principal, Depends(require(Permission.EQUIPMENT_READ))], db: SessionDep
) -> ServicesOut:
    return services_overview(db, principal.organization_id)


# --- Plataforma -----------------------------------------------------------------------------


@router.get("/platform/organizations/{organization_id}/services", response_model=ServicesOut)
def platform_services(organization_id: UUID, staff: StaffDep, db: SessionDep) -> ServicesOut:
    organization = _organization(db, organization_id)
    return services_overview(db, organization.id)


@router.post(
    "/platform/organizations/{organization_id}/services",
    response_model=ServicesOut,
    status_code=status.HTTP_201_CREATED,
)
def platform_contract_service(
    organization_id: UUID, body: ContractServiceIn, staff: StaffDep, db: SessionDep
) -> ServicesOut:
    """Contrata a modalidade para a câmera. Um teste em andamento é encerrado na hora."""
    organization = _organization(db, organization_id)
    camera = _camera(db, organization.id, body.camera_id)
    contract = db.scalar(
        select(Contract).where(
            Contract.id == body.contract_id, Contract.organization_id == organization.id
        )
    )
    if contract is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "contrato não encontrado")
    if contract.status != "active":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Esse contrato está encerrado. Use um contrato ativo.",
        )
    moment = now()
    starts_at = start_of_day(db, camera.id, body.starts_on) if body.starts_on else moment
    for line in _current_lines(db, camera, body.service):
        if line.source == "trial":
            line.ends_at = max(starts_at, line.starts_at + timedelta(microseconds=1))
        else:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"A câmera {camera.name} já tem {LABEL[body.service]} contratado. "
                "Encerre o serviço atual antes de contratar de novo.",
            )
    line = CameraService(
        organization_id=organization.id,
        camera_id=camera.id,
        service=body.service,
        source="contract",
        contract_id=contract.id,
        monthly_fee_cents=body.monthly_fee_cents,
        starts_at=starts_at,
        ends_at=end_of_day(db, camera.id, contract.ends_on) if contract.ends_on else None,
        created_by=staff.user.id,
    )
    db.add(line)
    db.flush()
    audit.record(
        db,
        organization.id,
        staff.user.id,
        "service.contracted",
        "camera",
        camera.id,
        service=body.service,
        contract=contract.number,
        monthly_fee_cents=body.monthly_fee_cents,
    )
    db.commit()
    return services_overview(db, organization.id)


@router.post(
    "/platform/organizations/{organization_id}/services/trial",
    response_model=ServicesOut,
    status_code=status.HTTP_201_CREATED,
)
def platform_start_trial(
    organization_id: UUID, body: TrialIn, staff: StaffDep, db: SessionDep
) -> ServicesOut:
    organization = _organization(db, organization_id)
    camera = _camera(db, organization.id, body.camera_id)
    used = db.scalar(
        select(CameraService.id).where(
            CameraService.camera_id == camera.id,
            CameraService.service == body.service,
            CameraService.source == "trial",
        )
    )
    if used is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A câmera {camera.name} já usou o teste de {LABEL[body.service]}.",
        )
    if _current_lines(db, camera, body.service):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A câmera {camera.name} já tem {LABEL[body.service]}."
        )
    moment = now()
    db.add(
        CameraService(
            organization_id=organization.id,
            camera_id=camera.id,
            service=body.service,
            source="trial",
            starts_at=moment,
            ends_at=moment + timedelta(days=get_settings().trial_days),
            created_by=staff.user.id,
        )
    )
    audit.record(
        db,
        organization.id,
        staff.user.id,
        "service.trial",
        "camera",
        camera.id,
        service=body.service,
    )
    db.commit()
    return services_overview(db, organization.id)


@router.post(
    "/platform/organizations/{organization_id}/services/{line_id}/end",
    response_model=ServicesOut,
)
def platform_end_service(
    organization_id: UUID, line_id: UUID, body: EndServiceIn, staff: StaffDep, db: SessionDep
) -> ServicesOut:
    organization = _organization(db, organization_id)
    line = db.scalar(
        select(CameraService)
        .where(CameraService.id == line_id, CameraService.organization_id == organization.id)
        .with_for_update()
    )
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serviço não encontrado")
    moment = now()
    ends_at = end_of_day(db, line.camera_id, body.ends_on) if body.ends_on else moment
    if line.ends_at is not None and line.ends_at <= moment:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esse serviço já terminou.")
    if ends_at <= line.starts_at:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "O término precisa ser depois do início."
        )
    line.ends_at = ends_at
    audit.record(
        db,
        organization.id,
        staff.user.id,
        "service.ended",
        "camera",
        line.camera_id,
        service=line.service,
        source=line.source,
    )
    db.commit()
    return services_overview(db, organization.id)


def end_contract_services(db: Session, contract: Contract) -> None:
    """Encerrar o contrato encerra os serviços dele no último dia do contrato."""
    assert contract.ends_on is not None
    for line in db.scalars(
        select(CameraService).where(CameraService.contract_id == contract.id).with_for_update()
    ):
        ends_at = end_of_day(db, line.camera_id, contract.ends_on)
        if line.ends_at is None or line.ends_at > ends_at:
            line.ends_at = max(ends_at, line.starts_at + timedelta(microseconds=1))
