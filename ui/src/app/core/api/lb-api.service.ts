import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { API_BASE_URL } from '../config/environment.tokens';
import { joinUrl } from '../utils/url';
import type {
  HealthResponse,
  LbResponse,
  LbStateView,
  WorkerView,
} from '../models/lb.models';

@Injectable({ providedIn: 'root' })
export class LbApiService {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE_URL);

  health() {
    return this.http.get<HealthResponse>(joinUrl(this.base, '/health'));
  }
  workers() {
    return this.http.get<WorkerView[]>(joinUrl(this.base, '/workers'));
  }
  state() {
    return this.http.get<LbStateView>(joinUrl(this.base, '/state'));
  }

  request(payload?: Record<string, unknown>) {
    return payload
      ? this.http.post<LbResponse>(joinUrl(this.base, '/request'), { payload })
      : this.http.post<LbResponse>(joinUrl(this.base, '/request'), {});
  }
}
