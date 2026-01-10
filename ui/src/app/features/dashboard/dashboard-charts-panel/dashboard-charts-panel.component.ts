import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { AsyncPipe, DecimalPipe, NgIf } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import type { EChartsOption, LineSeriesOption } from 'echarts';
import { concat, from, of } from 'rxjs';
import {
  auditTime,
  catchError,
  filter,
  map,
  scan,
  shareReplay,
  switchMap,
} from 'rxjs/operators';

import { StateStreamService } from '../../../core/realtime/state-stream.service';
import type { LbStateSample, LbStateView } from '../../../core/models/lb.models';
import { LbApiService } from '../../../core/api/lb-api.service';
import { EchartComponent } from '../../../shared/echarts/echart/echart.component';

type Point = [number, number];

type Acc = {
  windowMs: number;

  lastTs: number | null;
  lastAssigned: number | null;
  lastOk: number | null;
  lastFail: number | null;

  throughput: Point[];
  failRatePct: Point[];

  workerIds: string[];
  sharePct: Record<string, Point[]>;
  latencyMs: Record<string, Point[]>;
};

type Vm = {
  throughputBaseOpt: EChartsOption;
  throughputMerge: EChartsOption;

  failRateBaseOpt: EChartsOption;
  failRateMerge: EChartsOption;

  shareBaseOpt: EChartsOption;
  shareMerge: EChartsOption;

  latencyBaseOpt: EChartsOption;
  latencyMerge: EChartsOption;

  lastThroughput: number | null;
  lastFailRate: number | null;
};

