"""Cria (ou atualiza) os dados de demonstração.

Uso: ``python -m alessio_api.seed``. Lê ``ALESSIO_DEMO_AGENT_TOKEN`` (se ausente,
gera e imprime um) e, para o login no painel, ``ALESSIO_DEMO_OWNER_EMAIL`` e
``ALESSIO_DEMO_OWNER_PASSWORD``. Só para demonstração e desenvolvimento: um
cliente real é criado com ``python -m alessio_api.admin`` e o agente é ativado
por código.
"""

import os
import sys
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alessio_api.db import get_sessionmaker
from alessio_api.models import (
    Agent,
    Camera,
    EventRule,
    Membership,
    Organization,
    Site,
    User,
    Zone,
)
from alessio_api.security import (
    generate_agent_token,
    hash_password,
    hash_token,
    password_problem,
)
from alessio_api.tenancy import set_tenant
from alessio_contracts import AfterHoursPresenceRule

DEFAULT_ORG_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")

# Segunda a sexta, 08:00-18:00 em São Paulo. Fora disso, qualquer presença na zona é ocorrência.
DEMO_RULE_CONFIG = {
    "min_confidence": 0.35,
    "min_duration_seconds": 3,
    "gap_tolerance_seconds": 2,
    "clear_after_seconds": 10,
    "schedule": {
        "timezone": "America/Sao_Paulo",
        "windows": [{"days": [0, 1, 2, 3, 4], "start": "08:00", "end": "18:00"}],
        "holidays": [],
    },
}


@dataclass(frozen=True)
class DemoIds:
    organization_id: uuid.UUID
    agent_id: uuid.UUID
    camera_id: uuid.UUID
    zone_id: uuid.UUID
    rule_id: uuid.UUID


def seed_demo(
    session: Session,
    org_id: uuid.UUID,
    agent_token: str,
    owner_email: str | None = None,
    owner_password: str | None = None,
    org_name: str = "Organização Demo",
) -> DemoIds:
    # Valida a configuração da regra com o mesmo contrato que o agente usa.
    AfterHoursPresenceRule(id=uuid.uuid4(), version=1, zone_id=uuid.uuid4(), **DEMO_RULE_CONFIG)

    org = session.get(Organization, org_id)
    if org is None:
        org = Organization(id=org_id, name=org_name)
        session.add(org)
        session.flush()
    set_tenant(session, org.id)

    if owner_email and owner_password:
        email = owner_email.lower()
        owner = session.scalar(select(User).where(User.email == email))
        if owner is None:
            owner = User(email=email, name="Pessoa Demo")
            session.add(owner)
        owner.password_hash = hash_password(owner_password)
        owner.status = "active"
        session.flush()
        if session.get(Membership, (org.id, owner.id)) is None:
            session.add(Membership(organization_id=org.id, user_id=owner.id, role="owner"))

    site = session.scalar(select(Site).where(Site.organization_id == org.id))
    if site is None:
        site = Site(organization_id=org.id, name="Escritório", timezone="America/Sao_Paulo")
        session.add(site)
        session.flush()

    agent = session.scalar(select(Agent).where(Agent.organization_id == org.id))
    if agent is None:
        agent = Agent(organization_id=org.id, site_id=site.id, name="agente-demo")
        session.add(agent)
    agent.token_hash = hash_token(agent_token)
    agent.status = "active"
    agent.enrolled_at = agent.enrolled_at or func.now()
    session.flush()

    camera = session.scalar(select(Camera).where(Camera.agent_id == agent.id))
    if camera is None:
        camera = Camera(
            organization_id=org.id,
            site_id=site.id,
            agent_id=agent.id,
            name="Entrada",
            source_ref="demo",
            analysis_fps=5.0,
            min_confidence=0.35,
        )
        session.add(camera)
        session.flush()

    zone = session.scalar(select(Zone).where(Zone.camera_id == camera.id))
    if zone is None:
        zone = Zone(
            organization_id=org.id,
            camera_id=camera.id,
            name="Área monitorada",
            version=1,
            polygon=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        )
        session.add(zone)
        session.flush()

    rule = session.scalar(select(EventRule).where(EventRule.zone_id == zone.id))
    if rule is None:
        rule = EventRule(
            organization_id=org.id,
            camera_id=camera.id,
            zone_id=zone.id,
            rule_type="person.after_hours",
            version=1,
            config=DEMO_RULE_CONFIG,
        )
        session.add(rule)
        session.flush()

    session.commit()
    return DemoIds(org.id, agent.id, camera.id, zone.id, rule.id)


def main() -> int:
    org_id = uuid.UUID(os.environ.get("ALESSIO_DEMO_ORG_ID", str(DEFAULT_ORG_ID)))
    token = os.environ.get("ALESSIO_DEMO_AGENT_TOKEN") or None  # vazio conta como ausente
    generated = token is None
    token = token or generate_agent_token()
    email = os.environ.get("ALESSIO_DEMO_OWNER_EMAIL") or None
    password = os.environ.get("ALESSIO_DEMO_OWNER_PASSWORD") or None
    if email and password_problem(password or ""):
        print(
            f"erro: ALESSIO_DEMO_OWNER_PASSWORD: {password_problem(password or '')}",
            file=sys.stderr,
        )
        return 1
    with get_sessionmaker()() as session:
        ids = seed_demo(session, org_id, token, email, password)
    print(f"organização: {ids.organization_id}")
    print(f"agente:      {ids.agent_id}")
    print(f"câmera:      {ids.camera_id} (source_ref 'demo')")
    if email:
        print(f"login:       {email.lower()}")
    if generated:
        print(f"token do agente (guarde, não será exibido novamente): {token}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
