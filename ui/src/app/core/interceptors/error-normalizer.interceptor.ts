import {
  HttpErrorResponse,
  type HttpInterceptorFn,
} from '@angular/common/http';
import { catchError, throwError } from 'rxjs';
import { ApiHttpError, type ApiError } from '../api/http.types';

export const errorNormalizerInterceptor: HttpInterceptorFn = (req, next) =>
  next(req).pipe(
    catchError((e: unknown) => {
      if (!(e instanceof HttpErrorResponse)) return throwError(() => e);

      const body = e.error;
      let msg = e.message || 'Request failed';
      let details: unknown = body;

      if (body && typeof body === 'object' && 'detail' in body) {
        const d = body.detail;
        if (typeof d === 'string') msg = d;
        else if (d && typeof d === 'object' && typeof d.message === 'string')
          msg = d.message;
        details = d;
      } else if (typeof body === 'string' && body.trim()) {
        msg = body;
      }

      const api: ApiError = {
        status: e.status ?? 0,
        message:
          (e.status ?? 0) === 0
            ? 'Network error (dev proxy / backend down?)'
            : msg,
        url: req.url,
        details,
      };

      return throwError(() => new ApiHttpError(api));
    })
  );
