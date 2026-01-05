import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
} from '@angular/core';
import { AsyncPipe, DatePipe, NgIf } from '@angular/common';
import {
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';

import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatExpansionModule } from '@angular/material/expansion';

import { BehaviorSubject, combineLatest, of, timer } from 'rxjs';
import {
  catchError,
  distinctUntilChanged,
  finalize,
  map,
  shareReplay,
  startWith,
  switchMap,
  tap,
} from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { TrafficApiService } from '../../../core/api/traffic-api.service';
import type {
  TrafficStartRequest,
  TrafficStatusResponse,
} from '../../../core/models/traffic.models';
import { ApiHttpError } from '../../../core/api/http.types';

type TrafficForm = FormGroup<{
  rps: FormControl<number>;
  duration_sec: FormControl<number | null>;
  endpoint: FormControl<string>;
  profile: FormControl<string>;
}>;

@Component({
  standalone: true,
  imports: [
    NgIf,
    AsyncPipe,
    DatePipe,
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatChipsModule,
    MatIconModule,
    MatSnackBarModule,
    MatProgressBarModule,
    MatExpansionModule,
  ],
  templateUrl: './traffic-page.component.html',
  styleUrl: './traffic-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TrafficPageComponent {
  private readonly api = inject(TrafficApiService);
  private readonly snack = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  private readonly refresh$ = new BehaviorSubject<void>(undefined);
  private readonly busySubject = new BehaviorSubject<boolean>(false);
  readonly busy$ = this.busySubject.asObservable();

  readonly form: TrafficForm = new FormGroup({
    rps: new FormControl(25, {
      nonNullable: true,
      validators: [
        Validators.required,
        Validators.min(0.1),
        Validators.max(5000),
      ],
    }),
    duration_sec: new FormControl<number | null>(10, {
      validators: [Validators.min(0.1)],
    }),
    endpoint: new FormControl('/request', {
      nonNullable: true,
      validators: [Validators.required, Validators.pattern(/^\/.*/)],
    }),
    profile: new FormControl('constant', { nonNullable: true }),
  });

  readonly status$ = combineLatest([
    timer(0, 1000),
    this.refresh$.pipe(startWith(undefined)),
  ]).pipe(
    switchMap(() =>
      this.api.status().pipe(
        catchError((e: unknown) => {
          this.snack.open(`Traffic status error: ${this.errMsg(e)}`, 'OK', {
            duration: 3500,
          });
          const fallback: TrafficStatusResponse = {
            running: false,
            rps: null,
            duration_sec: null,
            profile: null,
            endpoint: null,
            started_at: null,
            total_sent: 0,
            total_ok: 0,
            total_fail: 0,
            last_error: this.errMsg(e),
          };
          return of(fallback);
        })
      )
    ),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  readonly vm$ = combineLatest([this.status$, this.busy$]).pipe(
    map(([status, busy]) => {
      const inputsDisabled = busy || status.running;
      return {
        status,
        busy,
        canStart: !busy && !status.running,
        canStop: !busy && status.running,
        inputsDisabled,
      };
    }),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  private readonly _syncDisabled = this.vm$
    .pipe(
      map((vm) => vm.inputsDisabled),
      distinctUntilChanged(),
      tap((disabled) => this.syncFormDisabled(disabled)),
      takeUntilDestroyed(this.destroyRef)
    )
    .subscribe();

  refresh(): void {
    this.refresh$.next();
  }

  start(currentStatus: TrafficStatusResponse): void {
    if (currentStatus.running) return;

    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.snack.open('Fix form errors first.', 'OK', { duration: 2500 });
      return;
    }

    const payload = this.buildStartRequest();
    this.busySubject.next(true);

    this.api
      .start(payload)
      .pipe(
        tap(() => this.snack.open('Traffic started', 'OK', { duration: 2000 })),
        catchError((e: unknown) => {
          this.snack.open(`Start failed: ${this.errMsg(e)}`, 'OK', {
            duration: 3500,
          });
          return of(void 0);
        }),
        finalize(() => {
          this.busySubject.next(false);
          this.refresh();
        }),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe();
  }

  stop(currentStatus: TrafficStatusResponse): void {
    if (!currentStatus.running) return;

    this.busySubject.next(true);

    this.api
      .stop()
      .pipe(
        tap(() => this.snack.open('Traffic stopped', 'OK', { duration: 2000 })),
        catchError((e: unknown) => {
          this.snack.open(`Stop failed: ${this.errMsg(e)}`, 'OK', {
            duration: 3500,
          });
          return of(void 0);
        }),
        finalize(() => {
          this.busySubject.next(false);
          this.refresh();
        }),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe();
  }

  private syncFormDisabled(disabled: boolean): void {
    if (disabled) {
      if (!this.form.disabled) this.form.disable({ emitEvent: false });
      return;
    }
    if (this.form.disabled) this.form.enable({ emitEvent: false });
  }

  private buildStartRequest(): TrafficStartRequest {
    const v = this.form.getRawValue();

    const duration =
      v.duration_sec === null || Number.isNaN(v.duration_sec)
        ? null
        : v.duration_sec;

    return {
      rps: v.rps,
      duration_sec: duration,
      endpoint: v.endpoint,
      profile: v.profile,
    };
  }

  private errMsg(e: unknown): string {
    if (e instanceof ApiHttpError) return e.api.message;
    if (e instanceof Error) return e.message;
    return 'Unknown error';
  }
}
