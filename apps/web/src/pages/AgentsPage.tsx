import { type FormEvent, useEffect, useState } from "react";

import { type AgentInfo, type EnrollmentCode, api } from "../api";
import { formatAgo, formatDate } from "../format";
import {
  Badge,
  type BadgeTone,
  Button,
  Callout,
  type Column,
  DataTable,
  Panel,
  SecretField,
  SelectField,
  TextField,
} from "../ui";
import { useResource } from "../useResource";

function agentStatus(agent: AgentInfo): { label: string; tone: BadgeTone } {
  if (agent.status === "revoked") return { label: "Revogado", tone: "neutral" };
  if (agent.status === "pending") return { label: "Aguardando ativação", tone: "warn" };
  return { label: "Ativo", tone: "ok" };
}

function EnrollmentInstructions({ result, onClose }: { result: EnrollmentCode; onClose: () => void }) {
  const command = `alessio-agent enroll --api-url ${window.location.origin} --code ${result.enrollment_code}`;
  return (
    <Panel
      title={`Ativar "${result.agent.name}"`}
      actions={
        <Button size="sm" variant="ghost" onClick={onClose}>
          Concluído
        </Button>
      }
    >
      <div className="stack">
        <Callout tone="neutral" title="Este código aparece só agora">
          Ele vale uma única vez, até {formatDate(result.enrollment_expires_at)}. Se perder, gere outro.
        </Callout>
        <SecretField label="Código de ativação" value={result.enrollment_code} />
        <SecretField
          label="Comando para rodar no computador do agente"
          value={command}
          hint="O agente troca o código por uma credencial própria e a guarda só naquele computador."
        />
      </div>
    </Panel>
  );
}

export function AgentsPage() {
  const agents = useResource(api.agents, 10000);
  const sites = useResource(api.sites);
  const [name, setName] = useState("");
  const [siteId, setSiteId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enrollment, setEnrollment] = useState<EnrollmentCode | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null);

  useEffect(() => {
    if (!siteId && sites.data?.length) setSiteId(sites.data[0].id);
  }, [siteId, sites.data]);

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await agents.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const create = (event: FormEvent) => {
    event.preventDefault();
    void run("create", async () => {
      setEnrollment(await api.createAgent(name.trim(), siteId));
      setName("");
    });
  };

  const now = agents.updatedAt ?? Date.now();
  const columns: Column<AgentInfo>[] = [
    {
      key: "status",
      header: "Situação",
      render: (a) => {
        const status = agentStatus(a);
        return <Badge tone={status.tone}>{status.label}</Badge>;
      },
    },
    {
      key: "name",
      header: "Agente",
      render: (a) => (
        <>
          {a.name}
          {a.hostname && <span className="secondary"> · {a.hostname}</span>}
        </>
      ),
    },
    { key: "site", header: "Local", render: (a) => a.site_name },
    { key: "seen", header: "Último contato", data: true, render: (a) => formatAgo(a.last_seen_at, now) },
    { key: "version", header: "Versão", data: true, render: (a) => a.version ?? "—" },
    {
      key: "actions",
      header: "Ações",
      render: (a) =>
        confirmRevoke === a.id ? (
          <span className="row-actions">
            <Button size="sm" variant="danger" disabled={busy !== null} onClick={() => run(a.id, async () => {
              await api.revokeAgent(a.id);
              setConfirmRevoke(null);
            })}>
              Confirmar revogação
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirmRevoke(null)}>
              Cancelar
            </Button>
          </span>
        ) : (
          <span className="row-actions">
            <Button
              size="sm"
              variant="secondary"
              disabled={busy !== null}
              onClick={() => run(a.id, async () => setEnrollment(await api.newEnrollmentCode(a.id)))}
            >
              {a.status === "active" ? "Trocar credencial" : "Gerar código"}
            </Button>
            {a.status !== "revoked" && (
              <Button size="sm" variant="ghost" onClick={() => setConfirmRevoke(a.id)}>
                Revogar
              </Button>
            )}
          </span>
        ),
    },
  ];

  const siteOptions = (sites.data ?? []).map((s) => ({ value: s.id, label: s.name }));

  return (
    <>
      <div className="page-heading">
        <h1 className="page-title text-display">Agentes</h1>
        <p className="text-small secondary">
          Cada agente roda na rede do cliente, lê as câmeras e envia só ocorrências e métricas.
        </p>
      </div>
      {error && <Callout tone="danger">{error}</Callout>}
      {(agents.error || sites.error) && <Callout tone="danger">Falha ao carregar: {agents.error ?? sites.error}</Callout>}
      {enrollment && <EnrollmentInstructions result={enrollment} onClose={() => setEnrollment(null)} />}

      <Panel title="Novo agente">
        <form className="inline-form" onSubmit={create}>
          <TextField
            id="agent-name"
            label="Nome"
            placeholder="Ex.: Recepção - mini PC"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <SelectField
            id="agent-site"
            label="Local"
            options={siteOptions}
            value={siteId}
            onChange={(event) => setSiteId(event.target.value)}
          />
          <Button type="submit" disabled={busy !== null || !name.trim() || !siteId}>
            {busy === "create" ? "Criando…" : "Criar e gerar código"}
          </Button>
        </form>
      </Panel>

      <Panel title="Agentes cadastrados" meta={agents.data ? `${agents.data.length}` : undefined}>
        <DataTable
          caption="Agentes da organização"
          columns={columns}
          rows={agents.data ?? []}
          rowKey={(a) => a.id}
          empty="Nenhum agente ainda. Crie um acima e rode o comando de ativação no computador que fica junto das câmeras."
        />
      </Panel>
    </>
  );
}
