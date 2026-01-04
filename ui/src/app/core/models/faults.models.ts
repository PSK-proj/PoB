export type FaultKind = 'delay' | 'drop' | 'corrupt' | 'cpu_burn' | 'error';

export interface FaultCommon {
  probability?: number;
  duration_sec?: number | null;
}

export interface DelayFaultCreate extends FaultCommon {
  kind: 'delay';
  delay_ms: number;
}

export interface DropFaultCreate extends FaultCommon {
  kind: 'drop';
  mode?: '503' | 'timeout';
  status_code?: number;
  sleep_ms?: number;
}

export interface CorruptFaultCreate extends FaultCommon {
  kind: 'corrupt';
  mode?: 'invalid_json' | 'bad_fields';
}

export interface CpuBurnFaultCreate extends FaultCommon {
  kind: 'cpu_burn';
  burn_ms?: number;
}

export interface ErrorFaultCreate extends FaultCommon {
  kind: 'error';
  status_code?: number;
  message?: string;
}

export type FaultCreate =
  | DelayFaultCreate
  | DropFaultCreate
  | CorruptFaultCreate
  | CpuBurnFaultCreate
  | ErrorFaultCreate;

export interface FaultView {
  id: string;
  kind: string;
  created_at: number;
  expires_at: number | null;
  spec: Record<string, unknown>;
}
