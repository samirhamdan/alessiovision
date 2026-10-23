"""Comunicação com a plataforma: envio da fila local e download de configuração.

Toda conexão parte do agente (HTTPS de saída); nenhuma porta precisa ser aberta
na rede do cliente.
"""

import json
import logging
import threading
from pathlib import Path

import httpx

from alessio_agent.outbox import Outbox
from alessio_contracts import AgentConfig, BatchResult

log = logging.getLogger(__name__)


class AuthError(RuntimeError):
    """Credencial do agente recusada (revogada ou inválida)."""


class TransientError(RuntimeError):
    """Falha de rede ou da nuvem; a mensagem continua na fila."""


class CloudClient:
    def __init__(self, base_url: str, token: str, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(base_url=base_url, timeout=15.0)
        self._headers = {"Authorization": f"Bearer {token}"}

    def post_messages(self, bodies: list[str]) -> httpx.Response:
        content = '{"messages":[' + ",".join(bodies) + "]}"
        try:
            response = self._http.post(
                "/agent/v1/messages",
                content=content,
                headers={**self._headers, "Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise TransientError(str(exc)) from exc
        if response.status_code in (401, 403):
            raise AuthError(f"credencial recusada ({response.status_code})")
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientError(f"HTTP {response.status_code}")
        return response

    def fetch_config(self, etag: str | None) -> tuple[AgentConfig | None, str | None]:
        """Retorna ``(None, etag)`` quando a configuração não mudou."""
        headers = dict(self._headers)
        if etag:
            headers["If-None-Match"] = etag
        try:
            response = self._http.get("/agent/v1/config", headers=headers)
        except httpx.HTTPError as exc:
            raise TransientError(str(exc)) from exc
        if response.status_code in (401, 403):
            raise AuthError(f"credencial recusada ({response.status_code})")
        if response.status_code == 304:
            return None, etag
        if response.status_code != 200:
            raise TransientError(f"HTTP {response.status_code}")
        return AgentConfig.model_validate_json(response.content), response.headers.get("ETag")


class ConfigStore:
    """Mantém a última configuração recebida em disco para o agente iniciar sem internet."""

    def __init__(self, client: CloudClient, state_dir: Path) -> None:
        self._client = client
        self._path = state_dir / "config.json"

    def load(self) -> AgentConfig:
        cached: AgentConfig | None = None
        etag: str | None = None
        if self._path.exists():
            data = json.loads(self._path.read_text())
            cached = AgentConfig.model_validate(data["config"])
            etag = data.get("etag")
        try:
            fresh, etag = self._client.fetch_config(etag)
        except TransientError as exc:
            if cached is None:
                raise
            log.warning("nuvem indisponível (%s); usando configuração em cache", exc)
            return cached
        if fresh is None:
            assert cached is not None
            return cached
        self._path.write_text(
            json.dumps({"etag": etag, "config": fresh.model_dump(mode="json")}, indent=2)
        )
        return fresh


class Sender:
    """Esvazia a fila local em lotes, preservando a ordem."""

    def __init__(self, outbox: Outbox, client: CloudClient, batch_size: int = 200) -> None:
        self._outbox = outbox
        self._client = client
        self._batch_size = batch_size

    def flush_once(self) -> int:
        """Envia um lote. Retorna quantas mensagens saíram da fila pendente."""
        batch = self._outbox.pending(self._batch_size)
        if not batch:
            return 0
        ids = [message_id for message_id, _ in batch]
        try:
            response = self._client.post_messages([body for _, body in batch])
        except TransientError as exc:
            self._outbox.record_failure(ids, str(exc))
            raise
        if response.status_code == 200:
            self._apply(BatchResult.model_validate_json(response.content))
            return len(batch)
        if len(batch) > 1:
            # Lote recusado por inteiro (ex.: 422): reenvia uma a uma para isolar a culpada,
            # sem deixar uma mensagem inválida travar a fila.
            return sum(self._send_single(message_id, body) for message_id, body in batch)
        self._outbox.dead_letter({ids[0]: f"HTTP {response.status_code}: {response.text[:300]}"})
        return 1

    def _send_single(self, message_id: str, body: str) -> int:
        response = self._client.post_messages([body])
        if response.status_code == 200:
            self._apply(BatchResult.model_validate_json(response.content))
        else:
            self._outbox.dead_letter(
                {message_id: f"HTTP {response.status_code}: {response.text[:300]}"}
            )
        return 1

    def _apply(self, result: BatchResult) -> None:
        delivered = [str(r.message_id) for r in result.results if r.status != "rejected"]
        rejected = {
            str(r.message_id): r.reason or "rejeitada"
            for r in result.results
            if r.status == "rejected"
        }
        if rejected:
            log.error("nuvem rejeitou %d mensagem(ns): %s", len(rejected), rejected)
            self._outbox.dead_letter(rejected)
        self._outbox.acknowledge(delivered)

    def drain(self, stop: threading.Event | None = None) -> bool:
        """Envia até esvaziar a fila. Retorna False se uma falha transitória interromper."""
        while stop is None or not stop.is_set():
            try:
                if self.flush_once() == 0:
                    return True
            except TransientError as exc:
                log.warning("falha ao enviar (%s); mensagens mantidas na fila", exc)
                return False
        return False

    def run(self, stop: threading.Event, idle_seconds: float = 1.0) -> None:
        """Laço de envio em segundo plano, com espera exponencial em falhas."""
        backoff = 1.0
        while not stop.is_set():
            try:
                sent = self.flush_once()
                backoff = 1.0
                if sent == 0:
                    stop.wait(idle_seconds)
            except TransientError as exc:
                log.warning("falha ao enviar (%s); nova tentativa em %.0fs", exc, backoff)
                stop.wait(backoff)
                backoff = min(backoff * 2, 60.0)
            except AuthError:
                log.error("credencial do agente recusada; envio suspenso por 5 minutos")
                stop.wait(300)
