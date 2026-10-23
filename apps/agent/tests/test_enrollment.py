import json
import stat
from uuid import uuid4

import httpx
import pytest

from alessio_agent.cli import main
from alessio_agent.enrollment import EnrollmentError, enroll, load_credentials


def http_with(handler):
    return httpx.Client(base_url="http://cloud", transport=httpx.MockTransport(handler))


def test_successful_enrollment_saves_private_credentials(tmp_path):
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "agent_id": str(uuid4()),
                "organization_name": "Acme",
                "agent_name": "Recepção",
                "token": "alg_x",
            },
        )

    result = enroll("http://cloud", "K7QX-M2PA-9TRD-H4WN", tmp_path, http=http_with(handler))
    assert result.agent_name == "Recepção"
    assert seen["code"] == "K7QX-M2PA-9TRD-H4WN" and seen["hostname"]
    path = tmp_path / "credentials.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_credentials(tmp_path) == {
        "api_url": "http://cloud",
        "agent_id": str(result.agent_id),
        "token": "alg_x",
    }


def test_refused_code_shows_the_cloud_message_and_saves_nothing(tmp_path):
    def handler(request):
        return httpx.Response(400, json={"detail": "Código de ativação inválido ou expirado."})

    with pytest.raises(EnrollmentError, match="inválido ou expirado"):
        enroll("http://cloud", "AAAA-BBBB-CCCC-DDDD", tmp_path, http=http_with(handler))
    assert load_credentials(tmp_path) is None


def test_run_without_credentials_explains_how_to_enroll(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ALESSIO_AGENT_TOKEN", raising=False)
    assert main(["--state-dir", str(tmp_path)]) == 2
    assert "alessio-agent enroll" in capsys.readouterr().err


def test_refused_credential_exits_with_instructions(tmp_path, capsys, monkeypatch):
    import alessio_agent.cli as cli
    from alessio_agent.cloud import AuthError

    class RefusedAgent:
        def __init__(self, settings):
            pass

        def run(self, stop):
            raise AuthError("credencial recusada (401)")

    monkeypatch.setattr(cli, "Agent", RefusedAgent)
    assert main(["run", "--token", "alg_x", "--state-dir", str(tmp_path)]) == 3
    assert "Gere um novo código" in capsys.readouterr().err
