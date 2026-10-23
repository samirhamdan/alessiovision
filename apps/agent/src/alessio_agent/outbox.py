"""Fila local (SQLite) de mensagens para a nuvem.

Toda mensagem é gravada aqui antes do envio. Se a internet cair, o agente
continua analisando e acumulando; ao reconectar, reenvia na ordem original. A
nuvem descarta reenvios pelo ``message_id``.
"""

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import TypeAdapter

from alessio_contracts import (
    AgentMessage,
    Heartbeat,
    HeartbeatMessage,
    OccurrenceClosed,
    OccurrenceClosedMessage,
    OccurrenceOpened,
    OccurrenceOpenedMessage,
    OccurrenceUpdated,
    OccurrenceUpdatedMessage,
    ZoneMetrics1m,
    ZoneMetricsMessage,
)

_MESSAGE_ADAPTER = TypeAdapter(AgentMessage)

_ENVELOPES = {
    OccurrenceOpened: OccurrenceOpenedMessage,
    OccurrenceUpdated: OccurrenceUpdatedMessage,
    OccurrenceClosed: OccurrenceClosedMessage,
    ZoneMetrics1m: ZoneMetricsMessage,
    Heartbeat: HeartbeatMessage,
}

Payload = OccurrenceOpened | OccurrenceUpdated | OccurrenceClosed | ZoneMetrics1m | Heartbeat


def envelope(payload: Payload, session_id: UUID) -> AgentMessage:
    return _ENVELOPES[type(payload)](
        message_id=uuid4(),
        agent_session_id=session_id,
        sent_at=datetime.now(UTC),
        payload=payload,
    )


class Outbox:
    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS outbox_status_seq ON outbox (status, seq)")

    def enqueue(self, message: AgentMessage) -> None:
        body = _MESSAGE_ADAPTER.dump_json(message).decode()
        with self._lock:
            self._db.execute(
                "INSERT INTO outbox (message_id, body, created_at) VALUES (?, ?, ?)",
                (str(message.message_id), body, datetime.now(UTC).isoformat()),
            )

    def pending(self, limit: int) -> list[tuple[str, str]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT message_id, body FROM outbox WHERE status = 'pending' ORDER BY seq LIMIT ?",
                (limit,),
            ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def acknowledge(self, message_ids: list[str]) -> None:
        with self._lock:
            self._db.executemany(
                "DELETE FROM outbox WHERE message_id = ?", [(m,) for m in message_ids]
            )

    def record_failure(self, message_ids: list[str], error: str) -> None:
        with self._lock:
            self._db.executemany(
                "UPDATE outbox SET attempts = attempts + 1, last_error = ? WHERE message_id = ?",
                [(error[:500], m) for m in message_ids],
            )

    def dead_letter(self, failures: dict[str, str]) -> None:
        """Mensagens que a nuvem recusou: saem da fila, mas ficam guardadas para diagnóstico."""
        with self._lock:
            self._db.executemany(
                "UPDATE outbox SET status = 'dead', attempts = attempts + 1, last_error = ? "
                "WHERE message_id = ?",
                [(reason[:500], m) for m, reason in failures.items()],
            )

    def count(self, status: str = "pending") -> int:
        with self._lock:
            return self._db.execute(
                "SELECT COUNT(*) FROM outbox WHERE status = ?", (status,)
            ).fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._db.close()
