import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Gauge, Play, RotateCcw, Shield, Square } from "lucide-react";
import { MiniSparkline } from "../components/MiniSparkline";
import { api } from "../lib/api";
import { formatCpuAffinity } from "../lib/utils";
import { ResourceLabState, SystemTelemetry } from "../types";

const HISTORY_LIMIT = 90;

interface Props {
  telemetry: SystemTelemetry | null;
  cpuHistory: number[];
}

export function ResourceLabPage({ telemetry, cpuHistory }: Props) {
  const [state, setState] = useState<ResourceLabState | null>(null);
  const [workers, setWorkers] = useState(4);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [foregroundHistory, setForegroundHistory] = useState<number[]>([]);
  const [backgroundHistory, setBackgroundHistory] = useState<number[]>([]);

  const refresh = useCallback(async () => {
    try {
      const next = await api.getResourceLab();
      setState(next);
      setForegroundHistory((old) =>
        [...old, next.foreground_operations_per_second].slice(-HISTORY_LIMIT),
      );
      setBackgroundHistory((old) =>
        [...old, next.background_operations_per_second].slice(-HISTORY_LIMIT),
      );
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Resource Lab failed",
      );
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const act = async (operation: () => Promise<ResourceLabState>) => {
    setBusy(true);
    try {
      setState(await operation());
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Operation failed");
    } finally {
      setBusy(false);
    }
  };
  const running = state?.state !== "stopped";
  const contract = state?.contract;
  const foreground =
    state?.workloads.filter((item) => item.role === "foreground") ?? [];
  const background =
    state?.workloads.filter((item) => item.role === "background") ?? [];
  const allocationChanged = useMemo(
    () =>
      background.some(
        (item) => item.affinity.join() !== item.original_affinity.join(),
      ),
    [background],
  );

  return (
    <main className="page resource-lab">
      <header className="page-header">
        <div>
          <div className="page-kicker">Controlled Linux Experiment</div>
          <h1 className="page-title">Resource Lab</h1>
          <p className="page-description">
            Run measured foreground and background work, then let a real ARC
            contract isolate contention and restore the exact kernel state.
          </p>
        </div>
        <span className={`badge ${running ? "green" : ""}`}>
          {state?.supported === false
            ? "Linux Required"
            : (state?.state ?? "Loading")}
        </span>
      </header>

      {error && <div className="notice error">{error}</div>}
      <section className="lab-controls" aria-label="Scenario controls">
        <label>
          Background Workers
          <input
            className="field"
            type="number"
            min={1}
            max={16}
            value={workers}
            disabled={running || busy}
            onChange={(event) => setWorkers(Number(event.target.value))}
          />
        </label>
        <button
          className="button primary"
          disabled={running || busy}
          onClick={() => void act(() => api.startResourceLab(workers))}
        >
          <Play size={13} /> Start Scenario
        </button>
        <button
          className="button"
          disabled={!running || busy}
          onClick={() => void act(() => api.setResourceLabPressure(true))}
        >
          <Activity size={13} /> Apply Pressure
        </button>
        <button
          className="button"
          disabled={!running || busy}
          onClick={() => void act(() => api.setResourceLabPressure(false))}
        >
          <RotateCcw size={13} /> Lower Pressure
        </button>
        <button
          className="button"
          disabled={!running || busy || contract?.contract.enabled}
          onClick={() => void act(() => api.setResourceLabPolicy(true))}
        >
          <Shield size={13} /> Enable Policy
        </button>
        <button
          className="button danger"
          disabled={!running || busy}
          onClick={() => void act(() => api.stopResourceLab())}
        >
          <Square size={13} /> Stop Scenario
        </button>
      </section>

      <div className="lab-summary">
        <div>
          <span>System CPU</span>
          <strong>
            {telemetry ? `${telemetry.cpu_percent.toFixed(1)}%` : "unavailable"}
          </strong>
        </div>
        <div>
          <span>Foreground Rate</span>
          <strong>
            {Math.round(
              state?.foreground_operations_per_second ?? 0,
            ).toLocaleString()}{" "}
            ops/s
          </strong>
        </div>
        <div>
          <span>Background Rate</span>
          <strong>
            {Math.round(
              state?.background_operations_per_second ?? 0,
            ).toLocaleString()}{" "}
            ops/s
          </strong>
        </div>
        <div>
          <span>Contract</span>
          <strong>{contract?.lifecycle ?? "not installed"}</strong>
        </div>
        <div>
          <span>Kernel Allocation</span>
          <strong>
            {allocationChanged
              ? `restricted to CPU ${state?.policy_cpu}`
              : "original"}
          </strong>
        </div>
      </div>

      <div className="lab-grid">
        <section className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <Gauge size={14} /> Workload Performance
            </div>
            <span className="panel-subtle">
              Measured worker operations per second
            </span>
          </div>
          <div className="lab-chart-row">
            <div>
              <span>System CPU, 0 to 100%</span>
              <MiniSparkline data={cpuHistory} max={100} color="var(--cpu)" />
            </div>
            <div>
              <span>Foreground</span>
              <MiniSparkline
                data={foregroundHistory}
                max={Math.max(...foregroundHistory, 1)}
                color="var(--cpu)"
              />
            </div>
            <div>
              <span>Background</span>
              <MiniSparkline
                data={backgroundHistory}
                max={Math.max(...backgroundHistory, 1)}
                color="var(--memory)"
              />
            </div>
          </div>
        </section>
        <section className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <Shield size={14} /> Contract Lifecycle
            </div>
          </div>
          <div className="panel-body lab-lifecycle">
            <strong>
              {contract?.contract.name ??
                "Start the scenario to install the policy"}
            </strong>
            {contract && (
              <>
                <span>
                  Trigger: CPU &gt; {String(contract.contract.trigger.value)}%
                  for {contract.contract.trigger.for_seconds}s
                </span>
                <span>
                  Progress: {Math.round(contract.trigger_elapsed_seconds ?? 0)}s
                </span>
                <span>
                  Targets:{" "}
                  {contract.matched_pids.length
                    ? contract.matched_pids.join(", ")
                    : "none"}
                </span>
                <span>
                  Action: background affinity to CPU {state?.policy_cpu}
                </span>
                <span>
                  Restore: CPU &lt; {String(contract.contract.restore.value)}%
                  for {contract.contract.restore.for_seconds}s
                </span>
                {contract.last_error && (
                  <span className="error-text">{contract.last_error}</span>
                )}
              </>
            )}
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div className="panel-title">Kernel-Verified Workloads</div>
          <span className="panel-subtle">
            Actual PIDs, affinity and nice values
          </span>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Role</th>
                <th>PID</th>
                <th>CPU</th>
                <th>Throughput</th>
                <th>Allowed CPUs</th>
                <th>Original CPUs</th>
                <th>Nice</th>
              </tr>
            </thead>
            <tbody>
              {[...foreground, ...background].map((item) => (
                <tr key={item.pid}>
                  <td>{item.role}</td>
                  <td className="mono">{item.pid}</td>
                  <td className="mono">{item.cpu_percent.toFixed(1)}%</td>
                  <td className="mono">
                    {Math.round(item.operations_per_second).toLocaleString()}{" "}
                    ops/s
                  </td>
                  <td className="mono">{formatCpuAffinity(item.affinity)}</td>
                  <td className="mono">
                    {formatCpuAffinity(item.original_affinity)}
                  </td>
                  <td className="mono">{item.nice}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel lab-workbench">
        <div className="panel-header">
          <div className="panel-title">Resource-Control Workbench</div>
          <span className="panel-subtle">
            Restricted to Resource Lab-owned processes
          </span>
        </div>
        <div className="lab-workbench-grid">
          <div>
            <strong>CPU Affinity</strong>
            <span>
              The installed policy narrows background workers and restores their
              captured CPU sets.
            </span>
          </div>
          <div>
            <strong>Process Suspension</strong>
            <span>
              Load the disabled resource-lab-suspend example in Contracts to verify
              SIGSTOP and SIGCONT.
            </span>
          </div>
          <div>
            <strong>Conflict Protection</strong>
            <span>
              Load resource-lab-affinity-conflict to observe resource_conflict
              deferral without a kernel overwrite.
            </span>
          </div>
        </div>
      </section>
    </main>
  );
}
