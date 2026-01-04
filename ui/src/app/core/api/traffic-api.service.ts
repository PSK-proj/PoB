import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { API_BASE_URL } from '../config/environment.tokens';
import { joinUrl } from '../utils/url';
import type {
  TrafficStartRequest,
  TrafficStatusResponse,
} from '../models/traffic.models';

@Injectable({ providedIn: 'root' })
export class TrafficApiService {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE_URL);

  start(req: TrafficStartRequest) {
    return this.http.post(joinUrl(this.base, '/traffic/start'), req);
  }

  stop() {
    return this.http.post(joinUrl(this.base, '/traffic/stop'), {});
  }

  status() {
    return this.http.get<TrafficStatusResponse>(
      joinUrl(this.base, '/traffic/status')
    );
  }
}
