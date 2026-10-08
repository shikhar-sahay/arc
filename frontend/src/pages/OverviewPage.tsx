import {
  EngineStatus,
  SystemTelemetry,
  ContractStatus,
  ArcEvent,
} from "../types";
import { MiniSparkline } from "../components/MiniSparkline";
import { LifecycleBadge, SeverityBadge } from "../components/Badge";
import {
  formatTimestamp,
  opSymbol,
  describeAction,
  isProtectedLifecycle,
  lifecycleCounts,
} from "../lib/utils";
import { WsStatus } from "../useWebSocket";

interface OverviewPageProps {
  engineStatus: EngineStatus | null;
  telemetry: SystemTelemetry | null;
  cpuHistory: number[];
  memHistory: number[];
  contracts: ContractStatus[];
  recentEvents: ArcEvent[];
  wsStatus: WsStatus;
  onNavigateEvents: () => void;
  onNavigateContracts: () => void;
}

function MetricCard({
  label,
  value,
  sub,
  history,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  history: number[];
  color: string;
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-slate-500 font-mono">
            {label}
          </div>
          <div className="mt-1 text-2xl font-mono font-bold" style={{ color }}>
            {value}
          </div>
          {sub && (
            <div className="mt-0.5 text-[10px] text-slate-600 font-mono">
              {sub}
            </div>
          )}
        </div>
        <MiniSparkline data={history} color={color} width={80} height={32} />
      </div>
    </div>
  );
}

function CapabilityRow({
  label,
  status,
  detail,
}: {
  label: string;
  status: "ok" | "warn" | "off";
  detail: string;
}) {
  const dot =
    status === "ok"
      ? "bg-emerald-400"
      : status === "warn"
        ? "bg-amber-400"
        : "bg-slate-600";
  const text =
    status === "ok"
      ? "text-emerald-300"
      : status === "warn"
        ? "text-amber-300"
        : "text-slate-500";
  return (
    <div className="flex items-center space-x-3 text-xs font-mono">
      <span className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />
      <span className="text-slate-400 w-32 shrink-0">{label}</span>
      <span className={text}>{detail}</span>
    </div>
  );
}

