import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
} from '@angular/core';
import { AsyncPipe, DatePipe, DecimalPipe, NgIf } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatTabsModule } from '@angular/material/tabs';

import { distinctUntilChanged, map, shareReplay } from 'rxjs/operators';

import { StateStreamService } from '../../../core/realtime/state-stream.service';
import type { WorkerView } from '../../../core/models/lb.models';
import { WorkerConfigPanelComponent } from '../worker-config-panel/worker-config-panel.component';
import { WorkerMetricsPanelComponent } from '../worker-metrics-panel/worker-metrics-panel.component';
import { WorkerFaultsPanelComponent } from '../worker-faults-panel/worker-faults-panel.component';

@Component({
  standalone: true,
  imports: [
    NgIf,
    AsyncPipe,
    DatePipe,
    DecimalPipe,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatTabsModule,
    WorkerConfigPanelComponent,
    WorkerMetricsPanelComponent,
    WorkerFaultsPanelComponent,
  ],
  templateUrl: './worker-details-page.component.html',
  styleUrl: './worker-details-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkerDetailsPageComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly stream = inject(StateStreamService);
  private readonly destroyRef = inject(DestroyRef);

  readonly workerId$ = this.route.paramMap.pipe(
    map((pm) => pm.get('id') ?? ''),
    map((v) => v.trim()),
    distinctUntilChanged(),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  readonly worker$ = this.stream.state$.pipe(
    map((s) => s.workers),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  findWorker(workers: WorkerView[], id: string): WorkerView | null {
    const w = workers.find((x) => x.id === id);
    return w ?? null;
  }
}
