import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { API_BASE_URL } from '../config/environment.tokens';
import { joinUrl } from '../utils/url';
import type {
  WorkerConfig,
  WorkerConfigPatch,
  WorkerMetrics,
  MetricsResetResponse,
} from '../models/worker.models';
import type { FaultCreate, FaultView } from '../models/faults.models';

@Injectable({ providedIn: 'root' })
export class WorkerApiService {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE_URL);

  config(workerId: string) {
    return this.http.get<WorkerConfig>(
      joinUrl(this.base, `/workers/${encodeURIComponent(workerId)}/config`)
    );
  }

  patchConfig(workerId: string, patch: WorkerConfigPatch) {
    return this.http.patch<WorkerConfig>(
      joinUrl(this.base, `/workers/${encodeURIComponent(workerId)}/config`),
      patch
    );
  }

  metrics(workerId: string) {
    return this.http.get<WorkerMetrics>(
      joinUrl(this.base, `/workers/${encodeURIComponent(workerId)}/metrics`)
    );
  }

  resetMetrics(workerId: string) {
    return this.http.post<MetricsResetResponse>(
      joinUrl(
        this.base,
        `/workers/${encodeURIComponent(workerId)}/metrics/reset`
      ),
      {}
    );
  }

  listFaults(workerId: string) {
    return this.http.get<FaultView[]>(
      joinUrl(this.base, `/workers/${encodeURIComponent(workerId)}/faults`)
    );
  }

  createFault(workerId: string, payload: FaultCreate) {
    return this.http.post<FaultView>(
      joinUrl(this.base, `/workers/${encodeURIComponent(workerId)}/faults`),
      payload
    );
  }

  deleteFault(workerId: string, faultId: string) {
    return this.http.delete(
      joinUrl(
        this.base,
        `/workers/${encodeURIComponent(workerId)}/faults/${encodeURIComponent(
          faultId
        )}`
      )
    );
  }

  clearFaults(workerId: string) {
    return this.http.delete(
      joinUrl(this.base, `/workers/${encodeURIComponent(workerId)}/faults`)
    );
  }
}
