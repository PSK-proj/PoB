export interface WorkerConfig {
  base_lat_ms: number;
  jitter_ms: number;
  capacity: number;
  weight: number;
}

export interface WorkerConfigPatch {
  base_lat_ms?: number | null;
  jitter_ms?: number | null;
  capacity?: number | null;
  weight?: number | null;
}

export interface WorkerMetrics {
  worker_id: string;
  inflight: number;
  total: number;
  ok: number;
  fail: number;
  last_error?: string | null;
  last_simulated_ms?: number | null;
  last_completed_at?: number | null;
}

export interface MetricsResetResponse {
  before: WorkerMetrics;
  after: WorkerMetrics;
}
