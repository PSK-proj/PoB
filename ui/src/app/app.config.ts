import { ApplicationConfig } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimations } from '@angular/platform-browser/animations';

import { routes } from './app.routes';
import { API_BASE_URL, WS_PATH } from './core/config/environment.tokens';
import { errorNormalizerInterceptor } from './core/interceptors/error-normalizer.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideAnimations(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([errorNormalizerInterceptor])),

    { provide: API_BASE_URL, useValue: '' },
    { provide: WS_PATH, useValue: '/stream' },
  ],
};
