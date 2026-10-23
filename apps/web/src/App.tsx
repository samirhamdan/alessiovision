import { useEffect, useState } from "react";

import { type Camera, type Occurrence, fetchCameras, fetchOccurrences } from "./api";

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

function cameraHealth(camera: Camera, now: number): { label: string; tone: string } {
  if (!camera.last_status_at) return { label: "Aguardando agente", tone: "muted" };
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
      return { label: "Desconhecido", tone: "muted" };
  }
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
      <header className="header">
        <div>
          <h1>ALESSIO</h1>
          <p className="subtitle">Central de ocorrências</p>
        </div>
        <p className="refresh" aria-live="polite">
          {error
            ? `Falha ao atualizar: ${error}`
            : updatedAt
              ? `Atualizado às ${new Date(updatedAt).toLocaleTimeString("pt-BR")}`
              : "Carregando…"}
        </p>
      </header>

      <section aria-labelledby="cameras-title">
        <h2 id="cameras-title">Câmeras</h2>
        {cameras.length === 0 ? (
          <p className="empty">Nenhuma câmera cadastrada.</p>
        ) : (
          <ul className="cameras">
            {cameras.map((camera) => {
              const health = cameraHealth(camera, now);
              return (
                <li key={camera.id} className="camera">
                  <div className="camera-name">{camera.name}</div>
                  <span className={`badge badge-${health.tone}`}>{health.label}</span>
                  <div className="camera-meta">
                    Último quadro analisado: {formatDate(camera.last_frame_at)}
                    {camera.status_detail ? ` · ${camera.status_detail}` : ""}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="occurrences-title">
        <h2 id="occurrences-title">
          Ocorrências <span className="count">{open > 0 ? `${open} em andamento` : "nenhuma em andamento"}</span>
        </h2>
        {occurrences.length === 0 ? (
          <p className="empty">Nenhuma ocorrência registrada.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Situação</th>
                  <th>Tipo</th>
                  <th>Câmera / zona</th>
                  <th>Início</th>
                  <th>Duração</th>
                  <th className="num">Pessoas (máx.)</th>
                  <th>Encerramento</th>
                </tr>
              </thead>
              <tbody>
                {occurrences.map((o) => (
                  <tr key={o.id}>
                    <td>
                      <span className={`badge ${o.state === "open" ? "badge-danger" : "badge-muted"}`}>
                        {o.state === "open" ? "Em andamento" : "Encerrada"}
                      </span>
                    </td>
                    <td>{EVENT_LABELS[o.event_type] ?? o.event_type}</td>
                    <td>
                      {o.camera_name}
                      <span className="secondary"> / {o.zone_name}</span>
                    </td>
                    <td>{formatDate(o.started_at)}</td>
                    <td>{formatDuration(o.started_at, o.ended_at, now)}</td>
                    <td className="num">{o.max_people}</td>
                    <td>{o.close_reason ? CLOSE_LABELS[o.close_reason] : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
