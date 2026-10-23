"""Orquestra o agente: configuração, uma thread por câmera, envio e heartbeat."""

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alessio_agent import __version__
from alessio_agent.cloud import CloudClient, ConfigStore, Sender
from alessio_agent.detection import Detector, build_detector
from alessio_agent.outbox import Outbox, Payload, envelope
from alessio_agent.pipeline import CameraPipeline
from alessio_agent.sources import FileSource, LiveSource, is_live, redact
from alessio_contracts import CameraConfig, CameraStatus, Heartbeat

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentSettings:
    api_url: str
    token: str
    sources_file: Path
    state_dir: Path
    detector: str = "hog"
    detector_model: str | None = None
    replay_start: datetime | None = None
    realtime: bool = False
    heartbeat_seconds: float = 30.0


def load_sources(path: Path) -> dict[str, str]:
    """Arquivo local ``{source_ref: uri}``. As URIs (com senha) nunca são enviadas à nuvem."""
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise ValueError(f"{path} deve ser um objeto JSON {{source_ref: uri}}")
    return data


class _CameraWorker:
    def __init__(self, pipeline: CameraPipeline, source: FileSource | LiveSource) -> None:
        self.pipeline = pipeline
        self.source = source
        self.thread: threading.Thread | None = None

    def start(self, stop: threading.Event) -> None:
        self.thread = threading.Thread(
            target=self._run, args=(stop,), name=f"camera-{self.pipeline.camera.name}", daemon=True
        )
        self.thread.start()

    def _run(self, stop: threading.Event) -> None:
        try:
            for item in self.source.frames(stop):
                self.pipeline.handle(item)
        except Exception as exc:
            log.exception("câmera %s parou", self.pipeline.camera.name)
            self.source.status, self.source.detail = "error", str(exc)[:200]
        finally:
            moment = self.pipeline.last_frame_at or datetime.now(UTC)
            self.pipeline.finish(moment, "shutdown")

    def status(self) -> CameraStatus:
        return self.pipeline.status(self.source.status, self.source.detail)


class Agent:
    def __init__(
        self,
        settings: AgentSettings,
        client: CloudClient | None = None,
        detector_factory: Callable[[], Detector] | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or CloudClient(settings.api_url, settings.token)
        self._detector_factory = detector_factory or (
            lambda: build_detector(settings.detector, settings.detector_model)
        )
        self.session_id = uuid4()
        settings.state_dir.mkdir(parents=True, exist_ok=True)
        self.outbox = Outbox(settings.state_dir / "outbox.sqlite3")

    def emit(self, payload: Payload) -> None:
        self.outbox.enqueue(envelope(payload, self.session_id))

    def run(self, stop: threading.Event) -> bool:
        """Executa até ``stop`` ou até todas as fontes terminarem (replay).

        Retorna True se a fila local foi totalmente entregue ao final.
        """
        config = ConfigStore(self.client, self.settings.state_dir).load()
        sources = load_sources(self.settings.sources_file)
        workers = [w for camera in config.cameras if (w := self._worker(camera, sources))]
        log.info(
            "agente %s (sessão %s): %d câmera(s)", config.agent_id, self.session_id, len(workers)
        )

        sender = Sender(self.outbox, self.client)
        sender_stop = threading.Event()
        sender_thread = threading.Thread(target=sender.run, args=(sender_stop,), daemon=True)
        sender_thread.start()

        for worker in workers:
            worker.start(stop)
        self._heartbeat(workers)
        next_heartbeat = time.monotonic() + self.settings.heartbeat_seconds
        while any(w.thread and w.thread.is_alive() for w in workers):
            if stop.wait(0.5):
                break
            if time.monotonic() >= next_heartbeat:
                self._heartbeat(workers)
                next_heartbeat += self.settings.heartbeat_seconds
        for worker in workers:
            if worker.thread:
                worker.thread.join()
        self._heartbeat(workers)

        sender_stop.set()
        sender_thread.join()
        delivered = sender.drain()
        log.info(
            "fila local: %d pendente(s), %d rejeitada(s)",
            self.outbox.count(),
            self.outbox.count("dead"),
        )
        self.outbox.close()
        return delivered

    def _worker(self, camera: CameraConfig, sources: dict[str, str]) -> _CameraWorker | None:
        uri = sources.get(camera.source_ref)
        if uri is None:
            log.error(
                "câmera %s: source_ref %r ausente em %s",
                camera.name,
                camera.source_ref,
                self.settings.sources_file,
            )
            return None
        log.info("câmera %s → %s", camera.name, redact(uri))
        pipeline = CameraPipeline(camera, self._detector_factory(), self.emit)
        if is_live(uri):
            return _CameraWorker(pipeline, LiveSource(uri, camera.analysis_fps))
        start_at = self.settings.replay_start or datetime.now(UTC)
        return _CameraWorker(
            pipeline, FileSource(uri, camera.analysis_fps, start_at, self.settings.realtime)
        )

    def _heartbeat(self, workers: list[_CameraWorker]) -> None:
        self.emit(Heartbeat(agent_version=__version__, cameras=[w.status() for w in workers]))
