"""Cadastro de clientes pela equipe Alessio (área Plataforma).

Ordem do cadastro: Cliente → Contrato → Locais ("haverá serviço Vision?") →
Agentes → Câmeras ("esta câmera terá serviço Vision?" e os dados do
equipamento, numa só operação). Ao criar o cliente, o local principal é criado
com o mesmo endereço, e o responsável recebe um convite de proprietário.
"""

import re
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alessio_api import audit
from alessio_api.auth import Principal, require_staff
from alessio_api.br import UFS, format_document, only_alnum, only_digits, valid_cnpj, valid_cpf
from alessio_api.db import get_session
from alessio_api.models import (
    Agent,
    Camera,
    Equipment,
    EventRule,
    Membership,
    Organization,
    Site,
    User,
    Zone,
)
from alessio_api.routers.admin import (
    AgentOut,
    EnrollmentCodeOut,
    _agent_out,
    _issue_invite,
    _new_code,
)
from alessio_api.routers.equipment import EquipmentIn
from alessio_api.routers.equipment import _apply as apply_equipment
from alessio_api.routers.equipment import _check_links as check_equipment_links
from alessio_api.routers.services import contract_service, services_overview, start_trial
from alessio_api.tenancy import set_tenant
from alessio_contracts import AfterHoursPresenceRule

router = APIRouter(prefix="/api/v1/platform", tags=["cadastro de clientes"])

SessionDep = Annotated[Session, Depends(get_session)]
StaffDep = Annotated[Principal, Depends(require_staff)]

DEFAULT_SCHEDULE_WINDOWS = [{"days": [0, 1, 2, 3, 4], "start": "08:00", "end": "18:00"}]


# --- Esquemas -------------------------------------------------------------------------------


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class AddressIn(BaseModel):
    postal_code: str | None = None
    street: str | None = Field(default=None, max_length=200)
    street_number: str | None = Field(default=None, max_length=20)
    complement: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, value):
        return _blank_to_none(value)

    @field_validator("postal_code")
    @classmethod
    def _cep(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits = only_digits(value)
        if len(digits) != 8:
            raise ValueError("CEP precisa ter 8 dígitos")
        return digits

    @field_validator("state")
    @classmethod
    def _uf(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.upper() not in UFS:
            raise ValueError("UF inválida")
        return value.upper()


ADDRESS_FIELDS = tuple(AddressIn.model_fields)


def _phone(value: str | None) -> str | None:
    if value is None:
        return None
    digits = only_digits(value)
    if len(digits) not in (10, 11):
        raise ValueError("telefone com DDD: 10 ou 11 dígitos")
    return digits


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="Nome fantasia (exibição)")
    person_type: Literal["pj", "pf"] = "pj"
    document: str
    legal_name: str = Field(
        min_length=1, max_length=200, description="Razão social ou nome completo"
    )
    state_registration: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    phone: str | None = None
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    address: AddressIn = Field(default_factory=AddressIn)
    notes: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "inactive"] = "active"

    @field_validator(
        "state_registration",
        "email",
        "phone",
        "contact_name",
        "contact_email",
        "contact_phone",
        "notes",
        mode="before",
    )
    @classmethod
    def _strip(cls, value):
        return _blank_to_none(value)

    @field_validator("phone", "contact_phone")
    @classmethod
    def _phones(cls, value: str | None) -> str | None:
        return _phone(value)

    @model_validator(mode="after")
    def _document(self) -> "ClientIn":
        if self.person_type == "pf":
            if not valid_cpf(self.document):
                raise ValueError("CPF inválido")
            self.document = only_digits(self.document)
        else:
            if not valid_cnpj(self.document):
                raise ValueError("CNPJ inválido")
            self.document = only_alnum(self.document)
        return self


class ClientCreateIn(ClientIn):
    site_name: str = Field(default="Matriz", min_length=1, max_length=200)
    timezone: str = "America/Sao_Paulo"
    # "Haverá serviço Vision no local principal?"
    site_vision_planned: bool = True
    # Convida o responsável (contact_email) como proprietário da organização.
    invite_contact: bool = True

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("fuso horário desconhecido") from exc
        return value


class AddressOut(BaseModel):
    postal_code: str | None
    street: str | None
    street_number: str | None
    complement: str | None
    district: str | None
    city: str | None
    state: str | None


class ClientOut(BaseModel):
    id: UUID
    name: str
    status: str
    person_type: str
    document: str | None
    document_formatted: str | None
    legal_name: str | None
    state_registration: str | None
    email: str | None
    phone: str | None
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    address: AddressOut
    notes: str | None
    created_at: datetime


