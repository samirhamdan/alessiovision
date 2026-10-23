"""Cria (ou atualiza) os dados de demonstração da Fase 0.

Uso: ``python -m alessio_api.seed``. Lê ``ALESSIO_DASHBOARD_ORG_ID`` e
``ALESSIO_DEMO_AGENT_TOKEN``; se o token não for informado, gera e imprime um.

Os cadastros pelo painel chegam na Fase 1; até lá, este script é a única forma
de cadastrar organização, agente, câmera, zona e regra.
"""

import os
import sys
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from alessio_api.db import get_sessionmaker
from alessio_api.models import Agent, Camera, EventRule, Organization, Site, Zone
from alessio_api.security import generate_agent_token, hash_token
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


def seed_demo(session: Session, org_id: uuid.UUID, agent_token: str) -> DemoIds:
    # Valida a configuração da regra com o mesmo contrato que o agente usa.
    AfterHoursPresenceRule(id=uuid.uuid4(), version=1, zone_id=uuid.uuid4(), **DEMO_RULE_CONFIG)

    org = session.get(Organization, org_id)
    if org is None:
        org = Organization(id=org_id, name="Organização Demo")
        session.add(org)
        session.flush()

    site = session.scalar(select(Site).where(Site.organization_id == org.id))
    if site is None:
        site = Site(organization_id=org.id, name="Escritório", timezone="America/Sao_Paulo")
        session.add(site)
        session.flush()

    agent = session.scalar(select(Agent).where(Agent.organization_id == org.id))
    if agent is None:
        agent = Agent(organization_id=org.id, site_id=site.id, name="agente-demo", token_hash="")
        session.add(agent)
    agent.token_hash = hash_token(agent_token)
    agent.status = "active"
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
    org_id = uuid.UUID(os.environ.get("ALESSIO_DASHBOARD_ORG_ID", str(DEFAULT_ORG_ID)))
    token = os.environ.get("ALESSIO_DEMO_AGENT_TOKEN")
    generated = token is None
    token = token or generate_agent_token()
    with get_sessionmaker()() as session:
        ids = seed_demo(session, org_id, token)
    print(f"organização: {ids.organization_id}")
    print(f"agente:      {ids.agent_id}")
    print(f"câmera:      {ids.camera_id} (source_ref 'demo')")
    if generated:
        print(f"token do agente (guarde, não será exibido novamente): {token}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
