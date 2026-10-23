import { useState } from "react";

import { type Camera, type Occurrence, api } from "../api";
import { formatDate, formatDay, formatDuration, SERVICE_LABELS } from "../format";
import { Badge, type BadgeTone, Button, Callout, type Column, DataTable, Panel } from "../ui";
import { useResource } from "../useResource";

const REFRESH_MS = 5000;
// O agente envia heartbeat a cada 30 s; sem notícias por 90 s, o painel avisa.
const AGENT_SILENCE_MS = 90_000;

const EVENT_LABELS: Record<string, string> = {
  "person.after_hours": "Presença fora do horário",
};

const CLOSE_LABELS: Record<string, string> = {
  cleared: "Área liberada",
  schedule: "Início do expediente",
  signal_lost: "Sinal perdido",
  shutdown: "Agente encerrado",
};

function cameraHealth(camera: Camera, now: number): { label: string; tone: BadgeTone } {
  if (!camera.last_status_at) return { label: "Aguardando agente", tone: "neutral" };
  if (now - Date.parse(camera.last_status_at) > AGENT_SILENCE_MS) {
    return { label: "Agente sem contato", tone: "danger" };
  }
  switch (camera.status) {
    case "connected":
      return { label: "Analisando", tone: "ok" };
    case "disconnected":
      return { label: "Sem sinal", tone: "warn" };
    case "error":
      return { label: "Erro", tone: "danger" };
    default:
      return { label: "Desconhecido", tone: "neutral" };
  }
}

export function OccurrencesPage({ canReview }: { canReview: boolean }) {
  const occurrences = useResource(api.occurrences, REFRESH_MS);
  const cameras = useResource(api.cameras, REFRESH_MS);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const now = occurrences.updatedAt ?? Date.now();

  const acknowledge = async (occurrence: Occurrence) => {
    setBusyId(occurrence.id);
    setReviewError(null);
    try {
      await api.reviewOccurrence(occurrence.id, "acknowledged");
      await occurrences.reload();
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  const columns: Column<Occurrence>[] = [
    {
      key: "state",
      header: "Situação",
      render: (o) =>
        o.state === "open" ? <Badge tone="danger">Em andamento</Badge> : <Badge tone="neutral">Encerrada</Badge>,
    },
    { key: "type", header: "Tipo", render: (o) => EVENT_LABELS[o.event_type] ?? o.event_type },
    {
      key: "where",
      header: "Câmera / zona",
      render: (o) => (
        <>
          {o.camera_name}
          <span className="secondary"> / {o.zone_name}</span>
        </>
      ),
    },
    { key: "start", header: "Início", data: true, render: (o) => formatDate(o.started_at) },
    { key: "duration", header: "Duração", data: true, render: (o) => formatDuration(o.started_at, o.ended_at, now) },
    { key: "people", header: "Pessoas (máx.)", align: "end", render: (o) => o.max_people },
    { key: "end", header: "Encerramento", render: (o) => (o.close_reason ? CLOSE_LABELS[o.close_reason] : "—") },
    {
      key: "review",
      header: "Atendimento",
      render: (o) => {
        if (o.review_status === "acknowledged") return <Badge tone="accent">Reconhecida</Badge>;
        if (o.review_status === "resolved") return <Badge tone="neutral">Resolvida</Badge>;
        if (!canReview) return <span className="secondary">Pendente</span>;
        return (
          <Button size="sm" variant="secondary" disabled={busyId === o.id} onClick={() => acknowledge(o)}>
            {busyId === o.id ? "Salvando…" : "Reconhecer"}
          </Button>
        );
      },
    },
  ];

  const list = occurrences.data ?? [];
  const open = list.filter((o) => o.state === "open").length;
  const cameraList = cameras.data ?? [];
  const loadError = occurrences.error ?? cameras.error;

  return (
    <>
      <div className="page-heading">
        <h1 className="page-title text-display">Central de ocorrências</h1>
        <p className="text-small secondary" aria-live="polite">
          {occurrences.updatedAt
            ? `Atualizado às ${new Date(occurrences.updatedAt).toLocaleTimeString("pt-BR")}`
            : "Carregando…"}
        </p>
      </div>
      {loadError && <Callout tone="danger">Falha ao atualizar: {loadError}</Callout>}
      {reviewError && <Callout tone="danger">{reviewError}</Callout>}

      <Panel title="Câmeras" meta={`${cameraList.length} cadastrada${cameraList.length === 1 ? "" : "s"}`}>
        {cameraList.length === 0 ? (
          <p className="secondary flush">Nenhuma câmera cadastrada. Elas aparecem depois que um agente ativo é configurado.</p>
        ) : (
          <ul className="cameras">
            {cameraList.map((camera) => {
              const health = cameraHealth(camera, now);
              return (
                <li key={camera.id} className="camera">
                  <div className="camera__top">
                    <h3 className="camera__name text-heading">{camera.name}</h3>
                    <Badge tone={health.tone}>{health.label}</Badge>
                  </div>
                  <div className="camera__services">
                    {(Object.entries(camera.history_until) as [keyof typeof SERVICE_LABELS, string][]).map(([service, until]) => (
                      <Badge key={`h-${service}`} tone="neutral">
                        {`${SERVICE_LABELS[service]} encerrado · consulta até ${formatDay(until.slice(0, 10))}`}
                      </Badge>
                    ))}
                    {camera.services.length === 0 ? (
                      Object.keys(camera.history_until).length === 0 && <span className="text-small secondary">Sem Vision</span>
                    ) : (
                      camera.services.map((service) => (
                        <Badge key={service} tone="accent">
                          {SERVICE_LABELS[service]}
                        </Badge>
                      ))
                    )}
                  </div>
                  <p className="camera__meta text-small">
                    Último quadro analisado: <span className="text-data">{formatDate(camera.last_frame_at)}</span>
                    {camera.status_detail ? ` · ${camera.status_detail}` : ""}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <Panel title="Ocorrências" meta={open > 0 ? `${open} em andamento` : "nenhuma em andamento"}>
        <DataTable
          caption="Ocorrências de segurança, mais recentes primeiro"
          columns={columns}
          rows={list}
          rowKey={(o) => o.id}
          empty="Nenhuma ocorrência registrada."
        />
      </Panel>
    </>
  );
}
