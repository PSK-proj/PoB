import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map } from 'rxjs';

export type ResetTarget = 'clientgen' | 'worker' | 'lb' | 'unknown';

export type ResetResult = {
  target: ResetTarget;
  id?: string | null;
  ok: boolean;
  detail?: string | null;
  rawTarget?: string | null;
};

export type ExperimentResetResponse = {
  ok: boolean;
  results: ResetResult[];
};

type RawResetResult = {
  target: string;
  id?: string | null;
  ok: boolean;
  detail?: string | null;
};

type RawExperimentResetResponse = {
  ok: boolean;
  results: RawResetResult[];
};

function toTarget(t: string): ResetTarget {
  if (t === 'clientgen' || t === 'worker' || t === 'lb') return t;
  return 'unknown';
}

@Injectable({ providedIn: 'root' })
export class ExperimentApiService {
  private readonly http = inject(HttpClient);

  resetExperiment(): Observable<ExperimentResetResponse> {
    return this.http
      .post<RawExperimentResetResponse>('/experiment/reset', {})
      .pipe(
        map((raw) => {
          const results = Array.isArray(raw?.results) ? raw.results : [];
          return {
            ok: Boolean(raw?.ok),
            results: results.map((r) => ({
              target: toTarget(String(r.target)),
              rawTarget: r.target ?? null,
              id: r.id ?? null,
              ok: Boolean(r.ok),
              detail: r.detail ?? null,
            })),
          };
        })
      );
  }
}
