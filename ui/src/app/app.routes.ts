import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },

  {
    path: 'dashboard',
    loadComponent: () =>
      import(
        './features/dashboard/dashboard-page/dashboard-page.component'
      ).then((m) => m.DashboardPageComponent),
  },
  {
    path: 'traffic',
    loadComponent: () =>
      import('./features/traffic/traffic-page/traffic-page.component').then(
        (m) => m.TrafficPageComponent
      ),
  },
  {
    path: 'workers',
    loadComponent: () =>
      import('./features/workers/workers-page/workers-page.component').then(
        (m) => m.WorkersPageComponent
      ),
  },
  {
    path: 'workers/:id',
    loadComponent: () =>
      import(
        './features/workers/worker-details-page/worker-details-page.component'
      ).then((m) => m.WorkerDetailsPageComponent),
  },
  { path: '**', redirectTo: 'dashboard' },
];
