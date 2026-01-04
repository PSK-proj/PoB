import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { API_BASE_URL } from '../config/environment.tokens';
import { joinUrl } from '../utils/url';
import type { WeightMode } from '../models/lb.models';

@Injectable({ providedIn: 'root' })
export class WeightsApiService {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE_URL);

  getMode() {
    return this.http.get<{ mode: WeightMode }>(
      joinUrl(this.base, '/lb/weight-mode')
    );
  }

  setMode(mode: WeightMode) {
    return this.http.post<{ ok: true; mode: WeightMode }>(
      joinUrl(this.base, '/lb/weight-mode'),
      { mode }
    );
  }

  setManualWeight(workerId: string, weight: number) {
    return this.http.patch<{
      ok: true;
      worker_id: string;
      manual_weight: number;
      effective_weight: number;
    }>(
      joinUrl(
        this.base,
        `/workers/${encodeURIComponent(workerId)}/manual-weight`
      ),
      { weight }
    );
  }

  clearManualWeight(workerId: string) {
    return this.http.delete<{
      ok: true;
      worker_id: string;
      manual_weight: null;
      effective_weight: number;
    }>(
      joinUrl(
        this.base,
        `/workers/${encodeURIComponent(workerId)}/manual-weight`
      )
    );
  }
}
