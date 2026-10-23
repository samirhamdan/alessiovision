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

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export const fetchOccurrences = () => get<Occurrence[]>("/api/v1/occurrences?limit=100");
export const fetchCameras = () => get<Camera[]>("/api/v1/cameras");
