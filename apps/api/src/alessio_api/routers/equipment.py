"""Equipamentos e contratos (comodato + serviços Vision no mesmo contrato).

Regras de negócio:
- A infraestrutura de um cliente pode ser dele ou da Alessio em comodato, e os
  dois tipos podem conviver no mesmo cliente (por item).
- Só a equipe Alessio cadastra e altera (área Plataforma). O administrador do
  cliente consulta.
- Equipamento em comodato pertence a um contrato ativo do mesmo cliente e pode
  ter valor mensal (soma na mensalidade; a cobrança ainda não está no sistema)
  e valor de reposição. Equipamento do cliente não tem contrato nem mensalidade.
- Encerrar um contrato lista o que ainda precisa ser devolvido.

Valores em centavos. Manutenção e documentos ficam fora por enquanto.
"""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alessio_api import audit
from alessio_api.auth import Principal, require, require_staff
from alessio_api.db import get_session
from alessio_api.models import Agent, Camera, Contract, Equipment, Organization, Site
from alessio_api.permissions import Permission
from alessio_api.routers.services import (
    end_contract_services,
    services_monthly_cents,
    services_overview,
)
from alessio_api.tenancy import set_tenant

router = APIRouter(prefix="/api/v1", tags=["equipamentos"])

SessionDep = Annotated[Session, Depends(get_session)]
StaffDep = Annotated[Principal, Depends(require_staff)]

Kind = Literal["camera", "agent_host", "recorder", "switch", "ups", "other"]
Ownership = Literal["client", "comodato"]
EquipmentStatus = Literal["in_use", "maintenance", "returned", "retired"]
Cents = Annotated[int, Field(ge=0, le=100_000_000)]
ShortText = Annotated[str, Field(max_length=100)]


# --- Esquemas -------------------------------------------------------------------------------


class ContractIn(BaseModel):
    number: str = Field(min_length=1, max_length=64)
    starts_on: date
    ends_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _dates(self) -> "ContractIn":
        if self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("o término não pode ser antes do início")
        return self


class ContractEndIn(BaseModel):
    ends_on: date


class ContractOut(BaseModel):
    id: UUID
    number: str
    starts_on: date
    ends_on: date | None
    status: Literal["active", "ended"]
    notes: str | None
    equipment_count: int
    service_count: int
    # Comodato em uso + serviços Vision ativos deste contrato.
    monthly_fee_cents: int
    pending_return: int


class EquipmentIn(BaseModel):
    kind: Kind
    ownership: Ownership
    brand: ShortText | None = None
    model: ShortText | None = None
    serial_number: ShortText | None = None
    site_id: UUID | None = None
    camera_id: UUID | None = None
    agent_id: UUID | None = None
    contract_id: UUID | None = None
    status: EquipmentStatus = "in_use"
    reference_value_cents: Cents | None = None
    monthly_fee_cents: Cents | None = None
    delivered_on: date | None = None
    returned_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _ownership_rules(self) -> "EquipmentIn":
        if self.ownership == "comodato" and self.contract_id is None:
            raise ValueError("equipamento em comodato precisa de um contrato")
        if self.ownership == "client" and (self.contract_id or self.monthly_fee_cents is not None):
            raise ValueError("equipamento do cliente não tem contrato nem valor mensal")
        return self


class EquipmentOut(BaseModel):
    id: UUID
    kind: Kind
    ownership: Ownership
    brand: str | None
    model: str | None
    serial_number: str | None
    site_id: UUID | None
    site_name: str | None
    camera_id: UUID | None
    camera_name: str | None
    agent_id: UUID | None
    agent_name: str | None
    contract_id: UUID | None
    contract_number: str | None
    status: EquipmentStatus
    reference_value_cents: int | None
    monthly_fee_cents: int | None
    delivered_on: date | None
    returned_on: date | None
    notes: str | None
    updated_at: datetime


