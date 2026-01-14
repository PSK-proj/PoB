import { Subject } from 'rxjs';

export type WsStatus =
  | { kind: 'connecting' }
  | { kind: 'connected' }
  | { kind: 'disconnected'; reason?: string };

export class WsClient<T> {
  private ws: WebSocket | null = null;
  private lastMsgAt = 0;
  private staleTimer: ReturnType<typeof globalThis.setInterval> | null = null;

  private readonly statusSubject = new Subject<WsStatus>();
  private readonly msgSubject = new Subject<T>();

  readonly status$ = this.statusSubject.asObservable();
  readonly messages$ = this.msgSubject.asObservable();

  constructor(private readonly url: string, private readonly staleMs: number) {}

  connect(): void {
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    this.statusSubject.next({ kind: 'connecting' });
    const ws = new WebSocket(this.url);
    this.ws = ws;

    ws.onopen = () => {
      this.lastMsgAt = Date.now();
      this.statusSubject.next({ kind: 'connected' });
      this.armStale();
    };

    ws.onmessage = (ev) => {
      this.lastMsgAt = Date.now();
      try {
        const txt = typeof ev.data === 'string' ? ev.data : String(ev.data);
        this.msgSubject.next(JSON.parse(txt) as T);
      } catch {
        this.close('invalid_json_message');
      }
    };

    ws.onclose = (ev) => {
      this.disarmStale();
      this.statusSubject.next({
        kind: 'disconnected',
        reason: `${ev.code}:${ev.reason}`,
      });
      this.ws = null;
    };

    ws.onerror = () => {};
  }

  close(reason = 'client_close'): void {
    this.disarmStale();
    try {
      this.ws?.close(1000, reason);
    } catch {}
    this.ws = null;
    this.statusSubject.next({ kind: 'disconnected', reason });
  }

  private armStale(): void {
    this.disarmStale();

    const everyMs = Math.max(250, Math.floor(this.staleMs / 2));
    this.staleTimer = globalThis.setInterval(() => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      if (Date.now() - this.lastMsgAt > this.staleMs) this.close('stale');
    }, everyMs);
  }

  private disarmStale(): void {
    if (this.staleTimer != null) {
      globalThis.clearInterval(this.staleTimer);
      this.staleTimer = null;
    }
  }
}
