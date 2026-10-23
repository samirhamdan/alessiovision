"""Fontes de vídeo: arquivo (replay com relógio simulado) e stream ao vivo (RTSP)."""

import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlparse

import cv2
import numpy as np

log = logging.getLogger(__name__)

LIVE_SCHEMES = {"rtsp", "rtsps", "rtmp", "http", "https"}


@dataclass(frozen=True, slots=True)
class Frame:
    timestamp: datetime
    image: np.ndarray


@dataclass(frozen=True, slots=True)
class SignalLost:
    timestamp: datetime
    detail: str


SourceItem = Frame | SignalLost
SourceStatus = Literal["connected", "disconnected", "error"]


def is_live(uri: str) -> bool:
    return urlparse(uri).scheme.lower() in LIVE_SCHEMES


def redact(uri: str) -> str:
    """Remove usuário e senha de uma URI antes de registrá-la em log."""
    parsed = urlparse(uri)
    if parsed.username or parsed.password:
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return parsed._replace(netloc=f"***@{host}").geturl()
    return uri


class FileSource:
    """Lê um arquivo de vídeo e atribui a cada quadro o horário ``start_at + posição``.

    Com ``realtime=False`` processa o mais rápido possível (testes, backtesting);
    com ``realtime=True`` respeita o ritmo do vídeo (demonstrações).
    """

    def __init__(
        self, path: str, analysis_fps: float, start_at: datetime, realtime: bool = False
    ) -> None:
        self.path = urlparse(path).path if path.startswith("file://") else path
        self.analysis_fps = analysis_fps
        self.start_at = start_at
        self.realtime = realtime
        self.status: SourceStatus = "disconnected"
        self.detail: str | None = None

    def frames(self, stop: threading.Event) -> Iterator[SourceItem]:
        capture = cv2.VideoCapture(self.path)
        if not capture.isOpened():
            self.status, self.detail = "error", f"não foi possível abrir {self.path}"
            raise FileNotFoundError(self.detail)
        self.status = "connected"
        source_fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        step = max(1, round(source_fps / self.analysis_fps))
        wall_start = time.monotonic()
        index = 0
        try:
            while not stop.is_set():
                if not capture.grab():
                    break
                if index % step == 0:
                    ok, image = capture.retrieve()
                    if ok:
                        offset = index / source_fps
                        if self.realtime:
                            delay = offset - (time.monotonic() - wall_start)
                            if delay > 0:
                                stop.wait(delay)
                        yield Frame(self.start_at + timedelta(seconds=offset), image)
                index += 1
        finally:
            capture.release()
            self.status = "disconnected"


class LiveSource:
    """Stream ao vivo com reconexão e espera exponencial (1 s a 30 s)."""

    def __init__(self, uri: str, analysis_fps: float) -> None:
        self.uri = uri
        self.analysis_fps = analysis_fps
        self.status: SourceStatus = "disconnected"
        self.detail: str | None = None

    def frames(self, stop: threading.Event) -> Iterator[SourceItem]:
        backoff = 1.0
        interval = 1.0 / self.analysis_fps
        while not stop.is_set():
            capture = cv2.VideoCapture(self.uri)
            if not capture.isOpened():
                self.status, self.detail = "error", "falha ao conectar"
                log.warning(
                    "câmera %s indisponível; nova tentativa em %.0fs", redact(self.uri), backoff
                )
                stop.wait(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            self.status, self.detail = "connected", None
            backoff = 1.0
            next_at = time.monotonic()
            try:
                while not stop.is_set():
                    # grab() descarta quadros sem decodificar, evitando acúmulo no buffer.
                    if not capture.grab():
                        self.status, self.detail = "disconnected", "stream interrompido"
                        yield SignalLost(datetime.now(UTC), self.detail)
                        break
                    if time.monotonic() < next_at:
                        continue
                    next_at = max(next_at + interval, time.monotonic())
                    ok, image = capture.retrieve()
                    if ok:
                        yield Frame(datetime.now(UTC), image)
            finally:
                capture.release()
