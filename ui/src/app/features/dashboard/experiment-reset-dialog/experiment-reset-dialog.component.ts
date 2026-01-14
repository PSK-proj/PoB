import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
} from '@angular/core';
import { AsyncPipe, NgIf } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';

import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { MatDividerModule } from '@angular/material/divider';

import { BehaviorSubject, of } from 'rxjs';
import { catchError, finalize, map, take, tap } from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import {
  ExperimentApiService,
  type ExperimentResetResponse,
  type ResetResult,
} from '../../../core/api/experiment-api.service';

@Component({
  standalone: true,
  imports: [
    NgIf,
    AsyncPipe,
    MatDialogModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    MatTableModule,
    MatDividerModule,
  ],
  templateUrl: './experiment-reset-dialog.component.html',
  styleUrl: './experiment-reset-dialog.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ExperimentResetDialogComponent {
  private readonly api = inject(ExperimentApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly ref = inject(MatDialogRef<ExperimentResetDialogComponent>);

  readonly busy$ = new BehaviorSubject<boolean>(false);
  readonly error$ = new BehaviorSubject<string | null>(null);
  readonly response$ = new BehaviorSubject<ExperimentResetResponse | null>(
    null
  );

  readonly cols = ['target', 'id', 'ok', 'detail'] as const;

  readonly failures$ = this.response$.pipe(
    map((r) => (r?.results ?? []).filter((x) => !x.ok))
  );

  close(): void {
    this.ref.close();
  }

  runReset(): void {
    this.error$.next(null);
    this.busy$.next(true);

    this.api
      .resetExperiment()
      .pipe(
        take(1),
        tap((r) => this.response$.next(r)),
        catchError((e: unknown) => {
          this.response$.next(null);
          this.error$.next(this.errMsg(e));
          return of(null);
        }),
        finalize(() => this.busy$.next(false)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe();
  }

  trackByKey(_: number, r: ResetResult): string {
    return `${r.target}:${r.id ?? ''}:${r.ok}:${r.detail ?? ''}`;
  }

  private errMsg(e: unknown): string {
    if (e instanceof HttpErrorResponse) {
      const detail =
        typeof e.error === 'string' ? e.error : JSON.stringify(e.error);
      return `${e.status} ${detail}`;
    }
    return e instanceof Error ? e.message : 'Unknown error';
  }
}
