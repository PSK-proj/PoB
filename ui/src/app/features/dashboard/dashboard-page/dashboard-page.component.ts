import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { AsyncPipe, DatePipe, DecimalPipe, NgIf } from '@angular/common';
import { RouterLink } from '@angular/router';

import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatChipsModule } from '@angular/material/chips';

import { StateStreamService } from '../../../core/realtime/state-stream.service';

@Component({
  standalone: true,
  imports: [
    AsyncPipe,
    NgIf,
    DatePipe,
    DecimalPipe,
    RouterLink,
    MatCardModule,
    MatTableModule,
    MatChipsModule,
  ],
  templateUrl: './dashboard-page.component.html',
  styleUrl: './dashboard-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardPageComponent {
  private readonly stream = inject(StateStreamService);

  conn$ = this.stream.connection$;
  state$ = this.stream.state$;

  cols = [
    'id',
    'online',
    'effWeight',
    'assignedPct',
    'okFail',
    'lat',
    'lastSeen',
    'err',
  ];
}
