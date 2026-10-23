export type Role = "owner" | "admin" | "operator" | "viewer";

export type Membership = { organization_id: string; organization_name: string; role: Role };

export type Me = {
  id: string;
  email: string;
  name: string;
  active_organization_id: string | null;
  role: Role | null;
  permissions: string[];
  memberships: Membership[];
};

export type Occurrence = {
  id: string;
  camera_id: string;
  camera_name: string;
  zone_id: string;
  zone_name: string;
  event_type: string;
  is_shadow: boolean;
  state: "open" | "closed";
  review_status: "new" | "acknowledged" | "resolved";
  reviewed_at: string | null;
  started_at: string;
  ended_at: string | null;
  last_observed_at: string;
  close_reason: "cleared" | "schedule" | "signal_lost" | "shutdown" | null;
  max_people: number;
  max_confidence: number;
};

export type Camera = {
  id: string;
  name: string;
  status: "unknown" | "connected" | "disconnected" | "error";
  status_detail: string | null;
  last_frame_at: string | null;
  last_status_at: string | null;
  agent_last_seen_at: string | null;
};

export type Site = { id: string; name: string; timezone: string };

export type AgentInfo = {
  id: string;
  name: string;
  site_id: string;
  site_name: string;
  status: "pending" | "active" | "revoked";
  version: string | null;
  hostname: string | null;
  enrolled_at: string | null;
  last_seen_at: string | null;
  enrollment_pending: boolean;
};

export type EnrollmentCode = {
  agent: AgentInfo;
  enrollment_code: string;
  enrollment_expires_at: string;
};

export type Member = {
  user_id: string;
  email: string;
  name: string;
  role: Role;
  status: "active" | "invited" | "disabled";
  joined_at: string;
};

export type MemberCreated = {
  member: Member;
  invite_token: string | null;
  invite_expires_at: string | null;
};

export const SESSION_EXPIRED_EVENT = "alessio:session-expired";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function detailMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  // Erros de validação do FastAPI: lista de {msg, loc}.
  if (Array.isArray(detail) && detail.length > 0 && typeof detail[0]?.msg === "string") {
    return detail.map((item) => item.msg).join(" ");
  }
  return `Erro inesperado (${status}). Tente de novo.`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        // Exigido pela API em toda alteração (proteção contra CSRF).
        "X-Alessio-Client": "web",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Sem conexão com o servidor. Verifique a rede e tente de novo.");
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/api/v1/auth/")) {
      // Sessão expirada ou encerrada em outro lugar: o App volta para o login.
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    throw new ApiError(response.status, detailMessage(data?.detail, response.status));
  }
  return data as T;
}

export const api = {
  me: () => request<Me>("GET", "/api/v1/me"),
  login: (email: string, password: string) => request<Me>("POST", "/api/v1/auth/login", { email, password }),
  logout: () => request<void>("POST", "/api/v1/auth/logout"),
  acceptInvite: (token: string, name: string, password: string) =>
    request<Me>("POST", "/api/v1/auth/accept-invite", { token, name, password }),
  switchOrganization: (organizationId: string) =>
    request<Me>("POST", "/api/v1/session/organization", { organization_id: organizationId }),

  occurrences: () => request<Occurrence[]>("GET", "/api/v1/occurrences?limit=100"),
  reviewOccurrence: (id: string, reviewStatus: "acknowledged" | "resolved") =>
    request<Occurrence>("PATCH", `/api/v1/occurrences/${id}/review`, { review_status: reviewStatus }),
  cameras: () => request<Camera[]>("GET", "/api/v1/cameras"),

  sites: () => request<Site[]>("GET", "/api/v1/sites"),
  agents: () => request<AgentInfo[]>("GET", "/api/v1/agents"),
  createAgent: (name: string, siteId: string) =>
    request<EnrollmentCode>("POST", "/api/v1/agents", { name, site_id: siteId }),
  newEnrollmentCode: (id: string) => request<EnrollmentCode>("POST", `/api/v1/agents/${id}/enrollment-code`),
  revokeAgent: (id: string) => request<AgentInfo>("POST", `/api/v1/agents/${id}/revoke`),

  members: () => request<Member[]>("GET", "/api/v1/members"),
  addMember: (email: string, name: string, role: Role) =>
    request<MemberCreated>("POST", "/api/v1/members", { email, name, role }),
  changeRole: (userId: string, role: Role) => request<Member>("PATCH", `/api/v1/members/${userId}`, { role }),
  removeMember: (userId: string) => request<void>("DELETE", `/api/v1/members/${userId}`),
  reissueInvite: (userId: string) => request<MemberCreated>("POST", `/api/v1/members/${userId}/invite`),
};
