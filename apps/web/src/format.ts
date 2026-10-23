import type { EquipmentKind, EquipmentStatus, Ownership, Role } from "./api";

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

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export function formatMoney(cents: number | null): string {
  return cents === null ? "—" : money.format(cents / 100);
}

/** "1.500,00", "1500", "R$ 99,9" → centavos. null se vazio; NaN se inválido. */
export function parseMoney(text: string): number | null {
  const clean = text.replace(/R\$|\s/g, "");
  if (!clean) return null;
  // Padrão brasileiro: ponto separa milhar, vírgula separa centavos ("1.500" = mil e quinhentos).
  const normalized = clean.includes(",")
    ? clean.replace(/\./g, "").replace(",", ".")
    : /^\d{1,3}(\.\d{3})+$/.test(clean)
      ? clean.replace(/\./g, "")
      : clean;
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return Number.NaN;
  return Math.round(Number(normalized) * 100);
}

export function centsToInput(cents: number | null): string {
  return cents === null ? "" : (cents / 100).toFixed(2).replace(".", ",");
}

const day = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeZone: "UTC" });

export function formatDay(value: string | null): string {
  return value ? day.format(new Date(`${value}T00:00:00Z`)) : "—";
}

export const KIND_LABELS: Record<EquipmentKind, string> = {
  camera: "Câmera",
  agent_host: "Computador do agente",
  recorder: "Gravador (NVR/DVR)",
  switch: "Switch",
  ups: "Nobreak",
  other: "Outro",
};

export const OWNERSHIP_LABELS: Record<Ownership, string> = {
  client: "Do cliente",
  comodato: "Comodato Alessio",
};

export const EQUIPMENT_STATUS_LABELS: Record<EquipmentStatus, string> = {
  in_use: "Em uso",
  maintenance: "Em manutenção",
  returned: "Devolvido",
  retired: "Baixado",
};
