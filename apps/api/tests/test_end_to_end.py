"""Fluxo completo: código de ativação no painel → agente ativado → vídeo →
ocorrência no PostgreSQL (com RLS) → API do painel autenticada.

O agente real (ativação, fila local, envio, configuração) conversa com a API
real; só o detector é substituído por um roteiro determinístico.
"""

import json
import stat
import threading
from datetime import UTC, datetime, timedelta

from alessio_agent.cloud import CloudClient
from alessio_agent.enrollment import enroll, load_credentials
from alessio_agent.runner import Agent, AgentSettings
from alessio_agent.testing import CENTER_PERSON, ScriptedDetector, write_test_video

# Sexta 23/10/2026, 23:00 em São Paulo: fora do expediente da regra de demonstração.
REPLAY_START = datetime(2026, 10, 24, 2, 0, tzinfo=UTC)


def test_video_to_dashboard(client, demo, tmp_path):
    code = client.post(f"/api/v1/agents/{demo.agent_id}/enrollment-code").json()["enrollment_code"]
    state_dir = tmp_path / "state"
    enroll("http://testserver", code, state_dir, http=client)
    assert stat.S_IMODE((state_dir / "credentials.json").stat().st_mode) == 0o600
    agent_token = load_credentials(state_dir)["token"]

    video = write_test_video(tmp_path / "demo.avi", seconds=30, fps=10)
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps({"demo": str(video)}))
    # Analisado a 5 fps: pessoa presente do quadro 10 ao 59 (de 2 s a 12 s do vídeo).
    detector = ScriptedDetector(lambda i: [CENTER_PERSON] if 10 <= i < 60 else [])

    agent = Agent(
        AgentSettings(
            api_url="http://testserver",
            token=agent_token,
            sources_file=sources,
            state_dir=state_dir,
            replay_start=REPLAY_START,
        ),
        client=CloudClient("http://testserver", agent_token, http=client),
        detector_factory=lambda: detector,
    )
    assert agent.run(threading.Event()) is True
    assert detector.calls == 150

    [occurrence] = client.get("/api/v1/occurrences").json()
    assert occurrence["event_type"] == "person.after_hours"
    assert occurrence["state"] == "closed"
    assert occurrence["close_reason"] == "cleared"
    assert occurrence["max_people"] == 1
    assert occurrence["started_at"] == "2026-10-24T02:00:02Z"
    assert occurrence["ended_at"] == "2026-10-24T02:00:11.800000Z"

    [camera] = client.get("/api/v1/cameras").json()
    assert camera["status"] == "disconnected"  # o arquivo terminou
    assert camera["last_frame_at"] == "2026-10-24T02:00:29.800000Z"

    [minute] = client.get(
        f"/api/v1/zones/{occurrence['zone_id']}/metrics",
        params={
            "from": REPLAY_START.isoformat(),
            "to": (REPLAY_START + timedelta(minutes=5)).isoformat(),
        },
    ).json()
    assert minute["analyzed_seconds"] == 30.0
    assert minute["occupancy_max"] == 1
    assert abs(minute["occupancy_avg"] - 10 / 30) < 1e-3  # arredondado a 4 casas
