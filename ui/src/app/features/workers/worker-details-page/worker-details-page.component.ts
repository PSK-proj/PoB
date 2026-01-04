import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AsyncPipe, CommonModule } from '@angular/common';
import { map } from 'rxjs';

import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';

@Component({
  standalone: true,
  imports: [
    AsyncPipe,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    CommonModule,
  ],
  templateUrl: './worker-details-page.component.html',
  styleUrl: './worker-details-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkerDetailsPageComponent {
  private readonly route = inject(ActivatedRoute);
  readonly workerId$ = this.route.paramMap.pipe(map((p) => p.get('id') ?? ''));
}
