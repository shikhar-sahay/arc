export interface EngineStatus {
  running: boolean;
  platform: string;
  enforcement_supported: boolean;
  euid?: number | null;
  privileged_hint?: boolean | null;
  poll_interval_seconds: number;
  contract_count: number;
  active_contracts: number;
  error_contracts: number;
  event_count: number;
  cgroup_available: boolean;
  cgroup_reason: string;
}

export interface SystemTelemetry {
  cpu_percent: number;
  memory_percent: number;
  cpu_count: number;
  timestamp: number;
  cpu_per_core_percent?: number[];
}

export interface TargetIdentity {
  pid: number;
  create_time: number;
  name?: string | null;
  start_time_ticks?: number | null;
}

export interface ResourceLabWorkload {
  pid: number;
  role: "foreground" | "background" | "suspension-target";
  cpu_percent: number;
  affinity: number[];
  original_affinity: number[];
  nice: number;
  operations_per_second: number;
  sampled_at?: number | null;
}

export interface ResourceLabState {
  supported: boolean;
  state: "stopped" | "baseline" | "pressure" | "recovery";
  worker_count: number;
  foreground_operations_per_second: number;
  background_operations_per_second: number;
  workloads: ResourceLabWorkload[];
  target_token?: string | null;
  policy_cpu?: number | null;
  contract?: ContractStatus | null;
}

export interface ProcessMatch {
  executable?: string | null;
  command_contains?: string | null;
}

export interface ProcessTarget {
  type: "process";
  match: ProcessMatch;
}

export interface Condition {
  metric: string;
  operator: string;
  value: number | boolean;
  for_seconds: number;
}

export type Action =
  | { type: "nice"; value: number }
  | { type: "cpu_affinity"; cpus: number[] }
  | { type: "suspend" }
  | { type: "resume" }
  | { type: "cpu_quota"; quota_percent: number };

export interface Contract {
  version: 1;
  id: string;
  name: string;
  description?: string | null;
  enabled: boolean;
  target: ProcessTarget;
  trigger: Condition;
  actions: Action[];
  restore: Condition;
}

export type LifecycleState =
  "inactive" | "activating" | "active" | "restoring" | "error";

export interface ContractStatus {
  contract: Contract;
  lifecycle: LifecycleState;
  outcome?: string | null;
  matched_pids: number[];
  active_targets?: TargetIdentity[];
  trigger_raw?: boolean | null;
  trigger_satisfied?: boolean | null;
  restore_raw?: boolean | null;
  restore_satisfied?: boolean | null;
  activated_at?: number | null;
  last_error?: string | null;
  trigger_elapsed_seconds?: number | null;
  restore_elapsed_seconds?: number | null;
}

export interface ProcessItem {
  pid: number;
  name?: string | null;
  cmdline?: string | null;
  cpu_percent?: number | null;
  memory_percent?: number | null;
  nice?: number | null;
  cpu_affinity?: number[] | null;
  arc_managed: boolean;
  active_contract_ids: string[];
}

export interface ArcEvent {
  seq: number;
  timestamp: number;
  type: string;
  severity: string;
  contract_id?: string | null;
  pid?: number | null;
  message: string;
  details?: Record<string, unknown>;
}

export interface WebSocketMessage {
  type: "init" | "tick";
  status: {
    running: boolean;
    contract_count: number;
    active_contracts: number;
    error_contracts: number;
    enforcement_supported: boolean;
    cgroup_available: boolean;
    cgroup_reason: string;
  };
  telemetry: SystemTelemetry | null;
  recent_events: Array<{
    seq: number;
    timestamp: number;
    type: string;
    severity: string;
    message: string;
    contract_id?: string | null;
    pid?: number | null;
  }>;
}
