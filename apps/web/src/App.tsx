import { useEffect, useState } from "react";

import { type Camera, type Occurrence, fetchCameras, fetchOccurrences } from "./api";
import { AppHeader, Badge, type BadgeTone, type Column, DataTable, Panel } from "./ui";

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

const dateTime = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" });

function formatDate(value: string | null): string {
  return value ? dateTime.format(new Date(value)) : "—";
}

function formatDuration(start: string, end: string | null, now: number): string {
  const seconds = Math.max(0, Math.round(((end ? Date.parse(end) : now) - Date.parse(start)) / 1000));
  const minutes = Math.floor(seconds / 60);
  if (minutes === 0) return `${seconds} s`;
  const hours = Math.floor(minutes / 60);
  if (hours === 0) return `${minutes} min ${seconds % 60} s`;
  return `${hours} h ${minutes % 60} min`;
}

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

function occurrenceColumns(now: number): Column<Occurrence>[] {
  return [
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
  ];
}

export function App() {
  const [occurrences, setOccurrences] = useState<Occurrence[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [nextOccurrences, nextCameras] = await Promise.all([fetchOccurrences(), fetchCameras()]);
        if (!active) return;
        setOccurrences(nextOccurrences);
        setCameras(nextCameras);
        setError(null);
        setUpdatedAt(Date.now());
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (active) setNow(Date.now());
      }
    };
    void load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const open = occurrences.filter((o) => o.state === "open").length;

  return (
    <div className="page">
      <AppHeader
        section="Segurança"
        aside={
          <span className={error ? "refresh--error" : undefined} aria-live="polite">
            {error
              ? `Falha ao atualizar: ${error}`
              : updatedAt
                ? `Atualizado às ${new Date(updatedAt).toLocaleTimeString("pt-BR")}`
                : "Carregando…"}
          </span>
        }
      />

      <main className="page-main">
        <h1 className="page-title text-display">Central de ocorrências</h1>

        <Panel title="Câmeras" meta={`${cameras.length} cadastrada${cameras.length === 1 ? "" : "s"}`}>
          {cameras.length === 0 ? (
            <p className="secondary">Nenhuma câmera cadastrada.</p>
          ) : (
            <ul className="cameras">
              {cameras.map((camera) => {
                const health = cameraHealth(camera, now);
                return (
                  <li key={camera.id} className="camera">
                    <div className="camera__top">
                      <h3 className="camera__name text-heading">{camera.name}</h3>
                      <Badge tone={health.tone}>{health.label}</Badge>
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
            columns={occurrenceColumns(now)}
            rows={occurrences}
            rowKey={(o) => o.id}
            empty="Nenhuma ocorrência registrada."
          />
        </Panel>
      </main>
    </div>
  );
}