class ClientCreatedOut(BaseModel):
    client: ClientOut
    # Link de convite do responsável, quando ele ainda não tem conta. Exibido uma vez.
    invite_token: str | None
    owner_email: str | None


class InviteOwnerIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = "America/Sao_Paulo"
    # "Haverá serviço Vision neste local?"
    vision_planned: bool = True
    address: AddressIn = Field(default_factory=AddressIn)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        return ClientCreateIn._tz(value)


class SiteOut(BaseModel):
    id: UUID
    name: str
    timezone: str
    vision_planned: bool
    address: AddressOut


def _source_ref(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError("apelido: use só letras, números, ponto, hífen e sublinhado")
    return value


class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    site_id: UUID
    agent_id: UUID
    # Apelido que o agente usa no sources.json local (o endereço RTSP nunca vem para a nuvem).
    source_ref: str = Field(min_length=1, max_length=128)
    analysis_fps: float = Field(default=5.0, gt=0, le=30)

    @field_validator("source_ref")
    @classmethod
    def _ref(cls, value: str) -> str:
        return _source_ref(value)


class CameraOut(BaseModel):
    id: UUID
    name: str
    site_id: UUID
    site_name: str
    agent_id: UUID
    agent_name: str
    source_ref: str
    analysis_fps: float
    services: list[str]


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    site_id: UUID


# --- Funções de apoio -----------------------------------------------------------------------


def _address(entity) -> AddressOut:
    return AddressOut(**{field: getattr(entity, field) for field in ADDRESS_FIELDS})


def _client_out(org: Organization) -> ClientOut:
    return ClientOut(
        id=org.id,
        name=org.name,
        status=org.status,
        person_type=org.person_type,
        document=org.document,
        document_formatted=format_document(org.person_type, org.document) if org.document else None,
        legal_name=org.legal_name,
        state_registration=org.state_registration,
        email=org.email,
        phone=org.phone,
        contact_name=org.contact_name,
        contact_email=org.contact_email,
        contact_phone=org.contact_phone,
        address=_address(org),
        notes=org.notes,
        created_at=org.created_at,
    )


def _apply_client(org: Organization, body: ClientIn) -> None:
    data = body.model_dump(
        exclude={"address", "site_name", "timezone", "invite_contact", "site_vision_planned"}
    )
    for field, value in data.items():
        setattr(org, field, value)
    for field, value in body.address.model_dump().items():
        setattr(org, field, value)


def _organization(db: Session, organization_id: UUID) -> Organization:
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cliente não encontrado")
    set_tenant(db, org.id)
    return org


def _document_conflict() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, "Já existe um cliente com esse CNPJ/CPF.")


def _invite_owner(
    db: Session, org: Organization, email: str, name: str, staff_id: UUID
) -> str | None:
    """Dá o papel de proprietário; cria a conta (com convite) se a pessoa ainda não tem."""
    email = email.lower()
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    token = None
    if user is None:
        user = User(email=email, name=name.strip(), status="invited")
        db.add(user)
        token, _ = _issue_invite(user)
        db.flush()
    elif user.status == "invited":
        token, _ = _issue_invite(user)
    membership = db.get(Membership, (org.id, user.id))
    if membership is None:
        db.add(Membership(organization_id=org.id, user_id=user.id, role="owner"))
    else:
        membership.role = "owner"
    audit.record(db, org.id, staff_id, "member.added", "user", user.id, role="owner")
    return token


def _site(db: Session, org: Organization, site_id: UUID) -> Site:
    site = db.scalar(select(Site).where(Site.id == site_id, Site.organization_id == org.id))
    if site is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "local não encontrado")
    return site


def _cameras(db: Session, org: Organization) -> list[CameraOut]:
    active = {c.camera_id: c for c in services_overview(db, org.id).cameras}
    rows = db.execute(
        select(Camera, Site.name, Agent.name)
        .join(Site, Site.id == Camera.site_id)
        .join(Agent, Agent.id == Camera.agent_id)
        .where(Camera.organization_id == org.id)
        .order_by(Camera.name)
    )
    result = []
    for camera, site_name, agent_name in rows:
        entry = active.get(camera.id)
        services = [
            name
            for name in ("security", "operation")
            if entry and getattr(entry, name) and getattr(entry, name).state == "active"
        ]
        result.append(
            CameraOut(
                id=camera.id,
                name=camera.name,
                site_id=camera.site_id,
                site_name=site_name,
                agent_id=camera.agent_id,
                agent_name=agent_name,
                source_ref=camera.source_ref,
                analysis_fps=camera.analysis_fps,
                services=services,
            )
        )
    return result


