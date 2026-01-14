import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { AsyncPipe, DatePipe, DecimalPipe, NgIf } from '@angular/common';
import { RouterLink } from '@angular/router';

import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';

import { ExperimentResetDialogComponent } from '../experiment-reset-dialog/experiment-reset-dialog.component';
import { StateStreamService } from '../../../core/realtime/state-stream.service';
import { DashboardChartsPanelComponent } from '../dashboard-charts-panel/dashboard-charts-panel.component';

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
    MatButtonModule,
    DashboardChartsPanelComponent,
  ],
  templateUrl: './dashboard-page.component.html',
  styleUrl: './dashboard-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardPageComponent {
  private readonly stream = inject(StateStreamService);
  private readonly dialog = inject(MatDialog);

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

  openResetExperiment(): void {
    this.dialog.open(ExperimentResetDialogComponent, {
      width: '900px',
      maxWidth: '95vw',
    });
  }
}
