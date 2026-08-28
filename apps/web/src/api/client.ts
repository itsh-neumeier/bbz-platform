/**
 * Thin API client. Every write will carry the command envelope (command_id,
 * expected_version, client_id, workplace_id) once write endpoints exist in
 * Phase 1 — mirrors bbz_core.api.idempotency. Foundation phase: reads only.
 */

export interface Meta {
  service: string;
  version: string;
  api_version: string;
  environment: string;
  node_id: string;
  capabilities: string[];
  known_integrations: string[];
}

export async function getMeta(fetchImpl: typeof fetch = fetch): Promise<Meta> {
  const res = await fetchImpl('/api/v1/meta');
  if (!res.ok) throw new Error(`meta failed: ${res.status}`);
  return (await res.json()) as Meta;
}

export interface ClusterStatus {
  stub: boolean;
  dcs: string;
  control_leader: string | null;
  nodes: { node_id: string; app_state: string; db_role: string }[];
  last_event_seq: number | null;
}

export async function getClusterStatus(fetchImpl: typeof fetch = fetch): Promise<ClusterStatus> {
  const res = await fetchImpl('/cluster/status');
  if (!res.ok) throw new Error(`cluster status failed: ${res.status}`);
  return (await res.json()) as ClusterStatus;
}
