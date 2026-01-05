import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  Input,
  OnInit,
  inject,
} from '@angular/core';
import { AsyncPipe, NgIf } from '@angular/common';
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
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressBarModule } from '@angular/material/progress-bar';

import { BehaviorSubject, of } from 'rxjs';
import { catchError, finalize, map, take } from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import {
  WorkerDetailsApiService,
  type WorkerConfig,
  type WorkerConfigPatch,
} from '../worker-details-api.service';

type ConfigForm = {
  base_lat_ms: FormControl<number>;
  jitter_ms: FormControl<number>;
  capacity: FormControl<number>;
  weight: FormControl<number>;
};

@Component({
  selector: 'app-worker-config-panel',
  standalone: true,
  imports: [
    NgIf,
    AsyncPipe,
    ReactiveFormsModule,
    MatCardModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSnackBarModule,
    MatProgressBarModule,
  ],
  templateUrl: './worker-config-panel.component.html',
  styleUrl: './worker-config-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkerConfigPanelComponent implements OnInit {
  private readonly api = inject(WorkerDetailsApiService);
  private readonly snack = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  @Input({ required: true }) workerId!: string;

  private baseline: WorkerConfig | null = null;

  readonly busy$ = new BehaviorSubject<boolean>(false);

  readonly form = new FormGroup<ConfigForm>({
    base_lat_ms: new FormControl<number>(0, {
      nonNullable: true,
      validators: [Validators.min(0), Validators.max(60000)],
    }),
    jitter_ms: new FormControl<number>(0, {
      nonNullable: true,
      validators: [Validators.min(0), Validators.max(60000)],
    }),
    capacity: new FormControl<number>(1, {
      nonNullable: true,
      validators: [Validators.min(1), Validators.max(100000)],
    }),
    weight: new FormControl<number>(1, {
      nonNullable: true,
      validators: [Validators.min(1), Validators.max(1000)],
    }),
  });

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.busy$.next(true);

    this.api
      .getConfig(this.workerId)
      .pipe(
        take(1),
        map((cfg) => {
          this.baseline = cfg;
          this.form.setValue(
            {
              base_lat_ms: cfg.base_lat_ms,
              jitter_ms: cfg.jitter_ms,
              capacity: cfg.capacity,
              weight: cfg.weight,
            },
            { emitEvent: false }
          );
          this.form.markAsPristine();
        }),
        catchError((e) => {
          this.snack.open(`Load config failed: ${this.errMsg(e)}`, 'OK', {
            duration: 4000,
          });
          return of(void 0);
        }),
        finalize(() => this.busy$.next(false)),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe();
  }

  save(): void {
    if (!this.baseline) return;

    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.snack.open('Fix validation errors.', 'OK', { duration: 2500 });
      return;
    }

    const v = this.form.getRawValue();
    const patch: WorkerConfigPatch = {};

    if (v.base_lat_ms !== this.baseline.base_lat_ms)
      patch.base_lat_ms = v.base_lat_ms;
    if (v.jitter_ms !== this.baseline.jitter_ms) patch.jitter_ms = v.jitter_ms;
    if (v.capacity !== this.baseline.capacity) patch.capacity = v.capacity;
    if (v.weight !== this.baseline.weight) patch.weight = v.weight;

    if (Object.keys(patch).length === 0) {
      this.snack.open('No changes to save.', 'OK', { duration: 2000 });
      return;
    }

    this.busy$.next(true);

    this.api
      .patchConfig(this.workerId, patch)
      .pipe(
        take(1),
        map((cfg) => {
          this.baseline = cfg;
          this.form.setValue(
            {
              base_lat_ms: cfg.base_lat_ms,
              jitter_ms: cfg.jitter_ms,
              capacity: cfg.capacity,
              weight: cfg.weight,
            },
            { emitEvent: false }
          );
          this.form.markAsPristine();
          this.snack.open('Config saved.', 'OK', { duration: 2000 });
        }),
        catchError((e) => {
          this.snack.open(`Save failed: ${this.errMsg(e)}`, 'OK', {
            duration: 4000,
          });
          return of(void 0);
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
