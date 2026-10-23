import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from alessio_agent.cloud import CloudClient, Sender, TransientError
from alessio_agent.outbox import Outbox, envelope
from alessio_contracts import Heartbeat


def make_outbox(tmp_path, n=3):
    outbox = Outbox(tmp_path / "outbox.sqlite3")
    session = uuid4()
    ids = []
    for _ in range(n):
        message = envelope(Heartbeat(agent_version="t"), session)
        outbox.enqueue(message)
        ids.append(str(message.message_id))
    return outbox, ids


def client_for(handler) -> CloudClient:
    http = httpx.Client(base_url="http://cloud", transport=httpx.MockTransport(handler))
    return CloudClient("http://cloud", "tok", http=http)


def results(request, status_for):
    messages = json.loads(request.content)["messages"]
    return httpx.Response(
        200,
        json={
            "results": [
                {"message_id": m["message_id"], "status": status_for(m["message_id"])}
                for m in messages
            ]
        },
    )


def test_delivered_and_duplicate_leave_queue_rejected_goes_to_dead_letter(tmp_path):
    outbox, ids = make_outbox(tmp_path)
    statuses = {ids[0]: "accepted", ids[1]: "duplicate", ids[2]: "rejected"}
    seen_auth = []

    def handler(request):
        seen_auth.append(request.headers["Authorization"])
        return results(request, statuses.__getitem__)

    sender = Sender(outbox, client_for(handler))
    assert sender.drain()
    assert outbox.count() == 0
    assert outbox.count("dead") == 1
    assert seen_auth == ["Bearer tok"]


def test_server_error_keeps_messages_for_retry(tmp_path):
    outbox, _ = make_outbox(tmp_path)
    sender = Sender(outbox, client_for(lambda request: httpx.Response(503)))
    with pytest.raises(TransientError):
        sender.flush_once()
    assert outbox.count() == 3
    assert not sender.drain()


def test_network_failure_keeps_messages(tmp_path):
    outbox, _ = make_outbox(tmp_path)

    def handler(request):
        raise httpx.ConnectError("sem rede")

    assert not Sender(outbox, client_for(handler)).drain()
    assert outbox.count() == 3


def test_invalid_batch_is_split_to_isolate_the_bad_message(tmp_path):
    outbox, ids = make_outbox(tmp_path)
    bad = ids[1]

    def handler(request):
        messages = json.loads(request.content)["messages"]
        if any(m["message_id"] == bad for m in messages):
            return httpx.Response(422, json={"detail": "inválida"})
        return results(request, lambda _: "accepted")

    assert Sender(outbox, client_for(handler)).drain()
    assert outbox.count() == 0
    assert outbox.count("dead") == 1


def test_outbox_survives_restart_in_order(tmp_path):
    outbox, ids = make_outbox(tmp_path)
    outbox.close()
    reopened = Outbox(tmp_path / "outbox.sqlite3")
    assert [message_id for message_id, _ in reopened.pending(10)] == ids
    body = json.loads(reopened.pending(1)[0][1])
    assert body["type"] == "heartbeat" and body["schema_version"] == "1.0"
    assert datetime.fromisoformat(body["sent_at"].replace("Z", "+00:00")) <= datetime.now(UTC)
