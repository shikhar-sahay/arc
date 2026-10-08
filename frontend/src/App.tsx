import { useEffect, useState, useCallback } from "react";
import {
  ContractStatus,
  EngineStatus,
  ProcessItem,
  ArcEvent,
  SystemTelemetry,
} from "./types";
import { useWebSocket } from "./useWebSocket";
import { api } from "./lib/api";
import { OverviewPage } from "./pages/OverviewPage";
import { ContractsPage } from "./pages/ContractsPage";
import { ProcessesPage } from "./pages/ProcessesPage";
import { EventsPage } from "./pages/EventsPage";

type NavTab = "overview" | "contracts" | "processes" | "events";

const MAX_HISTORY_POINTS = 30;

export default function App() {
  const [tab, setTab] = useState<NavTab>("overview");
  const { wsStatus, lastMessage } = useWebSocket();

  // Engine & telemetry state
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
  const [telemetry, setTelemetry] = useState<SystemTelemetry | null>(null);
  const [cpuHistory, setCpuHistory] = useState<number[]>([]);
  const [memHistory, setMemHistory] = useState<number[]>([]);

  // Contracts state
  const [contracts, setContracts] = useState<ContractStatus[]>([]);
  const [loadIssues, setLoadIssues] = useState<
    Array<{ file: string; error: string }>
  >([]);
  const [contractsLoading, setContractsLoading] = useState(false);

  // Processes state
  const [processes, setProcesses] = useState<ProcessItem[]>([]);
  const [totalProcesses, setTotalProcesses] = useState(0);
  const [procLoading, setProcLoading] = useState(false);

  // Events state
  const [events, setEvents] = useState<ArcEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  // Global banner notification for actions
  const [bannerNotice, setBannerNotice] = useState<string | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  const reportBackendError = useCallback((error: unknown) => {
    const detail = error instanceof Error ? error.message : "request failed";
    setBackendError(
      `Backend unavailable: ${detail}. Displayed data is not live.`,
    );
  }, []);

  // Sync state from WebSocket tick if available
  useEffect(() => {
    if (lastMessage) {
      if (lastMessage.telemetry) {
        const t = lastMessage.telemetry;
        setTelemetry(t);
        setCpuHistory((prev) => {
          const next = [...prev, t.cpu_percent];
          return next.slice(-MAX_HISTORY_POINTS);
        });
        setMemHistory((prev) => {
          const next = [...prev, t.memory_percent];
          return next.slice(-MAX_HISTORY_POINTS);
        });
      }
      if (lastMessage.status) {
        setEngineStatus((prev) =>
          prev
            ? {
                ...prev,
                running: lastMessage.status.running,
                contract_count: lastMessage.status.contract_count,
                active_contracts: lastMessage.status.active_contracts,
                error_contracts: lastMessage.status.error_contracts,
                enforcement_supported: lastMessage.status.enforcement_supported,
                cgroup_available: lastMessage.status.cgroup_available,
                cgroup_reason: lastMessage.status.cgroup_reason,
              }
            : null,
        );
      }
      if (lastMessage.recent_events && lastMessage.recent_events.length > 0) {
        setEvents((prev) => {
          const existingSeqs = new Set(prev.map((e) => e.seq));
          const newEvents = (lastMessage.recent_events as ArcEvent[]).filter(
            (e) => !existingSeqs.has(e.seq),
          );
          if (newEvents.length === 0) return prev;
          const merged = [...newEvents, ...prev];
          merged.sort((a, b) => b.seq - a.seq);
          return merged.slice(0, 300);
        });
      }
    }
  }, [lastMessage]);

  // Fetch engine status
  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.getStatus();
      setEngineStatus(data);
      setBackendError(null);
    } catch (error) {
      setEngineStatus(null);
      reportBackendError(error);
    }
  }, [reportBackendError]);

  // Fetch telemetry
  const fetchTelemetry = useCallback(async () => {
    try {
      const data = await api.getSystem();
      setTelemetry(data);
      setCpuHistory((prev) => {
        const next = [...prev, data.cpu_percent];
        return next.slice(-MAX_HISTORY_POINTS);
      });
      setMemHistory((prev) => {
        const next = [...prev, data.memory_percent];
        return next.slice(-MAX_HISTORY_POINTS);
      });
    } catch (error) {
      setTelemetry(null);
      reportBackendError(error);
    }
  }, [reportBackendError]);

  // Fetch contracts
  const fetchContracts = useCallback(async () => {
    setContractsLoading(true);
    try {
      const data = await api.getContracts();
      setContracts(data.contracts || []);
      setLoadIssues(data.load_errors || []);
    } catch (error) {
      setContracts([]);
      setLoadIssues([]);
      reportBackendError(error);
    } finally {
      setContractsLoading(false);
    }
  }, [reportBackendError]);

  // Fetch processes
  const fetchProcesses = useCallback(async () => {
    setProcLoading(true);
    try {
      const data = await api.getProcesses(300);
      setProcesses(data.processes || []);
      setTotalProcesses(
        data.total_observed ?? data.count ?? data.processes.length,
      );
    } catch (error) {
      setProcesses([]);
      setTotalProcesses(0);
      reportBackendError(error);
    } finally {
      setProcLoading(false);
    }
  }, [reportBackendError]);

  // Fetch events
  const fetchEvents = useCallback(async () => {
    setEventsLoading(true);
    try {
      const data = await api.getEvents(200);
      setEvents(data.events || []);
    } catch (error) {
      setEvents([]);
      reportBackendError(error);
    } finally {
      setEventsLoading(false);
    }
  }, [reportBackendError]);

  // Initial load
  useEffect(() => {
    fetchStatus();
    fetchTelemetry();
    fetchContracts();
    fetchEvents();
  }, [fetchStatus, fetchTelemetry, fetchContracts, fetchEvents]);

  // Tab-specific polling refresh fallback
  useEffect(() => {
    if (tab === "processes") {
      fetchProcesses();
      const id = setInterval(fetchProcesses, 4000);
      return () => clearInterval(id);
    }
    if (tab === "events") {
      fetchEvents();
      const id = setInterval(fetchEvents, 3000);
      return () => clearInterval(id);
    }
    if (tab === "contracts") {
      fetchContracts();
      const id = setInterval(fetchContracts, 3000);
      return () => clearInterval(id);
    }
    if (tab === "overview") {
      const id = setInterval(() => {
        fetchStatus();
        fetchTelemetry();
      }, 4000);
      return () => clearInterval(id);
    }
  }, [
    tab,
    fetchProcesses,
    fetchEvents,
    fetchContracts,
    fetchStatus,
    fetchTelemetry,
  ]);

  // Navigation handlers
  const handleNavigateEvents = () => setTab("events");
  const handleNavigateContracts = () => setTab("contracts");

  // Quick stats derived
  const activeCount =
    engineStatus?.active_contracts ??
    contracts.filter(
      (c) => c.lifecycle === "active" || c.lifecycle === "activating",
    ).length;
  const errorCount =
    engineStatus?.error_contracts ??
    contracts.filter((c) => c.lifecycle === "error").length;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans antialiased selection:bg-cyan-500 selection:text-slate-950">
      {/* HEADER */}
      <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Brand / Logo */}
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 rounded bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center font-mono font-bold text-slate-950 text-base shadow-sm">
                A
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-bold tracking-tight text-slate-100 font-mono text-sm">
                    ARC
                  </span>
                  <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 font-mono border border-slate-700">
                    Engine
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 font-mono">
                  Adaptive Resource Contract Engine
                </div>
              </div>
            </div>

            {/* Status indicators */}
            <div className="flex items-center space-x-3">
              {/* WebSocket Status Pill */}
              <div
                className={`flex items-center space-x-1.5 px-2.5 py-1 rounded text-xs font-mono border ${
                  wsStatus === "connected"
                    ? "bg-emerald-950/60 border-emerald-800 text-emerald-300"
                    : wsStatus === "reconnecting"
                      ? "bg-amber-950/60 border-amber-800 text-amber-300"
                      : "bg-rose-950/60 border-rose-800 text-rose-300"
                }`}
                title={
                  wsStatus === "connected"
                    ? "Real-time engine stream active"
                    : wsStatus === "reconnecting"
                      ? "Reconnecting to engine WebSocket..."
                      : "WebSocket disconnected; polling active"
                }
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    wsStatus === "connected"
                      ? "bg-emerald-400 animate-pulse"
                      : wsStatus === "reconnecting"
                        ? "bg-amber-400 animate-pulse"
                        : "bg-rose-400"
                  }`}
                />
                <span className="capitalize">{wsStatus}</span>
              </div>

              {/* Engine Enforcement Pill */}
              {engineStatus && (
                <div
                  className={`hidden sm:flex items-center space-x-1.5 px-2.5 py-1 rounded text-xs font-mono border ${
                    engineStatus.enforcement_supported
                      ? "bg-cyan-950/50 border-cyan-800 text-cyan-300"
                      : "bg-slate-900 border-slate-700 text-slate-400"
                  }`}
                  title={
                    engineStatus.enforcement_supported
                      ? "Linux kernel enforcement active (nice, affinity, cgroups, signals)"
                      : "Read-only mode (non-Linux platform or unprivileged)"
                  }
                >
                  <span className="uppercase text-[10px]">
                    {engineStatus.platform}
                  </span>
                  <span>•</span>
                  <span>
                    {engineStatus.enforcement_supported
                      ? "Enforcing"
                      : "Read-Only"}
                  </span>
                </div>
              )}

              {/* Active Contracts Badge */}
              {activeCount > 0 && (
                <button
                  onClick={() => setTab("contracts")}
                  className="px-2.5 py-1 rounded text-xs font-mono bg-cyan-950 border border-cyan-700 text-cyan-300 font-bold hover:bg-cyan-900 transition"
                  title="Active contracts currently enforcing"
                >
                  {activeCount} Active
                </button>
              )}

              {/* Error Contracts Badge */}
              {errorCount > 0 && (
                <button
                  onClick={() => setTab("contracts")}
                  className="px-2.5 py-1 rounded text-xs font-mono bg-rose-950 border border-rose-700 text-rose-300 font-bold hover:bg-rose-900 transition"
                  title="Contracts in error latch state requiring reset"
                >
                  {errorCount} Error
                </button>
              )}
            </div>
          </div>

          {/* Navigation Bar */}
          <nav className="flex space-x-1 -mb-px">
            <button
              onClick={() => setTab("overview")}
              className={`px-4 py-2.5 text-xs font-mono font-medium border-b-2 transition ${
                tab === "overview"
                  ? "border-cyan-400 text-cyan-300 bg-slate-800/30"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700"
              }`}
            >
              Overview
            </button>
            <button
              onClick={() => setTab("contracts")}
              className={`px-4 py-2.5 text-xs font-mono font-medium border-b-2 transition flex items-center space-x-1.5 ${
                tab === "contracts"
                  ? "border-cyan-400 text-cyan-300 bg-slate-800/30"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700"
              }`}
            >
              <span>Contracts</span>
              {contracts.length > 0 && (
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700">
                  {contracts.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setTab("processes")}
              className={`px-4 py-2.5 text-xs font-mono font-medium border-b-2 transition flex items-center space-x-1.5 ${
                tab === "processes"
                  ? "border-cyan-400 text-cyan-300 bg-slate-800/30"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700"
              }`}
            >
              <span>Processes</span>
              {totalProcesses > 0 && (
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700">
                  {totalProcesses}
                </span>
              )}
            </button>
            <button
              onClick={() => setTab("events")}
              className={`px-4 py-2.5 text-xs font-mono font-medium border-b-2 transition flex items-center space-x-1.5 ${
                tab === "events"
                  ? "border-cyan-400 text-cyan-300 bg-slate-800/30"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700"
              }`}
            >
              <span>Audit Log</span>
              {events.length > 0 && (
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700">
                  {events.length}
                </span>
              )}
            </button>
          </nav>
        </div>
      </header>

      {/* Notice Banner */}
      {bannerNotice && (
        <div className="bg-cyan-950/80 border-b border-cyan-800 text-cyan-200 px-4 py-2 text-xs font-mono flex items-center justify-between">
          <span>{bannerNotice}</span>
          <button
            onClick={() => setBannerNotice(null)}
            className="text-cyan-400 hover:text-cyan-200"
          >
            ✕
          </button>
        </div>
      )}

      {backendError && (
        <div className="bg-rose-950/90 border-b border-rose-800 text-rose-200 px-4 py-2 text-xs font-mono break-words">
          {backendError}
        </div>
      )}

      {/* MAIN CONTENT AREA */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {tab === "overview" && (
          <OverviewPage
            engineStatus={engineStatus}
            telemetry={telemetry}
            cpuHistory={cpuHistory}
            memHistory={memHistory}
            contracts={contracts}
            recentEvents={events}
            wsStatus={wsStatus}
            onNavigateEvents={handleNavigateEvents}
            onNavigateContracts={handleNavigateContracts}
          />
        )}

        {tab === "contracts" && (
          <ContractsPage
            contracts={contracts}
            loadIssues={loadIssues}
            loading={contractsLoading}
            onRefresh={fetchContracts}
          />
        )}

        {tab === "processes" && (
          <ProcessesPage
            processes={processes}
            totalObserved={totalProcesses}
            loading={procLoading}
            onRefresh={fetchProcesses}
          />
        )}

        {tab === "events" && (
          <EventsPage
            events={events}
            loading={eventsLoading}
            onRefresh={fetchEvents}
          />
        )}
      </main>

      {/* FOOTER */}
      <footer className="border-t border-slate-900 bg-slate-950 py-4 px-4 text-center text-xs font-mono text-slate-600">
        ARC • Linux user-space resource contract engine • Headless-capable core
      </footer>
    </div>
  );
}