class EquipmentSummary(BaseModel):
    total: int
    client_owned: int
    comodato: int
    comodato_monthly_cents: int
    comodato_reference_cents: int


class EquipmentList(BaseModel):
    summary: EquipmentSummary
    items: list[EquipmentOut]


class OrganizationOverview(BaseModel):
    id: UUID
    name: str
    status: str
    summary: EquipmentSummary
    active_contracts: int
    cameras_with_vision: int
    services_monthly_cents: int
    # Mensalidade = serviços Vision + comodato (a cobrança em si ainda não está no sistema).
    total_monthly_cents: int


class OptionOut(BaseModel):
    id: UUID
    name: str


class OrganizationContext(BaseModel):
    organization: OptionOut
    sites: list[OptionOut]
    cameras: list[OptionOut]
    agents: list[OptionOut]


# --- Consultas compartilhadas ---------------------------------------------------------------

IN_PLACE = ("in_use", "maintenance")  # o que ainda está no cliente


def _list_equipment(db: Session, organization_id: UUID) -> EquipmentList:
    rows = db.execute(
        select(Equipment, Site.name, Camera.name, Agent.name, Contract.number)
        .outerjoin(Site, Site.id == Equipment.site_id)
        .outerjoin(Camera, Camera.id == Equipment.camera_id)
        .outerjoin(Agent, Agent.id == Equipment.agent_id)
        .outerjoin(Contract, Contract.id == Equipment.contract_id)
        .where(Equipment.organization_id == organization_id)
        .order_by(Equipment.kind, Equipment.created_at)
    ).all()
    items = [
        EquipmentOut(
            id=e.id,
            kind=e.kind,
            ownership=e.ownership,
            brand=e.brand,
            model=e.model,
            serial_number=e.serial_number,
            site_id=e.site_id,
            site_name=site,
            camera_id=e.camera_id,
            camera_name=camera,
            agent_id=e.agent_id,
            agent_name=agent,
            contract_id=e.contract_id,
            contract_number=contract,
            status=e.status,
            reference_value_cents=e.reference_value_cents,
            monthly_fee_cents=e.monthly_fee_cents,
            delivered_on=e.delivered_on,
            returned_on=e.returned_on,
            notes=e.notes,
            updated_at=e.updated_at,
        )
        for e, site, camera, agent, contract in rows
    ]
    return EquipmentList(summary=_summary(items), items=items)


def _summary(items: list[EquipmentOut]) -> EquipmentSummary:
    in_place = [i for i in items if i.status in IN_PLACE]
    comodato = [i for i in in_place if i.ownership == "comodato"]
    return EquipmentSummary(
        total=len(in_place),
        client_owned=len(in_place) - len(comodato),
        comodato=len(comodato),
        comodato_monthly_cents=sum(i.monthly_fee_cents or 0 for i in comodato),
        comodato_reference_cents=sum(i.reference_value_cents or 0 for i in comodato),
    )


def _organization(db: Session, organization_id: UUID) -> Organization:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cliente não encontrado")
    set_tenant(db, organization.id)
    return organization


def _check_links(db: Session, organization_id: UUID, body: EquipmentIn, new: bool) -> None:
    """Site, câmera, agente e contrato precisam ser do mesmo cliente."""
    for model, value, label in (
        (Site, body.site_id, "local"),
        (Camera, body.camera_id, "câmera"),
        (Agent, body.agent_id, "agente"),
    ):
        if (
            value is not None
            and db.scalar(
                select(model.id).where(model.id == value, model.organization_id == organization_id)
            )
            is None
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{label} não encontrado")
    if body.contract_id is not None:
        contract = db.scalar(
            select(Contract).where(
                Contract.id == body.contract_id,
                Contract.organization_id == organization_id,
            )
        )
        if contract is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "contrato não encontrado")
        if new and contract.status != "active":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Esse contrato está encerrado. Use um contrato ativo para novos equipamentos.",
            )


