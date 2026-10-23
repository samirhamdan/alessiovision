"""Ativação do agente com o código de uso único gerado no painel.

O token recebido fica em ``<state-dir>/credentials.json``, legível só pelo
usuário do sistema que roda o agente. Ele não aparece em linha de comando nem
em variáveis de ambiente, que costumam vazar em listas de processos e logs.
"""

import json
import os
import socket
from pathlib import Path

import httpx

from alessio_agent import __version__
from alessio_contracts import EnrollmentRequest, EnrollmentResult

CREDENTIALS_FILE = "credentials.json"


class EnrollmentError(RuntimeError):
    pass


def enroll(
    api_url: str, code: str, state_dir: Path, http: httpx.Client | None = None
) -> EnrollmentResult:
    client = http or httpx.Client(base_url=api_url, timeout=15.0)
    request = EnrollmentRequest(code=code, hostname=socket.gethostname(), agent_version=__version__)
    try:
        response = client.post("/agent/v1/enroll", json=request.model_dump())
    except httpx.HTTPError as exc:
        raise EnrollmentError(f"não foi possível falar com {api_url}: {exc}") from exc
    if response.status_code != 200:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise EnrollmentError(detail or f"ativação recusada (HTTP {response.status_code})")
    result = EnrollmentResult.model_validate_json(response.content)
    save_credentials(state_dir, api_url, result)
    return result


def save_credentials(state_dir: Path, api_url: str, result: EnrollmentResult) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / CREDENTIALS_FILE
    data = {"api_url": api_url, "agent_id": str(result.agent_id), "token": result.token}
    # Cria já com permissão 0600 para o token nunca ficar legível por outros usuários.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle)
    os.chmod(path, 0o600)
    return path


def load_credentials(state_dir: Path) -> dict[str, str] | None:
    path = state_dir / CREDENTIALS_FILE
    if not path.exists():
        return None
    return json.loads(path.read_text())
