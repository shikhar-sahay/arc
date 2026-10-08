import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ClipboardList,
  Cpu,
  FileCode2,
  LayoutDashboard,
} from "lucide-react";
import {
  ArcEvent,
  ContractStatus,
  EngineStatus,
  ProcessItem,
  SystemTelemetry,
} from "./types";
import { useWebSocket } from "./useWebSocket";
import { api } from "./lib/api";
import { OverviewPage } from "./pages/OverviewPage";
import { ContractsPage } from "./pages/ContractsPage";
import { ProcessesPage } from "./pages/ProcessesPage";
import { EventsPage } from "./pages/EventsPage";

type NavTab = "overview" | "contracts" | "processes" | "events";
const MAX_HISTORY_POINTS = 60;

export default function App() {
  const [tab, setTab] = useState<NavTab>("overview");
  const { wsStatus, lastMessage } = useWebSocket();
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
  const [telemetry, setTelemetry] = useState<SystemTelemetry | null>(null);
  const [cpuHistory, setCpuHistory] = useState<number[]>([]);
  const [memHistory, setMemHistory] = useState<number[]>([]);
  const [contracts, setContracts] = useState<ContractStatus[]>([]);
  const [loadIssues, setLoadIssues] = useState<
    Array<{ file: string; error: string }>
  >([]);
  const [contractsLoading, setContractsLoading] = useState(false);
  const [processes, setProcesses] = useState<ProcessItem[]>([]);
  const [totalProcesses, setTotalProcesses] = useState(0);
  const [procLoading, setProcLoading] = useState(false);
  const [events, setEvents] = useState<ArcEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  const appendTelemetry = useCallback((sample: SystemTelemetry) => {
    setTelemetry(sample);
    setCpuHistory((prev) =>
      [...prev, sample.cpu_percent].slice(-MAX_HISTORY_POINTS),
    );
    setMemHistory((prev) =>
      [...prev, sample.memory_percent].slice(-MAX_HISTORY_POINTS),
    );
  }, []);

  const fail = useCallback((error: unknown) => {
    setBackendError(
      error instanceof Error ? error.message : "Backend request failed",
    );
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.telemetry) appendTelemetry(lastMessage.telemetry);
    setEngineStatus((previous) =>
      previous ? { ...previous, ...lastMessage.status } : null,
    );
    if (lastMessage.recent_events.length) {
      setEvents((previous) => {
        const bySequence = new Map(previous.map((event) => [event.seq, event]));
        for (const event of lastMessage.recent_events as ArcEvent[])
          bySequence.set(event.seq, event);
        return [...bySequence.values()]
          .sort((a, b) => b.seq - a.seq)
          .slice(0, 300);
      });
    }
  }, [lastMessage, appendTelemetry]);

  const fetchStatus = useCallback(async () => {
    try {
      setEngineStatus(await api.getStatus());
      setBackendError(null);
    } catch (error) {
      setEngineStatus(null);
      fail(error);
    }
  }, [fail]);
  const fetchTelemetry = useCallback(async () => {
    try {
      appendTelemetry(await api.getSystem());
      setBackendError(null);
    } catch (error) {
      setTelemetry(null);
      fail(error);
    }
  }, [appendTelemetry, fail]);
  const fetchContracts = useCallback(async () => {
    setContractsLoading(true);
    try {
      const data = await api.getContracts();
      setContracts(data.contracts);
      setLoadIssues(data.load_errors);
      setBackendError(null);
    } catch (error) {
      setContracts([]);
      setLoadIssues([]);
      fail(error);
    } finally {
      setContractsLoading(false);
    }
  }, [fail]);
  const fetchProcesses = useCallback(async () => {
    setProcLoading(true);
    try {
      const data = await api.getProcesses(300);
      setProcesses(data.processes);
      setTotalProcesses(data.total_observed);
      setBackendError(null);
    } catch (error) {
      setProcesses([]);
      setTotalProcesses(0);
      fail(error);
    } finally {
      setProcLoading(false);
    }
  }, [fail]);
  const fetchEvents = useCallback(async () => {
    setEventsLoading(true);
    try {
      const data = await api.getEvents(200);
      setEvents(data.events);
      setBackendError(null);
    } catch (error) {
      setEvents([]);
      fail(error);
    } finally {
      setEventsLoading(false);
    }
  }, [fail]);

  useEffect(() => {
    void Promise.all([
      fetchStatus(),
      fetchTelemetry(),
      fetchContracts(),
      fetchEvents(),
      fetchProcesses(),
    ]);
  }, [
    fetchStatus,
    fetchTelemetry,
    fetchContracts,
    fetchEvents,
    fetchProcesses,
  ]);
  useEffect(() => {
    const refresh = () => {
      if (tab === "overview")
        void Promise.all([fetchStatus(), fetchTelemetry(), fetchProcesses()]);
      if (tab === "contracts") void fetchContracts();
      if (tab === "processes") void fetchProcesses();
      if (tab === "events") void fetchEvents();
    };
    const timer = window.setInterval(refresh, tab === "overview" ? 4000 : 5000);
    return () => window.clearInterval(timer);
  }, [
    tab,
    fetchStatus,
    fetchTelemetry,
    fetchContracts,
    fetchProcesses,
    fetchEvents,
  ]);

  const nav = [
    { id: "overview" as const, label: "Overview", icon: LayoutDashboard },
    {
      id: "contracts" as const,
      label: "Contracts",
      icon: FileCode2,
      count: contracts.length,
    },
    {
      id: "processes" as const,
      label: "Processes",
      icon: Cpu,
      count: totalProcesses,
    },
    {
      id: "events" as const,
      label: "Audit Log",
      icon: ClipboardList,
      count: events.length,
    },
  ];
  const stale = !telemetry || now / 1000 - telemetry.timestamp > 12;
  const connectionLabel = backendError
    ? "Backend unavailable"
    : wsStatus === "connected"
      ? "Live stream connected"
      : wsStatus === "reconnecting"
        ? "Stream reconnecting"
        : "Stream disconnected";

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <div className="brand-mark">ARC</div>
          <div>
            <strong>ARC Engine</strong>
            <span>Resource policy control</span>
          </div>
        </div>
        <div className="nav-label">Workspace</div>
        <nav className="nav-list">
          {nav.map(({ id, label, icon: Icon, count }) => (
            <button
              key={id}
              className={`nav-item ${tab === id ? "active" : ""}`}
              onClick={() => setTab(id)}
              aria-current={tab === id ? "page" : undefined}
            >
              <Icon size={16} strokeWidth={1.8} />
              <span>{label}</span>
              {count ? <span className="count">{count}</span> : null}
            </button>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-status">
          <div className="status-line">
            <span
              className={`status-dot ${backendError ? "bad" : wsStatus === "connected" ? "ok" : "warn"}`}
            />
            <span>{connectionLabel}</span>
          </div>
          <div className="status-line">
            <Activity size={13} />
            <span>
              {engineStatus?.enforcement_supported
                ? "Linux enforcement supported"
                : engineStatus
                  ? `${engineStatus.platform} observation mode`
                  : "Engine state unavailable"}
            </span>
          </div>
        </div>
      </aside>
      <div className="main-column">
        <div className="mobile-bar">
          <div className="mobile-brand">
            <div className="brand-mark">ARC</div>ARC Engine
          </div>
          <span className={`status-dot ${backendError ? "bad" : "ok"}`} />
        </div>
        {backendError && (
          <div className="notice error" style={{ margin: "12px 14px 0" }}>
            Backend unavailable: {backendError}. Cached values are hidden.
          </div>
        )}
        {tab === "overview" && (
          <OverviewPage
            engineStatus={engineStatus}
            telemetry={telemetry}
            cpuHistory={cpuHistory}
            memHistory={memHistory}
            contracts={contracts}
            recentEvents={events}
            processes={processes}
            wsStatus={wsStatus}
            stale={stale}
            onNavigateEvents={() => setTab("events")}
            onNavigateContracts={() => setTab("contracts")}
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
      </div>
    </div>
  );
}