# --- Cliente --------------------------------------------------------------------------------


@router.post("/organizations", response_model=ClientCreatedOut, status_code=status.HTTP_201_CREATED)
def create_client(body: ClientCreateIn, staff: StaffDep, db: SessionDep) -> ClientCreatedOut:
    if db.scalar(select(Organization.id).where(Organization.document == body.document)):
        raise _document_conflict()
    org = Organization()
    _apply_client(org, body)
    db.add(org)
    try:
        db.flush()
    except IntegrityError as exc:
        raise _document_conflict() from exc
    set_tenant(db, org.id)
    site = Site(
        organization_id=org.id,
        name=body.site_name.strip(),
        timezone=body.timezone,
        vision_planned=body.site_vision_planned,
    )
    for field, value in body.address.model_dump().items():
        setattr(site, field, value)
    db.add(site)
    db.flush()
    audit.record(db, org.id, staff.user.id, "organization.created", "organization", org.id)
    token = None
    owner_email = None
    if body.invite_contact and body.contact_email:
        owner_email = body.contact_email.lower()
        token = _invite_owner(db, org, owner_email, body.contact_name or body.name, staff.user.id)
    db.commit()
    return ClientCreatedOut(client=_client_out(org), invite_token=token, owner_email=owner_email)


@router.get("/organizations/{organization_id}/profile", response_model=ClientOut)
def get_client(organization_id: UUID, staff: StaffDep, db: SessionDep) -> ClientOut:
    return _client_out(_organization(db, organization_id))


@router.put("/organizations/{organization_id}/profile", response_model=ClientOut)
def update_client(
    organization_id: UUID, body: ClientIn, staff: StaffDep, db: SessionDep
) -> ClientOut:
    org = _organization(db, organization_id)
    clash = db.scalar(
        select(Organization.id).where(
            Organization.document == body.document, Organization.id != org.id
        )
    )
    if clash:
        raise _document_conflict()
    _apply_client(org, body)
    audit.record(db, org.id, staff.user.id, "organization.updated", "organization", org.id)
    db.commit()
    return _client_out(org)


@router.post("/organizations/{organization_id}/owner-invite", response_model=ClientCreatedOut)
def invite_owner(
    organization_id: UUID, body: InviteOwnerIn, staff: StaffDep, db: SessionDep
) -> ClientCreatedOut:
    """Convida (ou reenvia o convite para) um proprietário do cliente."""
    org = _organization(db, organization_id)
    token = _invite_owner(db, org, body.email, body.name, staff.user.id)
    db.commit()
    return ClientCreatedOut(
        client=_client_out(org), invite_token=token, owner_email=body.email.lower()
    )


# --- Locais ---------------------------------------------------------------------------------


def _site_out(site: Site) -> SiteOut:
    return SiteOut(
        id=site.id,
        name=site.name,
        timezone=site.timezone,
        vision_planned=site.vision_planned,
        address=_address(site),
    )


@router.get("/organizations/{organization_id}/sites", response_model=list[SiteOut])
def list_sites(organization_id: UUID, staff: StaffDep, db: SessionDep) -> list[SiteOut]:
    org = _organization(db, organization_id)
    sites = db.scalars(select(Site).where(Site.organization_id == org.id).order_by(Site.name))
    return [_site_out(site) for site in sites]


@router.post(
    "/organizations/{organization_id}/sites",
    response_model=SiteOut,
    status_code=status.HTTP_201_CREATED,
)
def create_site(organization_id: UUID, body: SiteIn, staff: StaffDep, db: SessionDep) -> SiteOut:
    org = _organization(db, organization_id)
    site = Site(
        organization_id=org.id,
        name=body.name.strip(),
        timezone=body.timezone,
        vision_planned=body.vision_planned,
    )
    for field, value in body.address.model_dump().items():
        setattr(site, field, value)
    db.add(site)
    db.flush()
    audit.record(db, org.id, staff.user.id, "site.created", "site", site.id, name=site.name)
    db.commit()
    return _site_out(site)


@router.put("/organizations/{organization_id}/sites/{site_id}", response_model=SiteOut)
def update_site(
    organization_id: UUID, site_id: UUID, body: SiteIn, staff: StaffDep, db: SessionDep
) -> SiteOut:
    org = _organization(db, organization_id)
    site = _site(db, org, site_id)
    site.name = body.name.strip()
    site.timezone = body.timezone
    site.vision_planned = body.vision_planned
    for field, value in body.address.model_dump().items():
        setattr(site, field, value)
    audit.record(db, org.id, staff.user.id, "site.updated", "site", site.id)
    db.commit()
    return _site_out(site)


