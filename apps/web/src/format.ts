import type { Role } from "./api";

const dateTime = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" });

export function formatDate(value: string | null): string {
  return value ? dateTime.format(new Date(value)) : "—";
}

export function formatDuration(start: string, end: string | null, now: number): string {
  const seconds = Math.max(0, Math.round(((end ? Date.parse(end) : now) - Date.parse(start)) / 1000));
  const minutes = Math.floor(seconds / 60);
  if (minutes === 0) return `${seconds} s`;
  const hours = Math.floor(minutes / 60);
  if (hours === 0) return `${minutes} min ${seconds % 60} s`;
  return `${hours} h ${minutes % 60} min`;
}

export function formatAgo(value: string | null, now: number): string {
  if (!value) return "nunca";
  const seconds = Math.max(0, Math.round((now - Date.parse(value)) / 1000));
  if (seconds < 60) return `há ${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `há ${hours} h`;
  return formatDate(value);
}

export const ROLE_LABELS: Record<Role, string> = {
  owner: "Proprietário",
  admin: "Administrador",
  operator: "Operador",
  viewer: "Leitor",
};

export const ROLE_HINTS: Record<Role, string> = {
  owner: "Tudo, inclusive gerenciar outros proprietários.",
  admin: "Gerencia agentes, locais e membros.",
  operator: "Acompanha e reconhece ocorrências.",
  viewer: "Só consulta ocorrências e câmeras.",
};
