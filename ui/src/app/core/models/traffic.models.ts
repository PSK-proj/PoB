export interface TrafficStartRequest {
  rps: number;
  duration_sec?: number | null;
  endpoint?: string;
  profile?: string;
}

export interface TrafficStartResponse {
  ok: true;
  message: string;
  config: {
    rps: number;
    duration_sec?: number | null;
    endpoint: string;
    profile: string;
  };
}

export interface TrafficStopResponse {
  ok: true;
  message: string;
}

export interface TrafficStatusResponse {
  running: boolean;
  rps?: number | null;
  duration_sec?: number | null;
  profile?: string | null;
  endpoint?: string | null;
  started_at?: number | null;
  total_sent: number;
  total_ok: number;
  total_fail: number;
  last_error?: string | null;
}
