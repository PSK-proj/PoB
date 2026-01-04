import { inject, Injectable, NgZone } from '@angular/core';
import {
  BehaviorSubject,
  distinctUntilChanged,
  filter,
  interval,
  map,
  of,
  shareReplay,
  startWith,
  switchMap,
  tap,
  timer,
} from 'rxjs';
import { WS_PATH } from '../config/environment.tokens';
import { wsUrlFromWindow } from '../utils/url';
import type { StateStreamMessage } from '../models/lb.models';
import { LbApiService } from '../api/lb-api.service';
import { WsClient, type WsStatus } from './ws.client';

type SourceMode = 'ws' | 'poll';

@Injectable({ providedIn: 'root' })
export class StateStreamService {
  private readonly lb = inject(LbApiService);
  private readonly zone = inject(NgZone);
  private readonly wsPath = inject(WS_PATH);

  private readonly mode$ = new BehaviorSubject<SourceMode>('ws');
  private readonly status$ = new BehaviorSubject<WsStatus>({
    kind: 'disconnected',
    reason: 'init',
  });

  private readonly ws = new WsClient<StateStreamMessage>(
    wsUrlFromWindow(this.wsPath),
    5_000
  );

  readonly connection$ = this.status$.pipe(
    shareReplay({ bufferSize: 1, refCount: true })
  );

  readonly state$ = this.mode$.pipe(
    distinctUntilChanged(),
    switchMap((m) => (m === 'ws' ? this.wsState$() : this.pollState$())),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  constructor() {
    this.zone.runOutsideAngular(() => {
      this.ws.status$.subscribe((s) =>
        this.zone.run(() => this.status$.next(s))
      );
      this.ws.connect();
    });

    this.connection$
      .pipe(
        tap((s) => {
          if (s.kind === 'connected') this.mode$.next('ws');
          if (s.kind === 'disconnected') this.mode$.next('poll');
        }),
        switchMap((s) =>
          s.kind === 'disconnected' ? this.reconnectLoop$() : of(null)
        )
      )
      .subscribe();
  }

  private wsState$() {
    return this.ws.messages$.pipe(
      filter(
        (m): m is StateStreamMessage => !!m && m.type === 'state' && !!m.payload
      ),
      map((m) => m.payload)
    );
  }

  private pollState$() {
    return interval(1000).pipe(
      startWith(0),
      switchMap(() => this.lb.state())
    );
  }

  private reconnectLoop$() {
    const delays = [500, 1000, 2000, 5000];
    return timer(0, 5000).pipe(
      startWith(0),
      switchMap((tick) => {
        const i = Math.min(tick, delays.length - 1);
        return timer(delays[i] ?? 5000).pipe(
          tap(() => this.zone.runOutsideAngular(() => this.ws.connect()))
        );
      })
    );
  }
}
