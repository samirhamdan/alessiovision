"""Monta a configuração (contrato ``AgentConfig``) de um agente a partir do banco."""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from alessio_api.models import Agent, Camera, EventRule, Zone
from alessio_api.services import active_services
from alessio_contracts import AfterHoursPresenceRule, AgentConfig, CameraConfig, ZoneConfig


def build_agent_config(session: Session, agent: Agent) -> AgentConfig:
    services = active_services(session, agent.organization_id)
    # Câmera sem serviço Vision ativo não é enviada: o agente nem abre o vídeo dela.
    cameras = [
        camera
        for camera in session.scalars(
            select(Camera).where(Camera.agent_id == agent.id).order_by(Camera.created_at, Camera.id)
        )
        if services.get(camera.id)
    ]
    camera_ids = [camera.id for camera in cameras]
    zones = session.scalars(
        select(Zone).where(Zone.camera_id.in_(camera_ids)).order_by(Zone.created_at, Zone.id)
    ).all()
    rules = session.scalars(
        select(EventRule)
        .where(EventRule.camera_id.in_(camera_ids))
        .order_by(EventRule.created_at, EventRule.id)
    ).all()

    camera_configs = [
        CameraConfig(
            id=camera.id,
            name=camera.name,
            source_ref=camera.source_ref,
            analysis_fps=camera.analysis_fps,
            min_confidence=camera.min_confidence,
            services=sorted(services[camera.id]),
            zones=[
                ZoneConfig(
                    id=zone.id,
                    name=zone.name,
                    version=zone.version,
                    polygon=[tuple(point) for point in zone.polygon],
                )
                for zone in zones
                if zone.camera_id == camera.id
            ],
            rules=[
                AfterHoursPresenceRule(
                    **rule.config,
                    id=rule.id,
                    version=rule.version,
                    zone_id=rule.zone_id,
                    enabled=rule.enabled,
                    shadow=rule.shadow,
                )
                for rule in rules
                if rule.camera_id == camera.id and rule.rule_type == "person.after_hours"
            ],
        )
        for camera in cameras
    ]
    canonical = json.dumps(
        [camera.model_dump(mode="json") for camera in camera_configs], sort_keys=True
    )
    version = hashlib.sha256(canonical.encode()).hexdigest()[:32]
    return AgentConfig(
        agent_id=agent.id,
        config_version=version,
        generated_at=datetime.now(UTC),
        cameras=camera_configs,
    )