def _apply(equipment: Equipment, body: EquipmentIn) -> None:
    for field, value in body.model_dump().items():
        setattr(equipment, field, value)
    if body.status == "returned" and equipment.returned_on is None:
        equipment.returned_on = date.today()


# --- Cliente (administrador consulta) -------------------------------------------------------


@router.get("/equipment", response_model=EquipmentList)
def client_equipment(
    principal: Annotated[Principal, Depends(require(Permission.EQUIPMENT_READ))], db: SessionDep
) -> EquipmentList:
    return _list_equipment(db, principal.organization_id)


# --- Plataforma (equipe Alessio) ------------------------------------------------------------


@router.get("/platform/organizations", response_model=list[OrganizationOverview])
def platform_organizations(staff: StaffDep, db: SessionDep) -> list[OrganizationOverview]:
    organizations = db.scalars(select(Organization).order_by(Organization.name)).all()
    overview = []
    for organization in organizations:
        set_tenant(db, organization.id)
        active = db.scalar(
            select(func.count())
            .select_from(Contract)
            .where(
                Contract.organization_id == organization.id,
                Contract.status == "active",
            )
        )
        summary = _list_equipment(db, organization.id).summary
        services = services_overview(db, organization.id)
        overview.append(
            OrganizationOverview(
                id=organization.id,
                name=organization.name,
                status=organization.status,
                summary=summary,
                active_contracts=active or 0,
                cameras_with_vision=sum(
                    1
                    for c in services.cameras
                    if (c.security and c.security.state == "active")
                    or (c.operation and c.operation.state == "active")
                ),
                services_monthly_cents=services.services_monthly_cents,
                total_monthly_cents=services.services_monthly_cents
                + summary.comodato_monthly_cents,
            )
        )
    return overview


@router.get("/platform/organizations/{organization_id}/context", response_model=OrganizationContext)
def platform_context(organization_id: UUID, staff: StaffDep, db: SessionDep) -> OrganizationContext:
    organization = _organization(db, organization_id)

    def options(model) -> list[OptionOut]:
        rows = db.execute(
            select(model.id, model.name)
            .where(model.organization_id == organization.id)
            .order_by(model.name)
        )
        return [OptionOut(id=row.id, name=row.name) for row in rows]

    return OrganizationContext(
        organization=OptionOut(id=organization.id, name=organization.name),
        sites=options(Site),
        cameras=options(Camera),
        agents=options(Agent),
    )


@router.get("/platform/organizations/{organization_id}/equipment", response_model=EquipmentList)
def platform_equipment(organization_id: UUID, staff: StaffDep, db: SessionDep) -> EquipmentList:
    organization = _organization(db, organization_id)
    return _list_equipment(db, organization.id)


@router.post(
    "/platform/organizations/{organization_id}/equipment",
    response_model=EquipmentList,
    status_code=status.HTTP_201_CREATED,
)
def platform_add_equipment(
    organization_id: UUID, body: EquipmentIn, staff: StaffDep, db: SessionDep
) -> EquipmentList:
    organization = _organization(db, organization_id)
    _check_links(db, organization.id, body, new=True)
    equipment = Equipment(organization_id=organization.id)
    _apply(equipment, body)
    db.add(equipment)
    db.flush()
    audit.record(
        db,
        organization.id,
        staff.user.id,
        "equipment.added",
        "equipment",
        equipment.id,
        kind=body.kind,
        ownership=body.ownership,
    )
    db.commit()
    return _list_equipment(db, organization.id)


