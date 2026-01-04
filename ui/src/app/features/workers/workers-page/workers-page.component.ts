import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
} from '@angular/core';
import { AsyncPipe, DatePipe, DecimalPipe, NgIf } from '@angular/common';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import type { ThemePalette } from '@angular/material/core';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import { BehaviorSubject, combineLatest, from, of } from 'rxjs';
import {
  catchError,
  finalize,
  map,
  mergeMap,
  shareReplay,
  startWith,
  toArray,
} from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { StateStreamService } from '../../../core/realtime/state-stream.service';
import { WorkerApiService } from '../../../core/api/worker-api.service';
import { WeightsApiService } from '../../../core/api/weights-api.service';
import type { WorkerView, WeightMode } from '../../../core/models/lb.models';
import { ApiHttpError } from '../../../core/api/http.types';

type StatusFilter = 'all' | 'online' | 'offline' | 'error';

type BulkResult =
  | { id: string; ok: true }
  | { id: string; ok: false; error: string };

type WorkerFilters = {
  search: string;
  status: StatusFilter;
};

@Component({
  standalone: true,
  imports: [
    NgIf,
    AsyncPipe,
    DatePipe,
    DecimalPipe,
    RouterLink,
    ReactiveFormsModule,
    MatCardModule,
    MatTableModule,
    MatCheckboxModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
    MatProgressBarModule,
    MatTooltipModule,
  ],
  templateUrl: './workers-page.component.html',
  styleUrl: './workers-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkersPageComponent {
  private readonly stream = inject(StateStreamService);
  private readonly workerApi = inject(WorkerApiService);
  private readonly weightsApi = inject(WeightsApiService);
  private readonly snack = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  readonly searchCtrl = new FormControl<string>('', { nonNullable: true });
  readonly statusFilterCtrl = new FormControl<StatusFilter>('all', {
    nonNullable: true,
  });

  private readonly busySubject = new BehaviorSubject<boolean>(false);
  readonly busy$ = this.busySubject.asObservable();

  private readonly selectedSubject = new BehaviorSubject<Set<string>>(
    new Set()
  );
  readonly selected$ = this.selectedSubject.asObservable();

  private readonly manualWeightCtrls = new Map<
    string,
    FormControl<number | null>
  >();
  private readonly editingManualWeight = new Set<string>();

  readonly cols = [
    'select',
    'id',
    'status',
    'effWeight',
    'assignedPct',
    'okFail',
    'lat',
    'lastSeen',
    'err',
    'manualWeightActions',
    'actions',
  ] as const;

  readonly trackByWorkerId = (_: number, w: WorkerView): string => w.id;

  private readonly filters$ = combineLatest([
    this.searchCtrl.valueChanges.pipe(startWith(this.searchCtrl.value)),
    this.statusFilterCtrl.valueChanges.pipe(
      startWith(this.statusFilterCtrl.value)
    ),
  ]).pipe(
    map(
      ([search, status]): WorkerFilters => ({
        search: search.trim().toLowerCase(),
        status,
      })
    ),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  readonly vm$ = combineLatest([
    this.stream.state$,
    this.selected$,
    this.busy$,
    this.filters$,
  ]).pipe(
    map(([state, selected, busy, filters]) => {
      const mode = this.normalizeWeightMode(state.weight_mode);
      const workers = this.applyFilters(state.workers, filters);

      const allowed = new Set(workers.map((w) => w.id));
      const cleaned = new Set([...selected].filter((id) => allowed.has(id)));
      if (cleaned.size !== selected.size) this.selectedSubject.next(cleaned);

      const selectedCount = cleaned.size;
      const allCount = workers.length;
      const allSelected = allCount > 0 && selectedCount === allCount;

      return {
        mode,
        manualMode: mode === 'manual',
        workers,
        busy,
        selectedCount,
        allCount,
        allSelected,
        canBulk: !busy && selectedCount > 0,
      };
    }),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  getSelectedIds(): string[] {
    return [...this.selectedSubject.value];
  }

  clearSelection(): void {
    this.selectedSubject.next(new Set());
  }

  toggleAll(workers: WorkerView[], checked: boolean): void {
    const next = new Set(this.selectedSubject.value);

    if (checked) {
      for (const w of workers) next.add(w.id);
    } else {
      for (const w of workers) next.delete(w.id);
    }

    this.selectedSubject.next(next);
  }

  toggleOne(id: string, checked: boolean): void {
    const next = new Set(this.selectedSubject.value);

    if (checked) next.add(id);
    else next.delete(id);

    this.selectedSubject.next(next);
  }

  isSelected(id: string): boolean {
    return this.selectedSubject.value.has(id);
  }

  chipColorForWorker(worker: WorkerView): ThemePalette | null {
    return worker.online ? 'primary' : 'warn';
  }

  manualWeightDisabled(mode: WeightMode, busy: boolean): boolean {
    return busy || mode !== 'manual';
  }

  manualWeightTooltip(mode: WeightMode): string {
    return mode === 'manual' ? '' : 'Switch LB to manual mode on Dashboard';
  }

  onManualWeightFocus(workerId: string): void {
    this.editingManualWeight.add(workerId);
  }

  onManualWeightBlur(workerId: string): void {
    this.editingManualWeight.delete(workerId);
  }

  getManualWeightCtrl(worker: WorkerView): FormControl<number | null> {
    const id = worker.id;

    let ctrl = this.manualWeightCtrls.get(id);
    if (!ctrl) {
      ctrl = new FormControl<number | null>(worker.manual_weight ?? null, {
        validators: [Validators.min(1), Validators.max(1000)],
      });
      this.manualWeightCtrls.set(id, ctrl);
      return ctrl;
    }

    const isEditing = this.editingManualWeight.has(id);
    const canSync = !isEditing && !ctrl.dirty;

    if (canSync) {
      const nextValue = worker.manual_weight ?? null;
      if (ctrl.value !== nextValue)
        ctrl.setValue(nextValue, { emitEvent: false });
    }

    return ctrl;
  }

  setManualWeight(worker: WorkerView, mode: WeightMode): void {
    if (mode !== 'manual') {
      this.snack.open('Switch LB to manual mode first.', 'OK', {
        duration: 2500,
      });
      return;
    }

    const ctrl = this.getManualWeightCtrl(worker);
    if (ctrl.invalid) {
      ctrl.markAsTouched();
      this.snack.open('Manual weight must be 1..1000.', 'OK', {
        duration: 2500,
      });
      return;
    }

    const value = ctrl.value;
    if (value == null) {
      this.snack.open('Enter a manual weight or use Clear.', 'OK', {
        duration: 2500,
      });
      return;
    }

    this.busySubject.next(true);

    this.weightsApi
      .setManualWeight(worker.id, value)
      .pipe(
        map(() => {
          ctrl.markAsPristine();
          this.snack.open(`Manual weight set for ${worker.id}`, 'OK', {
            duration: 2000,
          });
        }),
        catchError((e: unknown) => {
          this.snack.open(`Set manual weight failed: ${this.errMsg(e)}`, 'OK', {
            duration: 3500,
          });
          return of(void 0);
        }),
        finalize(() => this.busySubject.next(false)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe();
  }

  clearManualWeight(worker: WorkerView, mode: WeightMode): void {
    if (mode !== 'manual') {
      this.snack.open('Switch LB to manual mode first.', 'OK', {
        duration: 2500,
      });
      return;
    }

    this.busySubject.next(true);

    this.weightsApi
      .clearManualWeight(worker.id)
      .pipe(
        map(() => {
          const ctrl = this.getManualWeightCtrl(worker);
          ctrl.setValue(null, { emitEvent: false });
          ctrl.markAsPristine();
          this.snack.open(`Manual weight cleared for ${worker.id}`, 'OK', {
            duration: 2000,
          });
        }),
        catchError((e: unknown) => {
          this.snack.open(
            `Clear manual weight failed: ${this.errMsg(e)}`,
            'OK',
            { duration: 3500 }
          );
          return of(void 0);
        }),
        finalize(() => this.busySubject.next(false)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe();
  }

  bulkResetMetrics(ids: string[]): void {
    if (ids.length === 0) return;

    this.busySubject.next(true);

    from(ids)
      .pipe(
        mergeMap(
          (id) =>
            this.workerApi.resetMetrics(id).pipe(
              map((): BulkResult => ({ id, ok: true })),
              catchError((e: unknown) =>
                of<BulkResult>({ id, ok: false, error: this.errMsg(e) })
              )
            ),
          4
        ),
        toArray(),
        finalize(() => this.busySubject.next(false)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe((results: BulkResult[]) =>
        this.reportBulk('Reset metrics', results)
      );
  }

  bulkClearFaults(ids: string[]): void {
    if (ids.length === 0) return;

    this.busySubject.next(true);

    from(ids)
      .pipe(
        mergeMap(
          (id) =>
            this.workerApi.clearFaults(id).pipe(
              map((): BulkResult => ({ id, ok: true })),
              catchError((e: unknown) =>
                of<BulkResult>({ id, ok: false, error: this.errMsg(e) })
              )
            ),
          4
        ),
        toArray(),
        finalize(() => this.busySubject.next(false)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe((results: BulkResult[]) =>
        this.reportBulk('Clear faults', results)
      );
  }

  private reportBulk(label: string, results: BulkResult[]): void {
    const okCount = results.filter((r) => r.ok).length;
    const failCount = results.length - okCount;

    if (failCount === 0) {
      this.snack.open(`${label}: OK (${okCount}/${results.length})`, 'OK', {
        duration: 2500,
      });
      return;
    }

    const failed = results.filter(
      (r): r is Extract<BulkResult, { ok: false }> => !r.ok
    );
    const sample = failed
      .slice(0, 2)
      .map((f) => `${f.id}: ${f.error}`)
      .join(' • ');
    this.snack.open(
      `${label}: ${okCount} ok, ${failCount} failed. ${sample}`,
      'OK',
      { duration: 6500 }
    );
  }

  private applyFilters(
    workers: WorkerView[],
    filters: WorkerFilters
  ): WorkerView[] {
    let out = workers;

    if (filters.search) {
      const s = filters.search;
      out = out.filter(
        (w) => w.id.toLowerCase().includes(s) || w.url.toLowerCase().includes(s)
      );
    }

    switch (filters.status) {
      case 'online':
        out = out.filter((w) => w.online);
        break;
      case 'offline':
        out = out.filter((w) => !w.online);
        break;
      case 'error':
        out = out.filter((w) => !!w.last_error);
        break;
      case 'all':
      default:
        break;
    }

    return out;
  }

  private normalizeWeightMode(raw: string): WeightMode {
    return raw === 'auto' ? 'auto' : 'manual';
  }

  private errMsg(e: unknown): string {
    if (e instanceof ApiHttpError) return e.api.message;
    if (e instanceof Error) return e.message;
    return 'Unknown error';
  }
}