# --- Agentes --------------------------------------------------------------------------------


@router.get("/organizations/{organization_id}/agents", response_model=list[AgentOut])
def list_agents(organization_id: UUID, staff: StaffDep, db: SessionDep) -> list[AgentOut]:
    org = _organization(db, organization_id)
    rows = db.execute(
        select(Agent, Site.name)
        .join(Site, Site.id == Agent.site_id)
        .where(Agent.organization_id == org.id)
        .order_by(Agent.created_at)
    )
    return [_agent_out(agent, site_name) for agent, site_name in rows]


@router.post(
    "/organizations/{organization_id}/agents",
    response_model=EnrollmentCodeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_agent(
    organization_id: UUID, body: AgentIn, staff: StaffDep, db: SessionDep
) -> EnrollmentCodeOut:
    """A equipe Alessio pode instalar o agente no cliente: mesma regra da tela Agentes."""
    org = _organization(db, organization_id)
    site = _site(db, org, body.site_id)
    agent = Agent(organization_id=org.id, site_id=site.id, name=body.name.strip(), status="pending")
    db.add(agent)
    code, expires = _new_code(agent)
    db.flush()
    audit.record(db, org.id, staff.user.id, "agent.created", "agent", agent.id, name=agent.name)
    db.commit()
    return EnrollmentCodeOut(
        agent=_agent_out(agent, site.name), enrollment_code=code, enrollment_expires_at=expires
    )


# --- Câmeras --------------------------------------------------------------------------------


def _check_camera_links(db: Session, org: Organization, body: CameraIn) -> None:
    _site(db, org, body.site_id)
    if (
        db.scalar(
            select(Agent.id).where(Agent.id == body.agent_id, Agent.organization_id == org.id)
        )
        is None
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "agente não encontrado")


def _source_conflict(body: CameraIn) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        f"Esse agente já tem uma câmera com o apelido '{body.source_ref}'. Use outro apelido.",
    )


@router.get("/organizations/{organization_id}/cameras", response_model=list[CameraOut])
def list_cameras(organization_id: UUID, staff: StaffDep, db: SessionDep) -> list[CameraOut]:
    return _cameras(db, _organization(db, organization_id))


class ServiceChoice(BaseModel):
    service: Literal["security", "operation"]
    mode: Literal["contract", "trial"]
    contract_id: UUID | None = None
    monthly_fee_cents: int | None = Field(default=None, ge=0, le=100_000_000)

    @model_validator(mode="after")
    def _mode(self) -> "ServiceChoice":
        if self.mode == "contract" and self.contract_id is None:
            raise ValueError("serviço contratado precisa de um contrato")
        if self.mode == "trial" and (self.contract_id or self.monthly_fee_cents is not None):
            raise ValueError("teste grátis não tem contrato nem valor")
        return self


class VisionSetup(BaseModel):
    """A câmera terá serviço Vision: precisa de um agente e de um apelido."""

    agent_id: UUID
    source_ref: str = Field(min_length=1, max_length=128)
    analysis_fps: float = Field(default=5.0, gt=0, le=30)
    services: list[ServiceChoice] = Field(min_length=1, max_length=2)

    @field_validator("source_ref")
    @classmethod
    def _ref(cls, value: str) -> str:
        return _source_ref(value)

    @model_validator(mode="after")
    def _unique(self) -> "VisionSetup":
        if len({choice.service for choice in self.services}) != len(self.services):
            raise ValueError("cada modalidade só uma vez")
        return self


class CameraEquipment(BaseModel):
    """O equipamento físico da câmera (do cliente ou em comodato)."""

    ownership: Literal["client", "comodato"]
    contract_id: UUID | None = None
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    asset_tag: str | None = Field(default=None, max_length=50)
    reference_value_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    monthly_fee_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    delivered_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class CameraInstallIn(BaseModel):
    """Cadastro de uma câmera no cliente, numa só operação.

    ``vision`` responde "esta câmera terá serviço Vision?": com serviço, a câmera
    entra no sistema (agente, apelido, zona e regra padrão) e os serviços são
    contratados ou postos em teste. ``equipment`` registra o equipamento físico.
    Câmera sem Vision é só equipamento.
    """

    name: str = Field(min_length=1, max_length=200)
    site_id: UUID
    vision: VisionSetup | None = None
    equipment: CameraEquipment | None = None

    @model_validator(mode="after")
    def _something(self) -> "CameraInstallIn":
        if self.vision is None and self.equipment is None:
            raise ValueError("informe o serviço Vision, o equipamento ou os dois")
        return self


