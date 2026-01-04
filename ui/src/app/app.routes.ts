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
  { path: '**', redirectTo: 'dashboard' },
];
