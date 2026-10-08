import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Cpu,
  FileCode2,
  MemoryStick,
  Radio,
  ServerCog,
} from "lucide-react";
import {
  ArcEvent,
  ContractStatus,
  EngineStatus,
  ProcessItem,
  SystemTelemetry,
} from "../types";
import { WsStatus } from "../useWebSocket";
import { TelemetryChart } from "../components/TelemetryChart";
import {
  formatSecondsAgo,
  formatTimestamp,
  lifecycleCounts,
} from "../lib/utils";
import { LifecycleBadge, SeverityBadge } from "../components/Badge";

interface Props {
  engineStatus: EngineStatus | null;
  telemetry: SystemTelemetry | null;
  cpuHistory: number[];
  memHistory: number[];
  contracts: ContractStatus[];
  recentEvents: ArcEvent[];
  processes: ProcessItem[];
  wsStatus: WsStatus;
  stale: boolean;
  onNavigateEvents: () => void;
  onNavigateContracts: () => void;
}

export function OverviewPage({
  engineStatus,
  telemetry,
  cpuHistory,
  memHistory,
  contracts,
  recentEvents,
  processes,
  wsStatus,
  stale,
  onNavigateEvents,
  onNavigateContracts,
}: Props) {
  const counts = lifecycleCounts(contracts);
  const enabled = contracts.filter((item) => item.contract.enabled).length;
  const managed = processes.filter((process) => process.arc_managed);
  const active = contracts.filter((item) =>
    ["activating", "active", "restoring"].includes(item.lifecycle),
  );
  const cores = telemetry?.cpu_per_core_percent ?? [];
  const connection = stale
    ? "Stale"
    : wsStatus === "connected"
      ? "Live"
      : wsStatus === "reconnecting"
        ? "Reconnecting"
        : "Disconnected";

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <div className="page-kicker">Operations</div>
          <h1 className="page-title">System overview</h1>
          <p className="page-description">
            Live Linux telemetry, policy state, and recent engine decisions from
            the persistent ARC runtime.
          </p>
        </div>
        <div className="page-actions">
          <span
            className={`badge ${stale || wsStatus !== "connected" ? "amber" : "green"}`}
          >
            <Radio size={11} />
            {connection}
          </span>
          <span
            className={`badge ${engineStatus?.enforcement_supported ? "green" : ""}`}
          >
            <ServerCog size={11} />
            {engineStatus?.enforcement_supported
              ? "Enforcement supported"
              : "Observation only"}
          </span>
        </div>
      </header>

      <section className="metric-grid" aria-label="Engine summary">
        <div className="metric-tile">
          <div className="metric-label">
            <Cpu size={14} />
            CPU utilization
          </div>
          <div className="metric-value" style={{ color: "var(--blue)" }}>
            {telemetry ? `${telemetry.cpu_percent.toFixed(1)}%` : "--"}
          </div>
          <div className="metric-note">
            {telemetry?.cpu_count ?? "--"} logical processors
          </div>
        </div>
        <div className="metric-tile">
          <div className="metric-label">
            <MemoryStick size={14} />
            Memory utilization
          </div>
          <div className="metric-value" style={{ color: "var(--purple)" }}>
            {telemetry ? `${telemetry.memory_percent.toFixed(1)}%` : "--"}
          </div>
          <div className="metric-note">Aggregate resident use</div>
        </div>
        <div className="metric-tile">
          <div className="metric-label">
            <FileCode2 size={14} />
            Resource contracts
          </div>
          <div className="metric-value">{contracts.length}</div>
          <div className="metric-note">
            {enabled} enabled, {counts.active} active
          </div>
        </div>
        <div className="metric-tile">
          <div className="metric-label">
            <Activity size={14} />
            Managed processes
          </div>
          <div className="metric-value">{managed.length}</div>
          <div className="metric-note">
            {counts.error
              ? `${counts.error} contract errors`
              : "No latched errors"}
          </div>
        </div>
      </section>

      <div className="section-grid">
        <div className="stack">
          <section className="panel">
            <div className="panel-header">
              <div className="panel-title">
                <Activity size={14} />
                Utilization history
              </div>
              <div className="panel-subtle">Rolling 60 samples · 0 to 100%</div>
            </div>
            <div className="panel-body" style={{ paddingBottom: 8 }}>
              <TelemetryChart
                height={190}
                series={[
                  { label: "CPU", values: cpuHistory, color: "#5aa9fa" },
                  { label: "Memory", values: memHistory, color: "#b28bf4" },
                ]}
              />
            </div>
          </section>
          <section className="panel">
            <div className="panel-header">
              <div className="panel-title">
                <Cpu size={14} />
                Logical processors
              </div>
              <div className="panel-subtle">Current non-blocking sample</div>
            </div>
            <div className="panel-body">
              {cores.length ? (
                <div className="core-grid">
                  {cores.map((value, index) => (
                    <div className="core-tile" key={index}>
                      <div className="core-head">
                        <span>CPU {index}</span>
                        <strong>{value.toFixed(0)}%</strong>
                      </div>
                      <div className="meter">
                        <span style={{ width: `${value}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty" style={{ minHeight: 100 }}>
                  <div>
                    <strong>Per-core telemetry unavailable</strong>
                    <p>The backend has not supplied a per-core sample yet.</p>
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>
        <div className="stack">
          <section className="panel">
            <div className="panel-header">
              <div className="panel-title">
                <FileCode2 size={14} />
                Policy activity
              </div>
              <button
                className="button icon-button"
                onClick={onNavigateContracts}
                aria-label="Open contracts"
              >
                <ChevronRight size={14} />
              </button>
            </div>
            {active.length ? (
              <div className="list">
                {active.map((item) => (
                  <div className="list-row" key={item.contract.id}>
                    <span className="status-dot ok" />
                    <div>
                      <div className="list-primary">{item.contract.name}</div>
                      <div className="list-secondary">
                        {item.matched_pids.length} target
                        {item.matched_pids.length === 1 ? "" : "s"} ·{" "}
                        {item.contract.actions
                          .map((action) => action.type)
                          .join(", ")}
                      </div>
                    </div>
                    <LifecycleBadge lifecycle={item.lifecycle} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty">
                <div>
                  <div className="empty-icon">
                    <CheckCircle2 size={18} />
                  </div>
                  <strong>No active enforcement</strong>
                  <p>
                    {contracts.length
                      ? "Contracts are loaded and waiting for their trigger conditions."
                      : "Create a contract to connect a condition, target process, resource action, and exact restoration rule."}
                  </p>
                  {!contracts.length && (
                    <button
                      className="button primary"
                      onClick={onNavigateContracts}
                    >
                      Create contract
                    </button>
                  )}
                </div>
              </div>
            )}
          </section>
          <section className="panel">
            <div className="panel-header">
              <div className="panel-title">
                <Activity size={14} />
                Recent decisions
              </div>
              <button
                className="button icon-button"
                onClick={onNavigateEvents}
                aria-label="Open audit log"
              >
                <ChevronRight size={14} />
              </button>
            </div>
            {recentEvents.length ? (
              <div className="list">
                {recentEvents.slice(0, 6).map((event) => (
                  <div className="list-row" key={event.seq}>
                    <SeverityBadge severity={event.severity} />
                    <div>
                      <div className="list-primary">{event.message}</div>
                      <div className="list-secondary">
                        {event.type.split("_").join(" ")} ·{" "}
                        {formatTimestamp(event.timestamp)}
                      </div>
                    </div>
                    <span className="panel-subtle">
                      {formatSecondsAgo(event.timestamp)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty" style={{ minHeight: 150 }}>
                <div>
                  <strong>No policy decisions yet</strong>
                  <p>
                    Lifecycle events appear here after the engine starts
                    evaluating contracts.
                  </p>
                </div>
              </div>
            )}
          </section>
          <details className="panel">
            <summary
              className="panel-header"
              style={{ cursor: "pointer", listStyle: "none" }}
            >
              <div className="panel-title">
                <ServerCog size={14} />
                Linux capabilities
              </div>
              <span className="panel-subtle">Detection and access</span>
            </summary>
            <div className="panel-body stack" style={{ gap: 10 }}>
              <div className="status-line">
                <span
                  className={`status-dot ${engineStatus?.enforcement_supported ? "ok" : "warn"}`}
                />
                <span>
                  {engineStatus?.enforcement_supported
                    ? "Linux process controls are supported on this host"
                    : `Enforcement is unavailable on ${engineStatus?.platform ?? "this host"}`}
                </span>
              </div>
              <div className="status-line">
                <span
                  className={`status-dot ${engineStatus?.cgroup_available ? "ok" : "warn"}`}
                />
                <span>
                  {engineStatus?.cgroup_available
                    ? "A writable cgroups v2 delegation was detected"
                    : engineStatus?.cgroup_reason ||
                      "cgroups v2 access not detected"}
                </span>
              </div>
              <div className="notice">
                <AlertTriangle
                  size={13}
                  style={{ display: "inline", marginRight: 7 }}
                />
                Capability detection does not prove every future operation will
                be permitted. ARC reports kernel denials and never invokes sudo.
              </div>
            </div>
          </details>
        </div>
      </div>
      <div className="panel-subtle" style={{ marginTop: 12 }}>
        Last telemetry:{" "}
        {telemetry
          ? `${new Date(telemetry.timestamp * 1000).toLocaleTimeString()} (${formatSecondsAgo(telemetry.timestamp)})`
          : "unavailable"}
      </div>
    </main>
  );
}
