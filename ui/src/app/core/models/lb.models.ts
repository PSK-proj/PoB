export type WeightMode = 'manual' | 'auto';

export interface HealthResponse {
  status: 'ok';
  service: string;
}

export interface WorkerView {
  id: string;
  url: string;
  online: boolean;

  reported_weight: number;
  manual_weight: number | null;
  auto_weight: number | null;
  effective_weight: number;

  assigned: number;
  assigned_pct: number;

  ok: number;
  fail: number;
  avg_latency_ms: number;

  last_error: string | null;
  last_seen: number | null;
}

export interface LbStateView {
  weight_mode: WeightMode;
  total_assigned: number;
  total_ok: number;
  total_fail: number;
  workers: WorkerView[];
}

export interface LbResponse {
  chosen_worker: string;
  attempt: number;
  worker_status: number;
  lb_forward_ms: number;
  worker_body: unknown;
}

export function isRawBody(x: unknown): x is { raw: string } {
  return (
    !!x &&
    typeof x === 'object' &&
    'raw' in x &&
    typeof (x as any).raw === 'string'
  );
}

export interface StateStreamMessage {
  type: 'state';
  payload: LbStateView;
}
