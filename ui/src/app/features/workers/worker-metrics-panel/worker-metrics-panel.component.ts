import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  Input,
  OnInit,
  inject,
} from '@angular/core';
import { AsyncPipe, DatePipe, NgIf } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';

import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressBarModule } from '@angular/material/progress-bar';

import { BehaviorSubject, of } from 'rxjs';
import { catchError, finalize, take, tap } from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import {
  WorkerDetailsApiService,
  type WorkerMetrics,
} from '../worker-details-api.service';

@Component({
  selector: 'app-worker-metrics-panel',
  standalone: true,
  imports: [
    NgIf,
    AsyncPipe,
    DatePipe,
    MatCardModule,
    MatButtonModule,
    MatSnackBarModule,
    MatProgressBarModule,
  ],
  templateUrl: './worker-metrics-panel.component.html',
  styleUrl: './worker-metrics-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkerMetricsPanelComponent implements OnInit {
  private readonly api = inject(WorkerDetailsApiService);
  private readonly snack = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  @Input({ required: true }) workerId!: string;

  readonly busy$ = new BehaviorSubject<boolean>(false);
  readonly metrics$ = new BehaviorSubject<WorkerMetrics | null>(null);

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.busy$.next(true);

    this.api
      .getMetrics(this.workerId)
      .pipe(
        take(1),
        tap((m) => this.metrics$.next(m)),
        catchError((e) => {
          this.snack.open(`Load metrics failed: ${this.errMsg(e)}`, 'OK', {
            duration: 4000,
          });
          return of(null);
        }),
        finalize(() => this.busy$.next(false)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe();
  }

  reset(): void {
    this.busy$.next(true);

    this.api
      .resetMetrics(this.workerId)
      .pipe(
        take(1),
        tap((r) => {
          this.metrics$.next(r.after);
          this.snack.open('Metrics reset.', 'OK', { duration: 2000 });
        }),
        catchError((e) => {
          this.snack.open(`Reset failed: ${this.errMsg(e)}`, 'OK', {
            duration: 4000,
          });
          return of(null);
        }),
        finalize(() => this.busy$.next(false)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe();
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
