"""Isolamento entre organizações no próprio PostgreSQL (Row-Level Security).

Cada tabela de dados de cliente tem a política ``tenant_isolation``: só são
visíveis e graváveis as linhas cuja ``organization_id`` é igual à configuração
``app.current_org`` da transação. Sem organização definida, nada aparece. Assim
um filtro esquecido na aplicação não vaza dados de outro cliente.

``set_tenant`` grava a organização em ``session.info``; o evento ``after_begin``
reaplica a configuração em toda transação nova da mesma sessão (depois de um
``commit``, por exemplo). A configuração é local à transação, então nunca vaza
para o próximo uso da conexão no pool.

``agents`` tem também a política ``agent_lookup``, que permite *ler* um agente
quando ``app.agent_lookup`` é igual ao hash do token ou do código de ativação.
É o único jeito de achar um agente antes de saber a organização, e só revela a
linha de quem já conhece o segredo.
"""

from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.orm import Session

TENANT_TABLES = (
    "sites",
    "agents",
    "cameras",
    "zones",
    "event_rules",
    "occurrences",
    "occurrence_updates",
    "zone_metrics_1m",
    "audit_logs",
    "comodato_contracts",
    "equipment",
)

_SET = text("SELECT set_config(:name, :value, true)")


def set_tenant(session: Session, organization_id: UUID) -> None:
    session.info["organization_id"] = organization_id
    session.execute(_SET, {"name": "app.current_org", "value": str(organization_id)})


def set_agent_lookup(session: Session, secret_hash: str) -> None:
    """Válido só até o fim da transação atual."""
    session.execute(_SET, {"name": "app.agent_lookup", "value": secret_hash})


@event.listens_for(Session, "after_begin")
def _apply_tenant(session: Session, transaction, connection) -> None:
    organization_id = session.info.get("organization_id")
    if organization_id is not None:
        connection.execute(_SET, {"name": "app.current_org", "value": str(organization_id)})