class InstallOut(BaseModel):
    camera_id: UUID | None
    equipment_id: UUID | None


@router.post(
    "/organizations/{organization_id}/cameras",
    response_model=InstallOut,
    status_code=status.HTTP_201_CREATED,
)
def install_camera(
    organization_id: UUID, body: CameraInstallIn, staff: StaffDep, db: SessionDep
) -> InstallOut:
    org = _organization(db, organization_id)
    site = _site(db, org, body.site_id)
    camera = None
    if body.vision:
        if not site.vision_planned:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"O local {site.name} foi cadastrado sem serviço Vision. "
                "Altere o local para incluir o serviço.",
            )
        camera = _create_system_camera(db, org, site, body.name, body.vision, staff.user.id)
        for choice in body.vision.services:
            if choice.mode == "trial":
                start_trial(db, camera, choice.service, staff.user.id)
            else:
                contract_service(
                    db,
                    camera,
                    choice.service,
                    choice.contract_id,
                    choice.monthly_fee_cents,
                    None,
                    staff.user.id,
                )
    equipment_id = None
    if body.equipment:
        data = body.equipment.model_dump()
        equipment_in = EquipmentIn(
            kind="camera",
            site_id=site.id,
            camera_id=camera.id if camera else None,
            **data,
        )
        check_equipment_links(db, org.id, equipment_in, new=True)
        equipment = Equipment(organization_id=org.id)
        apply_equipment(equipment, equipment_in)
        db.add(equipment)
        db.flush()
        equipment_id = equipment.id
        audit.record(
            db,
            org.id,
            staff.user.id,
            "equipment.added",
            "equipment",
            equipment.id,
            kind="camera",
            ownership=equipment_in.ownership,
        )
    db.commit()
    return InstallOut(camera_id=camera.id if camera else None, equipment_id=equipment_id)


def _create_system_camera(
    db: Session, org: Organization, site: Site, name: str, vision: VisionSetup, user_id: UUID
) -> Camera:
    """Câmera no sistema, com a zona "Imagem inteira" e a regra padrão de presença fora
    do horário (seg. a sex., 8h às 18h, no fuso do local). Ajustar zona e horário vem
    com o editor de zonas e as regras configuráveis."""
    if (
        db.scalar(
            select(Agent.id).where(Agent.id == vision.agent_id, Agent.organization_id == org.id)
        )
        is None
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "agente não encontrado")
    camera = Camera(
        organization_id=org.id,
        site_id=site.id,
        agent_id=vision.agent_id,
        name=name.strip(),
        source_ref=vision.source_ref,
        analysis_fps=vision.analysis_fps,
        min_confidence=0.35,
    )
    db.add(camera)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Esse agente já tem uma câmera com o apelido '{vision.source_ref}'. "
            "Use outro apelido.",
        ) from exc
    zone = Zone(
        organization_id=org.id,
        camera_id=camera.id,
        name="Imagem inteira",
        version=1,
        polygon=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    )
    db.add(zone)
    db.flush()
    config = {
        "min_confidence": 0.35,
        "min_duration_seconds": 3,
        "gap_tolerance_seconds": 2,
        "clear_after_seconds": 10,
        "schedule": {
            "timezone": site.timezone,
            "windows": DEFAULT_SCHEDULE_WINDOWS,
            "holidays": [],
        },
    }
    AfterHoursPresenceRule(id=camera.id, version=1, zone_id=zone.id, **config)  # valida
    db.add(
        EventRule(
            organization_id=org.id,
            camera_id=camera.id,
            zone_id=zone.id,
            rule_type="person.after_hours",
            version=1,
            config=config,
        )
    )
    audit.record(db, org.id, user_id, "camera.created", "camera", camera.id, name=camera.name)
    return camera


@router.put("/organizations/{organization_id}/cameras/{camera_id}", response_model=list[CameraOut])
def update_camera(
    organization_id: UUID, camera_id: UUID, body: CameraIn, staff: StaffDep, db: SessionDep
) -> list[CameraOut]:
    org = _organization(db, organization_id)
    camera = db.scalar(
        select(Camera)
        .where(Camera.id == camera_id, Camera.organization_id == org.id)
        .with_for_update()
    )
    if camera is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "câmera não encontrada")
    _check_camera_links(db, org, body)
    for field, value in body.model_dump().items():
        setattr(camera, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        raise _source_conflict(body) from exc
    audit.record(db, org.id, staff.user.id, "camera.updated", "camera", camera.id)
    db.commit()
    return _cameras(db, org)
