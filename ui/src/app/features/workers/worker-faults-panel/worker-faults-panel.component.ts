import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  Input,
  OnInit,
  inject,
} from '@angular/core';
import { AsyncPipe, DatePipe, NgIf } from '@angular/common';
import {
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTableModule } from '@angular/material/table';

import { BehaviorSubject, Observable, Subject, of } from 'rxjs';
import {
  catchError,
  finalize,
  startWith,
  switchMap,
  take,
  tap,
} from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import {
  WorkerDetailsApiService,
  type FaultCreate,
  type FaultView,
} from '../worker-details-api.service';

type Kind = FaultCreate['kind'];

type BaseForm = {
  kind: FormControl<Kind>;
  probability: FormControl<number>;
  duration_sec: FormControl<number | null>;
};

type DelayForm = BaseForm & {
  delay_ms: FormControl<number>;
};

type DropForm = BaseForm & {
  mode: FormControl<'503' | 'timeout'>;
  status_code: FormControl<number>;
  sleep_ms: FormControl<number>;
};

type CorruptForm = BaseForm & {
  corrupt_mode: FormControl<'invalid_json' | 'bad_fields'>;
};

type ErrorForm = BaseForm & {
  error_status_code: FormControl<number>;
  message: FormControl<string>;
};

type CpuBurnForm = BaseForm & {
  burn_ms: FormControl<number>;
};

@Component({
  selector: 'app-worker-faults-panel',
  standalone: true,
  imports: [
    NgIf,
    AsyncPipe,
    DatePipe,
    ReactiveFormsModule,
    MatCardModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
    MatProgressBarModule,
    MatTableModule,
  ],
  templateUrl: './worker-faults-panel.component.html',
  styleUrl: './worker-faults-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkerFaultsPanelComponent implements OnInit {
  private readonly api = inject(WorkerDetailsApiService);
  private readonly snack = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  @Input({ required: true }) workerId!: string;

  private readonly refreshSubject = new Subject<void>();
  readonly busy$ = new BehaviorSubject<boolean>(false);

  readonly faults$: Observable<FaultView[]> = this.refreshSubject.pipe(
    startWith(void 0),
    tap(() => this.busy$.next(true)),
    switchMap(() =>
      this.api.listFaults(this.workerId).pipe(
        catchError((e: unknown) => {
          this.snack.open(`Load faults failed: ${this.errMsg(e)}`, 'OK', {
            duration: 4000,
          });
          return of<FaultView[]>([]);
        }),
        finalize(() => this.busy$.next(false))
      )
    ),
    startWith<FaultView[]>([])
  );

  readonly cols = [
    'id',
    'kind',
    'created',
    'expires',
    'spec',
    'actions',
  ] as const;

  readonly form = new FormGroup<
    DelayForm & DropForm & CorruptForm & ErrorForm & CpuBurnForm
  >({
    kind: new FormControl<Kind>('delay', { nonNullable: true }),
    probability: new FormControl<number>(1, {
      nonNullable: true,
      validators: [Validators.min(0), Validators.max(1)],
    }),
    duration_sec: new FormControl<number | null>(null, {
      validators: [Validators.min(0.1)],
    }),

    delay_ms: new FormControl<number>(0, {
      nonNullable: true,
      validators: [Validators.min(0), Validators.max(60000)],
    }),

    mode: new FormControl<'503' | 'timeout'>('503', { nonNullable: true }),
    status_code: new FormControl<number>(503, {
      nonNullable: true,
      validators: [Validators.min(400), Validators.max(599)],
    }),
    sleep_ms: new FormControl<number>(5000, {
      nonNullable: true,
      validators: [Validators.min(1), Validators.max(600000)],
    }),

    corrupt_mode: new FormControl<'invalid_json' | 'bad_fields'>(
      'invalid_json',
      { nonNullable: true }
    ),

    error_status_code: new FormControl<number>(500, {
      nonNullable: true,
      validators: [Validators.min(400), Validators.max(599)],
    }),
    message: new FormControl<string>('fault: error', {
      nonNullable: true,
      validators: [Validators.maxLength(2000)],
    }),

    burn_ms: new FormControl<number>(50, {
      nonNullable: true,
      validators: [Validators.min(1), Validators.max(60000)],
    }),
  });

  ngOnInit(): void {
    this.refresh();
    this.faults$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe();
  }

  refresh(): void {
    this.refreshSubject.next();
  }

  add(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.snack.open('Fix validation errors.', 'OK', { duration: 2500 });
      return;
    }

    const payload = this.buildPayload();
    this.busy$.next(true);

    this.api
      .addFault(this.workerId, payload)
      .pipe(
        take(1),
        tap(() => this.snack.open('Fault added.', 'OK', { duration: 2000 })),
        catchError((e: unknown) => {
          this.snack.open(`Add fault failed: ${this.errMsg(e)}`, 'OK', {
            duration: 4000,
          });
          return of(null);
        }),
        finalize(() => this.busy$.next(false)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe(() => this.refresh());
  }

  delete(faultId: string): void {
    this.busy$.next(true);

    this.api
      .deleteFault(this.workerId, faultId)
      .pipe(
        take(1),
        tap(() => this.snack.open('Fault deleted.', 'OK', { duration: 2000 })),
        catchError((e: unknown) => {
          this.snack.open(`Delete failed: ${this.errMsg(e)}`, 'OK', {
            duration: 4000,
          });
          return of(null);
        }),
        finalize(() => this.busy$.next(false)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe(() => this.refresh());
  }

  clearAll(): void {
    this.busy$.next(true);

    this.api
      .clearFaults(this.workerId)
      .pipe(
        take(1),
        tap((r) =>
          this.snack.open(`Cleared: ${r.cleared}`, 'OK', { duration: 2500 })
        ),
        catchError((e: unknown) => {
          this.snack.open(`Clear failed: ${this.errMsg(e)}`, 'OK', {
            duration: 4000,
          });
          return of(null);
        }),
        finalize(() => this.busy$.next(false)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe(() => this.refresh());
  }

  isKind(kind: Kind, expected: Kind): boolean {
    return kind === expected;
  }

  specText(spec: Record<string, unknown>): string {
    try {
      return JSON.stringify(spec);
    } catch {
      return '[unserializable]';
    }
  }

  private buildPayload(): FaultCreate {
    const v = this.form.getRawValue();
    const duration = v.duration_sec ?? undefined;

    if (v.kind === 'delay') {
      return {
        kind: 'delay',
        delay_ms: v.delay_ms,
        probability: v.probability,
        duration_sec: duration,
      };
    }

    if (v.kind === 'drop') {
      return {
        kind: 'drop',
        mode: v.mode,
        status_code: v.status_code,
        sleep_ms: v.sleep_ms,
        probability: v.probability,
        duration_sec: duration,
      };
    }

    if (v.kind === 'corrupt') {
      return {
        kind: 'corrupt',
        mode: v.corrupt_mode,
        probability: v.probability,
        duration_sec: duration,
      };
    }

    if (v.kind === 'error') {
      return {
        kind: 'error',
        status_code: v.error_status_code,
        message: v.message,
        probability: v.probability,
        duration_sec: duration,
      };
    }

    return {
      kind: 'cpu_burn',
      burn_ms: v.burn_ms,
      probability: v.probability,
      duration_sec: duration,
    };
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