export function OverviewPage({
  engineStatus,
  telemetry,
  cpuHistory,
  memHistory,
  contracts,
  recentEvents,
  wsStatus,
  onNavigateEvents,
  onNavigateContracts,
}: OverviewPageProps) {
  const activeContracts = contracts.filter((cs) =>
    isProtectedLifecycle(cs.lifecycle),
  );

  const contractCounts = {
    ...lifecycleCounts(contracts),
    total: contracts.length,
    enabled: contracts.filter((cs) => cs.contract.enabled).length,
  };

  const cpu = telemetry?.cpu_percent ?? null;
  const mem = telemetry?.memory_percent ?? null;

  return (
    <div className="space-y-5">
      {/* System metrics row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          label="System CPU"
          value={cpu !== null ? `${cpu.toFixed(1)}%` : "---"}
          sub={`${telemetry?.cpu_count ?? "?"} cores`}
          history={cpuHistory}
          color="#22d3ee"
        />
        <MetricCard
          label="System Memory"
          value={mem !== null ? `${mem.toFixed(1)}%` : "---"}
          sub="resident utilization"
          history={memHistory}
          color="#818cf8"
        />
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-3">
          <div className="text-[10px] uppercase tracking-widest text-slate-500 font-mono">
            Contracts
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs font-mono">
            <div>
              <div className="text-slate-600 text-[10px]">total</div>
              <div className="text-slate-200 font-bold">
                {contractCounts.total}
              </div>
            </div>
            <div>
              <div className="text-slate-600 text-[10px]">active</div>
              <div className="text-emerald-400 font-bold">
                {contractCounts.active}
              </div>
            </div>
            <div>
              <div className="text-slate-600 text-[10px]">error</div>
              <div
                className={
                  contractCounts.error > 0
                    ? "text-rose-400 font-bold"
                    : "text-slate-600 font-bold"
                }
              >
                {contractCounts.error}
              </div>
            </div>
          </div>
          <button
            onClick={onNavigateContracts}
            className="text-[10px] text-cyan-400 hover:underline font-mono"
          >
            Manage contracts
          </button>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-2">
          <div className="text-[10px] uppercase tracking-widest text-slate-500 font-mono mb-1">
            Engine
          </div>
          <div className="flex items-center space-x-2 text-xs font-mono">
            <span
              className={`w-2 h-2 rounded-full ${
                engineStatus?.running
                  ? "bg-emerald-400 animate-pulse"
                  : "bg-slate-600"
              }`}
            />
            <span
              className={
                engineStatus?.running ? "text-emerald-300" : "text-slate-500"
              }
            >
              {engineStatus?.running ? "RUNNING" : "STOPPED"}
            </span>
          </div>
          <div className="flex items-center space-x-2 text-xs font-mono">
            <span
              className={`w-2 h-2 rounded-full ${
                wsStatus === "connected"
                  ? "bg-emerald-400"
                  : wsStatus === "reconnecting"
                    ? "bg-amber-400 animate-pulse"
                    : "bg-rose-500"
              }`}
            />
            <span className="text-slate-400">
              {wsStatus === "connected"
                ? "live stream"
                : wsStatus === "reconnecting"
                  ? "reconnecting..."
                  : "disconnected"}
            </span>
          </div>
          <div className="text-[10px] text-slate-600 font-mono">
            poll: {engineStatus?.poll_interval_seconds ?? "?"}s
          </div>
          <div className="text-[10px] text-slate-600 font-mono">
            {engineStatus?.platform ?? "unknown"}
          </div>
        </div>
      </div>

      {/* Active policies panel */}
      {activeContracts.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-bold uppercase tracking-widest text-slate-300 font-mono">
              Active Policies
            </h2>
            <span className="text-[10px] text-slate-600 font-mono">
              {activeContracts.length} enforcing now
            </span>
          </div>
          <div className="space-y-3">
            {activeContracts.map((cs) => {
              const c = cs.contract;
              return (
                <div
                  key={c.id}
                  className="border border-slate-800 rounded-lg p-4 bg-slate-950/50 space-y-3"
                >
                  <div className="flex items-center space-x-3">
                    <LifecycleBadge lifecycle={cs.lifecycle} />
                    <span className="font-bold text-slate-200 text-sm font-mono">
                      {c.name}
                    </span>
                    <span className="text-slate-600 text-[11px] font-mono">
                      {c.id}
                    </span>
                  </div>

                  {/* Active targets */}
                  {cs.active_targets && cs.active_targets.length > 0 && (
                    <div className="flex flex-wrap gap-2 text-[11px] font-mono">
                      <span className="text-slate-500">targets:</span>
                      {cs.active_targets.map((t) => (
                        <span
                          key={t.pid}
                          className="bg-cyan-950 border border-cyan-900 text-cyan-300 px-2 py-0.5 rounded"
                        >
                          PID {t.pid}
                          {t.name ? ` (${t.name})` : ""}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Actions applied */}
                  <div className="flex flex-wrap gap-2 text-[11px] font-mono">
                    <span className="text-slate-500">actions:</span>
                    {c.actions.map((act, i) => (
                      <span
                        key={i}
                        className="bg-slate-900 border border-slate-700 text-cyan-400 px-2 py-0.5 rounded"
                      >
                        {describeAction(
                          act as Parameters<typeof describeAction>[0],
                        )}
                      </span>
                    ))}
                  </div>

                  {/* Restore condition progress */}
                  {cs.lifecycle === "active" && (
                    <div className="text-[11px] font-mono space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="text-slate-500">restore when:</span>
                        <span className="text-slate-300">
                          {c.restore.metric} {opSymbol(c.restore.operator)}{" "}
                          {String(c.restore.value)}
                        </span>
                        <span className="text-slate-600">
                          for {c.restore.for_seconds}s
                        </span>
                      </div>
                      {cs.restore_raw !== null &&
                        cs.restore_raw !== undefined && (
                          <div className="flex items-center space-x-2">
                            <span className="text-slate-600">condition:</span>
                            <span
                              className={
                                cs.restore_raw
                                  ? "text-emerald-400"
                                  : "text-slate-500"
                              }
                            >
                              {cs.restore_raw ? "MET" : "not met"}
                            </span>
                            {cs.restore_elapsed_seconds !== null &&
                              cs.restore_elapsed_seconds !== undefined &&
                              cs.restore_elapsed_seconds > 0 && (
                                <span className="text-indigo-400">
                                  {cs.restore_elapsed_seconds.toFixed(1)}s /{" "}
                                  {c.restore.for_seconds}s
                                </span>
                              )}
                          </div>
                        )}
                      {cs.activated_at && (
                        <div className="text-slate-600">
                          activated: {formatTimestamp(cs.activated_at)}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Capability summary */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-3">
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-300 font-mono mb-3">
          Linux Capabilities
        </h2>
        <div className="space-y-2">
          <CapabilityRow
            label="Enforcement"
            status={engineStatus?.enforcement_supported ? "ok" : "warn"}
            detail={
              engineStatus?.enforcement_supported
                ? "supported (Linux)"
                : "preview only (non-Linux)"
            }
          />
          <CapabilityRow
            label="cgroups v2"
            status={engineStatus?.cgroup_available ? "ok" : "off"}
            detail={engineStatus?.cgroup_reason || "status unknown"}
          />
          <CapabilityRow
            label="cpu_affinity"
            status={engineStatus?.enforcement_supported ? "ok" : "off"}
            detail={
              engineStatus?.enforcement_supported
                ? "available, usually works without elevated privilege"
                : "unavailable on this platform"
            }
          />
          <CapabilityRow
            label="nice"
            status={engineStatus?.enforcement_supported ? "ok" : "off"}
            detail={
              engineStatus?.enforcement_supported
                ? "available, but restoring to lower values may need CAP_SYS_NICE"
                : "unavailable on this platform"
            }
          />
          <CapabilityRow
            label="suspend/resume"
            status={engineStatus?.enforcement_supported ? "ok" : "off"}
            detail={
              engineStatus?.enforcement_supported
                ? "available (SIGSTOP/SIGCONT)"
                : "unavailable on this platform"
            }
          />
          <CapabilityRow
            label="euid"
            status="ok"
            detail={
              engineStatus?.euid !== null && engineStatus?.euid !== undefined
                ? String(engineStatus.euid)
                : "unknown"
            }
          />
        </div>
      </div>

      {/* Recent policy decisions */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs font-bold uppercase tracking-widest text-slate-300 font-mono">
            Recent Policy Decisions
          </h2>
          <button
            onClick={onNavigateEvents}
            className="text-[11px] text-cyan-400 hover:underline font-mono"
          >
            Full audit log
          </button>
        </div>
        <div className="space-y-0 divide-y divide-slate-800">
          {recentEvents.length > 0 ? (
            recentEvents.map((ev) => (
              <div
                key={ev.seq}
                className="py-2.5 flex items-start space-x-3 text-xs font-mono"
              >
                <span className="text-slate-600 w-10 text-right shrink-0">
                  #{ev.seq}
                </span>
                <SeverityBadge severity={ev.severity} />
                <span className="text-[10px] text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded shrink-0">
                  {ev.type.replace(/_/g, " ")}
                </span>
                <span className="text-slate-300 flex-1 leading-relaxed">
                  {ev.message}
                </span>
                <div className="text-slate-600 text-[10px] space-y-0.5 text-right shrink-0">
                  {ev.contract_id && (
                    <div className="text-slate-500">{ev.contract_id}</div>
                  )}
                  {ev.pid && <div>PID {ev.pid}</div>}
                  <div>{formatTimestamp(ev.timestamp)}</div>
                </div>
              </div>
            ))
          ) : (
            <div className="py-6 text-center text-slate-600 font-mono text-xs">
              No events yet. Start the engine and load contracts.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