@Component({
  selector: 'app-dashboard-charts-panel',
  standalone: true,
  imports: [NgIf, AsyncPipe, DecimalPipe, MatCardModule, EchartComponent],
  templateUrl: './dashboard-charts-panel.component.html',
  styleUrl: './dashboard-charts-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardChartsPanelComponent {
  private readonly lb = inject(LbApiService);
  private readonly stream = inject(StateStreamService);

  private readonly windowMs = 120_000;

  private readonly throughputBaseOpt = this.buildThroughputBaseOption();
  private readonly failRateBaseOpt = this.buildFailRateBaseOption();
  private readonly shareBaseOpt = this.buildShareBaseOption();
  private readonly latencyBaseOpt = this.buildLatencyBaseOption();

  readonly vm$ = this.lb.stateHistory().pipe(
    catchError(() => of([] as LbStateSample[])),
    switchMap((history) => {
      const lastTs = history.at(-1)?.ts ?? 0;
      const history$ = from(history);
      const live$ = this.stream.stateSamples$.pipe(
        filter((s) => lastTs === 0 || s.ts > lastTs)
      );
      return concat(history$, live$);
    }),
    scan((acc, ev) => this.accumulate(acc, ev.ts, ev.state), this.initAcc()),
    auditTime(1000),
    map((acc): Vm => {
      const lastThroughput = acc.throughput.at(-1)?.[1] ?? null;
      const lastFailRate = acc.failRatePct.at(-1)?.[1] ?? null;

      return {
        throughputBaseOpt: this.throughputBaseOpt,
        throughputMerge: this.buildThroughputMerge(acc.throughput),

        failRateBaseOpt: this.failRateBaseOpt,
        failRateMerge: this.buildFailRateMerge(acc.failRatePct),

        shareBaseOpt: this.shareBaseOpt,
        shareMerge: this.buildShareMerge(acc.workerIds, acc.sharePct),

        latencyBaseOpt: this.latencyBaseOpt,
        latencyMerge: this.buildLatencyMerge(acc.workerIds, acc.latencyMs),

        lastThroughput,
        lastFailRate,
      };
    }),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  private initAcc(): Acc {
    return {
      windowMs: this.windowMs,
      lastTs: null,
      lastAssigned: null,
      lastOk: null,
      lastFail: null,
      throughput: [],
      failRatePct: [],
      workerIds: [],
      sharePct: {},
      latencyMs: {},
    };
  }

  private accumulate(acc: Acc, ts: number, s: LbStateView): Acc {
    if (this.isReset(acc, s)) return this.bootstrapAfterReset(ts, s);

    const next = this.ensureWorkers(acc, s);

    this.updateRates(next, ts, s);
    this.updatePerWorker(next, ts, s);

    next.lastTs = ts;
    next.lastAssigned = s.total_assigned;
    next.lastOk = s.total_ok;
    next.lastFail = s.total_fail;

    return next;
  }

  private isReset(acc: Acc, s: LbStateView): boolean {
    if (acc.lastAssigned == null || acc.lastOk == null || acc.lastFail == null)
      return false;
    return (
      s.total_assigned < acc.lastAssigned ||
      s.total_ok < acc.lastOk ||
      s.total_fail < acc.lastFail
    );
  }

  private bootstrapAfterReset(ts: number, s: LbStateView): Acc {
    const acc = this.initAcc();
    acc.lastTs = ts;
    acc.lastAssigned = s.total_assigned;
    acc.lastOk = s.total_ok;
    acc.lastFail = s.total_fail;

    acc.workerIds = s.workers.map((w) => w.id);
    for (const w of s.workers) {
      acc.sharePct[w.id] = [[ts, w.assigned_pct]];
      acc.latencyMs[w.id] = [[ts, this.safeNonNeg(w.avg_latency_ms)]];
    }

    return acc;
  }

  private ensureWorkers(acc: Acc, s: LbStateView): Acc {
    const next: Acc = { ...acc };

    if (next.workerIds.length === 0) {
      next.workerIds = s.workers.map((w) => w.id);
      next.sharePct = {};
      next.latencyMs = {};
      for (const id of next.workerIds) {
        next.sharePct[id] = [];
        next.latencyMs[id] = [];
      }
      return next;
    }

    const incoming = s.workers.map((w) => w.id);
    const newIds = incoming.filter((id) => !next.workerIds.includes(id));
    if (newIds.length === 0) return next;

    next.workerIds = [...next.workerIds, ...newIds];
    next.sharePct = { ...next.sharePct };
    next.latencyMs = { ...next.latencyMs };
    for (const id of newIds) {
      next.sharePct[id] = [];
      next.latencyMs[id] = [];
    }

    return next;
  }

  private updateRates(acc: Acc, ts: number, s: LbStateView): void {
    const prevTs = acc.lastTs;
    const prevAssigned = acc.lastAssigned;
    const prevOk = acc.lastOk;
    const prevFail = acc.lastFail;

    if (
      prevTs == null ||
      prevAssigned == null ||
      prevOk == null ||
      prevFail == null
    )
      return;

    const dt = (ts - prevTs) / 1000;
    if (dt <= 0) return;

    const dAssigned = Math.max(0, s.total_assigned - prevAssigned);
    const dOk = Math.max(0, s.total_ok - prevOk);
    const dFail = Math.max(0, s.total_fail - prevFail);

    acc.throughput = this.pushTrim(
      acc.throughput,
      [ts, dAssigned / dt],
      ts,
      acc.windowMs
    );

    const dCompleted = dOk + dFail;
    const failRate = dCompleted > 0 ? (dFail / dCompleted) * 100 : 0;
    acc.failRatePct = this.pushTrim(
      acc.failRatePct,
      [ts, failRate],
      ts,
      acc.windowMs
    );
  }

  private updatePerWorker(acc: Acc, ts: number, s: LbStateView): void {
    const share = { ...acc.sharePct };
    const lat = { ...acc.latencyMs };

    for (const w of s.workers) {
      const id = w.id;
      share[id] = this.pushTrim(
        share[id] ?? [],
        [ts, w.assigned_pct],
        ts,
        acc.windowMs
      );
      lat[id] = this.pushTrim(
        lat[id] ?? [],
        [ts, this.safeNonNeg(w.avg_latency_ms)],
        ts,
        acc.windowMs
      );
    }

    acc.sharePct = share;
    acc.latencyMs = lat;
  }

  private pushTrim(
    arr: Point[],
    p: Point,
    now: number,
    windowMs: number
  ): Point[] {
    const out = [...arr, p];
    const cutoff = now - windowMs;

    let i = 0;
    while (i < out.length && out[i][0] < cutoff) i++;

    return i > 0 ? out.slice(i) : out;
  }

  private safeNonNeg(x: number): number {
    return Math.max(0, Number.isFinite(x) ? x : 0);
  }

  private fmtTime(v: unknown): string {
    const ts = typeof v === 'number' ? v : Number(v);
    const d = new Date(Number.isFinite(ts) ? ts : Date.now());

    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
  }

  private baseGrid(): EChartsOption['grid'] {
    return { left: 44, right: 18, top: 30, bottom: 30, containLabel: true };
  }

  private baseGridWithLegend(): EChartsOption['grid'] {
    return { left: 44, right: 18, top: 56, bottom: 30, containLabel: true };
  }

  private baseTooltip(): EChartsOption['tooltip'] {
    return { trigger: 'axis', axisPointer: { type: 'line' } };
  }

  private buildThroughputBaseOption(): EChartsOption {
    const series: LineSeriesOption[] = [
      {
        id: 'throughput',
        name: 'assigned/s',
        type: 'line',
        showSymbol: false,
        data: [],
      },
    ];

    return {
      animation: false,
      grid: this.baseGrid(),
      tooltip: this.baseTooltip(),
      xAxis: {
        type: 'time',
        axisLabel: { formatter: (v: unknown) => this.fmtTime(v) },
      },
      yAxis: { type: 'value', name: 'req/s', min: 0 },
      series,
    };
  }

  private buildFailRateBaseOption(): EChartsOption {
    const series: LineSeriesOption[] = [
      {
        id: 'failRate',
        name: 'fail %',
        type: 'line',
        showSymbol: false,
        data: [],
      },
    ];

    return {
      animation: false,
      grid: this.baseGrid(),
      tooltip: this.baseTooltip(),
      xAxis: {
        type: 'time',
        axisLabel: { formatter: (v: unknown) => this.fmtTime(v) },
      },
      yAxis: { type: 'value', name: '%', min: 0, max: 100 },
      series,
    };
  }

  private buildShareBaseOption(): EChartsOption {
    return {
      animation: false,
      grid: this.baseGridWithLegend(),
      tooltip: this.baseTooltip(),
      legend: { type: 'scroll', top: 0 },
      xAxis: {
        type: 'time',
        axisLabel: { formatter: (v: unknown) => this.fmtTime(v) },
      },
      yAxis: {
        type: 'value',
        name: '%',
        min: 0,
        max: 100,
        nameLocation: 'middle',
        nameRotate: 90,
        nameGap: 40,
      },
      series: [],
    };
  }

  private buildLatencyBaseOption(): EChartsOption {
    return {
      animation: false,
      grid: this.baseGridWithLegend(),
      tooltip: this.baseTooltip(),
      legend: { type: 'scroll', top: 0 },
      xAxis: {
        type: 'time',
        axisLabel: { formatter: (v: unknown) => this.fmtTime(v) },
      },
      yAxis: {
        type: 'value',
        name: 'ms',
        min: 0,
        nameLocation: 'middle',
        nameRotate: 90,
        nameGap: 40,
      },
      series: [],
    };
  }

  private buildThroughputMerge(points: Point[]): EChartsOption {
    const series: LineSeriesOption[] = [{ id: 'throughput', data: points }];
    return { series };
  }

  private buildFailRateMerge(points: Point[]): EChartsOption {
    const series: LineSeriesOption[] = [{ id: 'failRate', data: points }];
    return { series };
  }

  private buildShareMerge(
    ids: string[],
    dict: Record<string, Point[]>
  ): EChartsOption {
    const series: LineSeriesOption[] = ids.map(
      (id): LineSeriesOption => ({
        id,
        name: id,
        type: 'line',
        showSymbol: false,
        stack: 'share',
        areaStyle: {},
        data: dict[id] ?? [],
      })
    );
    return { series };
  }

  private buildLatencyMerge(
    ids: string[],
    dict: Record<string, Point[]>
  ): EChartsOption {
    const series: LineSeriesOption[] = ids.map(
      (id): LineSeriesOption => ({
        id,
        name: id,
        type: 'line',
        showSymbol: false,
        data: dict[id] ?? [],
      })
    );
    return { series };
  }
}
