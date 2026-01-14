import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  Input,
  NgZone,
  OnChanges,
  OnDestroy,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import * as echarts from 'echarts';
import type { EChartsOption, EChartsType } from 'echarts';

@Component({
  selector: 'app-echart',
  standalone: true,
  templateUrl: './echart.component.html',
  styleUrl: './echart.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EchartComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() options: EChartsOption | null = null;
  @Input() merge: EChartsOption | null = null;
  @Input() height = 260;

  @ViewChild('host', { static: true }) hostRef!: ElementRef<HTMLDivElement>;

  private chart: EChartsType | null = null;
  private resizeObs: ResizeObserver | null = null;

  private pendingBase: EChartsOption | null = null;
  private pendingMerge: EChartsOption | null = null;

  constructor(private readonly zone: NgZone) {}

  ngAfterViewInit(): void {
    const el = this.hostRef.nativeElement;

    this.zone.runOutsideAngular(() => {
      this.chart = echarts.init(el);
      this.resizeObs = new ResizeObserver(() => this.chart?.resize());
      this.resizeObs.observe(el);
    });

    const base = this.pendingBase ?? this.options;
    if (base) this.applyBase(base);

    const m = this.pendingMerge ?? this.merge;
    if (m) this.applyMerge(m);

    this.pendingBase = null;
    this.pendingMerge = null;
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (!this.chart) {
      if ('options' in changes) this.pendingBase = this.options;
      if ('merge' in changes) this.pendingMerge = this.merge;
      return;
    }

    if ('options' in changes && this.options) {
      this.applyBase(this.options);
    }

    if ('merge' in changes && this.merge) {
      this.applyMerge(this.merge);
    }
  }

  ngOnDestroy(): void {
    this.resizeObs?.disconnect();
    this.resizeObs = null;

    this.chart?.dispose();
    this.chart = null;
  }

  private applyBase(opt: EChartsOption): void {
    this.zone.runOutsideAngular(() => {
      this.chart?.setOption(opt, { notMerge: true, lazyUpdate: true });
      this.chart?.resize();
    });
  }

  private applyMerge(merge: EChartsOption): void {
    this.zone.runOutsideAngular(() => {
      this.chart?.setOption(merge, { notMerge: false, lazyUpdate: true });
    });
  }
}
