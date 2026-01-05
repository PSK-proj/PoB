import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type WorkerConfig = {
  base_lat_ms: number;
  jitter_ms: number;
  capacity: number;
  weight: number;
};

export type WorkerConfigPatch = Partial<WorkerConfig>;

export type WorkerMetrics = {
  worker_id: string;
  inflight: number;
  total: number;
  ok: number;
  fail: number;
  last_error?: string | null;
  last_simulated_ms?: number | null;
  last_completed_at?: number | null;
};

export type MetricsResetResponse = {
  before: WorkerMetrics;
  after: WorkerMetrics;
};

export type FaultView = {
  id: string;
  kind: string;
  created_at: number;
  expires_at?: number | null;
  spec: Record<string, unknown>;
};

export type FaultCreate =
  | {
      kind: 'delay';
      delay_ms: number;
      probability: number;
      duration_sec?: number | null;
    }
  | {
      kind: 'drop';
      mode: '503' | 'timeout';
      status_code: number;
      sleep_ms: number;
      probability: number;
      duration_sec?: number | null;
    }
  | {
      kind: 'corrupt';
      mode: 'invalid_json' | 'bad_fields';
      probability: number;
      duration_sec?: number | null;
    }
  | {
      kind: 'cpu_burn';
      burn_ms: number;
      probability: number;
      duration_sec?: number | null;
    }
  | {
      kind: 'error';
      status_code: number;
      message: string;
      probability: number;
      duration_sec?: number | null;
    };

@Injectable({ providedIn: 'root' })
export class WorkerDetailsApiService {
  private readonly http = inject(HttpClient);

  getConfig(workerId: string): Observable<WorkerConfig> {
    return this.http.get<WorkerConfig>(
      `/workers/${encodeURIComponent(workerId)}/config`
    );
  }

  patchConfig(
    workerId: string,
    patch: WorkerConfigPatch
  ): Observable<WorkerConfig> {
    return this.http.patch<WorkerConfig>(
      `/workers/${encodeURIComponent(workerId)}/config`,
      patch
    );
  }

  getMetrics(workerId: string): Observable<WorkerMetrics> {
    return this.http.get<WorkerMetrics>(
      `/workers/${encodeURIComponent(workerId)}/metrics`
    );
  }

  resetMetrics(workerId: string): Observable<MetricsResetResponse> {
    return this.http.post<MetricsResetResponse>(
      `/workers/${encodeURIComponent(workerId)}/metrics/reset`,
      {}
    );
  }

  listFaults(workerId: string): Observable<FaultView[]> {
    return this.http.get<FaultView[]>(
      `/workers/${encodeURIComponent(workerId)}/faults`
    );
  }

  addFault(workerId: string, payload: FaultCreate): Observable<FaultView> {
    return this.http.post<FaultView>(
      `/workers/${encodeURIComponent(workerId)}/faults`,
      payload
    );
  }

  deleteFault(
    workerId: string,
    faultId: string
  ): Observable<{ ok: boolean; fault_id: string }> {
    return this.http.delete<{ ok: boolean; fault_id: string }>(
      `/workers/${encodeURIComponent(workerId)}/faults/${encodeURIComponent(
        faultId
      )}`
    );
  }

  clearFaults(workerId: string): Observable<{ ok: boolean; cleared: number }> {
    return this.http.delete<{ ok: boolean; cleared: number }>(
      `/workers/${encodeURIComponent(workerId)}/faults`
    );
  }
}