@router.patch(
    "/platform/organizations/{organization_id}/equipment/{equipment_id}",
    response_model=EquipmentList,
)
def platform_update_equipment(
    organization_id: UUID, equipment_id: UUID, body: EquipmentIn, staff: StaffDep, db: SessionDep
) -> EquipmentList:
    organization = _organization(db, organization_id)
    equipment = db.scalar(
        select(Equipment)
        .where(Equipment.id == equipment_id, Equipment.organization_id == organization.id)
        .with_for_update()
    )
    if equipment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "equipamento não encontrado")
    # Trocar de contrato só para um ativo; manter o mesmo contrato encerrado é permitido
    # (por exemplo, para registrar a devolução).
    _check_links(db, organization.id, body, new=body.contract_id != equipment.contract_id)
    previous = {"status": equipment.status, "ownership": equipment.ownership}
    _apply(equipment, body)
    audit.record(
        db,
        organization.id,
        staff.user.id,
        "equipment.updated",
        "equipment",
        equipment.id,
        previous=previous,
        status=body.status,
        ownership=body.ownership,
    )
    db.commit()
    return _list_equipment(db, organization.id)


def _contracts(db: Session, organization_id: UUID) -> list[ContractOut]:
    contracts = db.scalars(
        select(Contract)
        .where(Contract.organization_id == organization_id)
        .order_by(Contract.status, Contract.starts_on.desc())
    ).all()
    equipment = db.scalars(
        select(Equipment).where(
            Equipment.organization_id == organization_id, Equipment.contract_id.is_not(None)
        )
    ).all()
    service_lines = services_overview(db, organization_id).history
    result = []
    for contract in contracts:
        lines = [line for line in service_lines if line.contract_id == contract.id]
        items = [e for e in equipment if e.contract_id == contract.id]
        in_place = [e for e in items if e.status in IN_PLACE]
        result.append(
            ContractOut(
                id=contract.id,
                number=contract.number,
                starts_on=contract.starts_on,
                ends_on=contract.ends_on,
                status=contract.status,
                notes=contract.notes,
                equipment_count=len(items),
                service_count=sum(1 for line in lines if line.state != "ended"),
                monthly_fee_cents=sum(e.monthly_fee_cents or 0 for e in in_place)
                + services_monthly_cents(lines, contract.id),
                pending_return=len(in_place) if contract.status == "ended" else 0,
            )
        )
    return result


@router.get("/platform/organizations/{organization_id}/contracts", response_model=list[ContractOut])
def platform_contracts(organization_id: UUID, staff: StaffDep, db: SessionDep) -> list[ContractOut]:
    organization = _organization(db, organization_id)
    return _contracts(db, organization.id)


@router.post(
    "/platform/organizations/{organization_id}/contracts",
    response_model=list[ContractOut],
    status_code=status.HTTP_201_CREATED,
)
def platform_add_contract(
    organization_id: UUID, body: ContractIn, staff: StaffDep, db: SessionDep
) -> list[ContractOut]:
    organization = _organization(db, organization_id)
    contract = Contract(organization_id=organization.id, **body.model_dump())
    db.add(contract)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Já existe um contrato com esse número neste cliente."
        ) from exc
    audit.record(
        db,
        organization.id,
        staff.user.id,
        "contract.created",
        "contract",
        contract.id,
        number=body.number,
    )
    db.commit()
    return _contracts(db, organization.id)


@router.post(
    "/platform/organizations/{organization_id}/contracts/{contract_id}/end",
    response_model=list[ContractOut],
)
def platform_end_contract(
    organization_id: UUID, contract_id: UUID, body: ContractEndIn, staff: StaffDep, db: SessionDep
) -> list[ContractOut]:
    """Encerra o contrato. Os equipamentos continuam listados até a devolução ser registrada."""
    organization = _organization(db, organization_id)
    contract = db.scalar(
        select(Contract)
        .where(
            Contract.id == contract_id,
            Contract.organization_id == organization.id,
        )
        .with_for_update()
    )
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contrato não encontrado")
    if body.ends_on < contract.starts_on:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "o término não pode ser antes do início"
        )
    contract.status = "ended"
    contract.ends_on = body.ends_on
    end_contract_services(db, contract)
    audit.record(db, organization.id, staff.user.id, "contract.ended", "contract", contract.id)
    db.commit()
    return _contracts(db, organization.id)
