import React, { useEffect, useState, useCallback } from "react";
import {
  ContractStatus,
  EngineStatus,
  ProcessItem,
  ArcEvent,
  SystemTelemetry,
  Contract,
  Action,
} from "./types";
import { useWebSocket } from "./useWebSocket";

type NavTab = "overview" | "contracts" | "processes" | "events";

export default function App() {
  const [tab, setTab] = useState<NavTab>("overview");
  const { connected, lastMessage } = useWebSocket();

  // Engine & telemetry state
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
  const [telemetry, setTelemetry] = useState<SystemTelemetry | null>(null);

  // Contracts state
  const [contracts, setContracts] = useState<ContractStatus[]>([]);
  const [loadIssues, setLoadIssues] = useState<
    Array<{ file: string; error: string }>
  >([]);
  const [contractsLoading, setContractsLoading] = useState(false);

  // Processes state
  const [processes, setProcesses] = useState<ProcessItem[]>([]);
  const [procFilter, setProcFilter] = useState("");
  const [onlyArcManaged, setOnlyArcManaged] = useState(false);
  const [procLoading, setProcLoading] = useState(false);

  // Events state
  const [events, setEvents] = useState<ArcEvent[]>([]);
  const [eventFilter, setEventFilter] = useState("");
  const [eventSeverity, setEventSeverity] = useState("all");
  const [eventsLoading, setEventsLoading] = useState(false);

  // Contract form modal / state
  const [showModal, setShowModal] = useState(false);
  const [modalMode, setModalMode] = useState<"create" | "edit" | "yaml">(
    "create",
  );
  const [selectedContract, setSelectedContract] = useState<Contract | null>(
    null,
  );
  const [rawYaml, setRawYaml] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  // Form fields
  const [formId, setFormId] = useState("");
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formExecutable, setFormExecutable] = useState("");
  const [formCommand, setFormCommand] = useState("");
  const [formTriggerMetric, setFormTriggerMetric] =
    useState("system.cpu.percent");
  const [formTriggerOp, setFormTriggerOp] = useState("gt");
  const [formTriggerVal, setFormTriggerVal] = useState("75");
  const [formTriggerSec, setFormTriggerSec] = useState("5");
  const [formActionType, setFormActionType] = useState<
    "nice" | "cpu_affinity" | "suspend" | "resume" | "cpu_quota"
  >("nice");
  const [formNiceVal, setFormNiceVal] = useState("10");
  const [formAffinityCpus, setFormAffinityCpus] = useState("0");
  const [formQuotaVal, setFormQuotaVal] = useState("50");
  const [formRestoreMetric, setFormRestoreMetric] =
    useState("system.cpu.percent");
  const [formRestoreOp, setFormRestoreOp] = useState("lt");
  const [formRestoreVal, setFormRestoreVal] = useState("55");
  const [formRestoreSec, setFormRestoreSec] = useState("5");

  // Sync state from WebSocket tick if available
  useEffect(() => {
    if (lastMessage) {
      if (lastMessage.telemetry) {
        setTelemetry(lastMessage.telemetry);
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
    }
  }, [lastMessage]);

  // Fetch engine status
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/status");
      if (res.ok) {
        const data = (await res.json()) as EngineStatus;
        setEngineStatus(data);
      }
    } catch {
      // Ignored
    }
  }, []);

  // Fetch telemetry
  const fetchTelemetry = useCallback(async () => {
    try {
      const res = await fetch("/api/system");
      if (res.ok) {
        const data = (await res.json()) as SystemTelemetry;
        setTelemetry(data);
      }
    } catch {
      // Ignored
    }
  }, []);

  // Fetch contracts
  const fetchContracts = useCallback(async () => {
    setContractsLoading(true);
    try {
      const res = await fetch("/api/contracts");
      if (res.ok) {
        const data = await res.json();
        setContracts(data.contracts || []);
        setLoadIssues(data.load_errors || []);
      }
    } catch {
      // Ignored
    } finally {
      setContractsLoading(false);
    }
  }, []);

  // Fetch processes
  const fetchProcesses = useCallback(async () => {
    setProcLoading(true);
    try {
      const res = await fetch("/api/processes?limit=300");
      if (res.ok) {
        const data = await res.json();
        setProcesses(data.processes || []);
      }
    } catch {
      // Ignored
    } finally {
      setProcLoading(false);
    }
  }, []);

  // Fetch events
  const fetchEvents = useCallback(async () => {
    setEventsLoading(true);
    try {
      const res = await fetch("/api/events?limit=200");
      if (res.ok) {
        const data = await res.json();
        setEvents(data.events || []);
      }
    } catch {
      // Ignored
    } finally {
      setEventsLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchStatus();
    fetchTelemetry();
    fetchContracts();
  }, [fetchStatus, fetchTelemetry, fetchContracts]);

  // Polling fallback when tab is active
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

  // Toggle contract enabled
  const toggleEnabled = async (contractId: string, current: boolean) => {
    try {
      const res = await fetch(`/api/contracts/${contractId}/enabled`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !current }),
      });
      if (res.ok) {
        fetchContracts();
      }
    } catch {
      // Ignored
    }
  };

  // Reset error contract
  const resetContract = async (contractId: string) => {
    try {
      const res = await fetch(`/api/contracts/${contractId}/reset`, {
        method: "POST",
      });
      if (res.ok) {
        fetchContracts();
      }
    } catch {
      // Ignored
    }
  };

  // Delete contract
  const deleteContract = async (contractId: string) => {
    if (!confirm(`Delete contract "${contractId}" from disk?`)) return;
    try {
      const res = await fetch(`/api/contracts/${contractId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        fetchContracts();
      } else {
        const err = await res.json();
        alert(err.detail || "Delete failed");
      }
    } catch {
      alert("Delete request failed");
    }
  };

  // Reload engine from disk
  const reloadFromDisk = async () => {
    try {
      const res = await fetch("/api/engine/reload", { method: "POST" });
      if (res.ok) {
        fetchContracts();
        fetchStatus();
      }
    } catch {
      // Ignored
    }
  };

  // Open modal for Create
  const openCreateModal = () => {
    setModalMode("create");
    setSelectedContract(null);
    setFormError(null);
    setFormId("");
    setFormName("");
    setFormDesc("");
    setFormExecutable("python");
    setFormCommand("");
    setFormTriggerMetric("system.cpu.percent");
    setFormTriggerOp("gt");
    setFormTriggerVal("75");
    setFormTriggerSec("5");
    setFormActionType("nice");
    setFormNiceVal("10");
    setFormAffinityCpus("0");
    setFormQuotaVal("50");
    setFormRestoreMetric("system.cpu.percent");
    setFormRestoreOp("lt");
    setFormRestoreVal("55");
    setFormRestoreSec("5");
    setShowModal(true);
  };

  // Open modal for Edit
  const openEditModal = (cs: ContractStatus) => {
    const c = cs.contract;
    setModalMode("edit");
    setSelectedContract(c);
    setFormError(null);
    setFormId(c.id);
    setFormName(c.name);
    setFormDesc(c.description || "");
    setFormExecutable(c.target.match.executable || "");
    setFormCommand(c.target.match.command_contains || "");
    setFormTriggerMetric(c.trigger.metric);
    setFormTriggerOp(c.trigger.operator);
    setFormTriggerVal(String(c.trigger.value));
    setFormTriggerSec(String(c.trigger.for_seconds));

    const act = c.actions[0];
    if (act) {
      setFormActionType(act.type);
      if (act.type === "nice") setFormNiceVal(String(act.value));
      if (act.type === "cpu_affinity") setFormAffinityCpus(act.cpus.join(", "));
      if (act.type === "cpu_quota") setFormQuotaVal(String(act.quota_percent));
    }

    setFormRestoreMetric(c.restore.metric);
    setFormRestoreOp(c.restore.operator);
    setFormRestoreVal(String(c.restore.value));
    setFormRestoreSec(String(c.restore.for_seconds));
    setShowModal(true);
  };

  // Open modal for View YAML
  const openYamlModal = (c: Contract) => {
    setModalMode("yaml");
    setSelectedContract(c);
    setRawYaml(JSON.stringify(c, null, 2));
    setShowModal(true);
  };

  // Submit contract form
  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    let actionsObj: Action[] = [];
    if (formActionType === "nice") {
      actionsObj = [{ type: "nice", value: parseInt(formNiceVal, 10) }];
    } else if (formActionType === "cpu_affinity") {
      const cpus = formAffinityCpus
        .split(",")
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !isNaN(n));
      actionsObj = [{ type: "cpu_affinity", cpus }];
    } else if (formActionType === "suspend") {
      actionsObj = [{ type: "suspend" }];
    } else if (formActionType === "resume") {
      actionsObj = [{ type: "resume" }];
    } else if (formActionType === "cpu_quota") {
      actionsObj = [
        { type: "cpu_quota", quota_percent: parseFloat(formQuotaVal) },
      ];
    }

    const payload = {
      version: 1,
      id: formId.trim(),
      name: formName.trim(),
      description: formDesc.trim() || null,
      enabled: true,
      target: {
        type: "process",
        match: {
          executable: formExecutable.trim() || null,
          command_contains: formCommand.trim() || null,
        },
      },
      trigger: {
        metric: formTriggerMetric,
        operator: formTriggerOp,
        value: parseFloat(formTriggerVal),
        for_seconds: parseFloat(formTriggerSec),
      },
      actions: actionsObj,
      restore: {
        metric: formRestoreMetric,
        operator: formRestoreOp,
        value: parseFloat(formRestoreVal),
        for_seconds: parseFloat(formRestoreSec),
      },
    };

    // Client/Server validation
    try {
      const valRes = await fetch("/api/contracts/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const valData = await valRes.json();
      if (!valData.valid) {
        setFormError(valData.error || "Validation failed");
        return;
      }
    } catch {
      setFormError("Validation endpoint unreachable");
      return;
    }

    // Save
    try {
      const url =
        modalMode === "create"
          ? "/api/contracts"
          : `/api/contracts/${selectedContract?.id}`;
      const method = modalMode === "create" ? "POST" : "PUT";

      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        setFormError(err.detail || "Save failed");
        return;
      }

      setShowModal(false);
      fetchContracts();
    } catch {
      setFormError("Network error while saving contract");
    }
  };

  // Filtered processes
  const filteredProcesses = processes.filter((p) => {
    if (onlyArcManaged && !p.arc_managed) return false;
    if (!procFilter) return true;
    const q = procFilter.toLowerCase();
    const pidStr = String(p.pid);
    const nameStr = (p.name || "").toLowerCase();
    const cmdStr = (p.cmdline || "").toLowerCase();
    return pidStr.includes(q) || nameStr.includes(q) || cmdStr.includes(q);
  });

  // Filtered events
  const filteredEvents = events.filter((ev) => {
    if (
      eventSeverity !== "all" &&
      ev.severity.toLowerCase() !== eventSeverity.toLowerCase()
    ) {
      return false;
    }
    if (!eventFilter) return true;
    const q = eventFilter.toLowerCase();
    return (
      ev.type.toLowerCase().includes(q) ||
      ev.message.toLowerCase().includes(q) ||
      (ev.contract_id || "").toLowerCase().includes(q) ||
      String(ev.pid || "").includes(q)
    );
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-cyan-900 selection:text-cyan-100">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-20 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <span className="text-xl font-bold tracking-wider text-cyan-400 font-mono">
              ARC
            </span>
            <span className="text-xs text-slate-400 uppercase tracking-widest px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
              Policy Engine
            </span>
          </div>
          <div className="h-4 w-px bg-slate-800" />
          <nav className="flex space-x-1">
            {(["overview", "contracts", "processes", "events"] as NavTab[]).map(
              (t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                    tab === t
                      ? "bg-slate-800 text-cyan-300 border border-slate-700"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                  }`}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ),
            )}
          </nav>
        </div>

        {/* Global Live Indicators */}
        <div className="flex items-center space-x-4 text-xs font-mono">
          <div className="flex items-center space-x-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                connected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"
              }`}
            />
            <span className="text-slate-400">
              {connected ? "LIVE WS" : "DISCONNECTED"}
            </span>
          </div>
          <div className="h-3 w-px bg-slate-800" />
          <div className="text-slate-400">
            ENGINE:{" "}
            <span
              className={
                engineStatus?.running
                  ? "text-emerald-400 font-bold"
                  : "text-amber-400 font-bold"
              }
            >
              {engineStatus?.running ? "RUNNING" : "STOPPED"}
            </span>
          </div>
          <div className="h-3 w-px bg-slate-800" />
          <div className="text-slate-400">
            CGROUPS:{" "}
            <span
              className={
                engineStatus?.cgroup_available
                  ? "text-emerald-400"
                  : "text-slate-500"
              }
              title={engineStatus?.cgroup_reason || "Cgroups detection"}
            >
              {engineStatus?.cgroup_available ? "ACTIVE" : "UNAVAILABLE"}
            </span>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-6 max-w-7xl w-full mx-auto space-y-6">
        {/* OVERVIEW TAB */}
        {tab === "overview" && (
          <div className="space-y-6">
            {/* Quick Metrics Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">
                  System CPU
                </div>
                <div className="mt-2 text-3xl font-mono font-bold text-cyan-400">
                  {telemetry ? `${telemetry.cpu_percent.toFixed(1)}%` : "..."}
                </div>
                <div className="mt-1 text-xs text-slate-500 font-mono">
                  {telemetry?.cpu_count ?? "?"} cores detected
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">
                  System Memory
                </div>
                <div className="mt-2 text-3xl font-mono font-bold text-indigo-400">
                  {telemetry
                    ? `${telemetry.memory_percent.toFixed(1)}%`
                    : "..."}
                </div>
                <div className="mt-1 text-xs text-slate-500 font-mono">
                  Resident utilization
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">
                  Active Contracts
                </div>
                <div className="mt-2 text-3xl font-mono font-bold text-emerald-400">
                  {engineStatus?.active_contracts ?? 0}
                </div>
                <div className="mt-1 text-xs text-slate-500 font-mono">
                  {engineStatus?.contract_count ?? 0} total loaded
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">
                  Contract Errors
                </div>
                <div className="mt-2 text-3xl font-mono font-bold text-rose-400">
                  {engineStatus?.error_contracts ?? 0}
                </div>
                <div className="mt-1 text-xs text-slate-500 font-mono">
                  Latched error states
                </div>
              </div>
            </div>

            {/* Platform & Capabilities Detail */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
                Operating System Integration & Privilege Guard
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
                <div>
                  <span className="text-slate-500">Platform: </span>
                  <span className="text-slate-200">
                    {engineStatus?.platform ?? "unknown"}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Enforcement: </span>
                  <span
                    className={
                      engineStatus?.enforcement_supported
                        ? "text-emerald-400"
                        : "text-amber-400"
                    }
                  >
                    {engineStatus?.enforcement_supported
                      ? "SUPPORTED"
                      : "PREVIEW ONLY"}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Effective UID: </span>
                  <span className="text-slate-200">
                    {engineStatus?.euid ?? "N/A"}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Privileged: </span>
                  <span className="text-slate-200">
                    {engineStatus?.privileged_hint ? "YES" : "NO"}
                  </span>
                </div>
              </div>
              <div className="text-xs font-mono bg-slate-950 p-3 rounded border border-slate-800 text-slate-400">
                <span className="text-slate-500">Cgroup v2: </span>
                {engineStatus?.cgroup_reason || "None"}
              </div>
            </div>

            {/* Recent Streamed Events */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
                  Recent Policy Decisions
                </h2>
                <button
                  onClick={() => setTab("events")}
                  className="text-xs text-cyan-400 hover:underline font-mono"
                >
                  View all events →
                </button>
              </div>
              <div className="divide-y divide-slate-800 text-xs font-mono">
                {lastMessage?.recent_events &&
                lastMessage.recent_events.length > 0 ? (
                  lastMessage.recent_events.map((ev) => (
                    <div
                      key={ev.seq}
                      className="py-2.5 flex items-start space-x-3"
                    >
                      <span className="text-slate-500">#{ev.seq}</span>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                          ev.severity === "error"
                            ? "bg-rose-950 text-rose-300 border border-rose-800"
                            : "bg-cyan-950 text-cyan-300 border border-cyan-800"
                        }`}
                      >
                        {ev.type}
                      </span>
                      <span className="text-slate-300 flex-1">
                        {ev.message}
                      </span>
                      {ev.contract_id && (
                        <span className="text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded">
                          {ev.contract_id}
                        </span>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="py-4 text-slate-500 text-center">
                    Awaiting live engine events...
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* CONTRACTS TAB */}
        {tab === "contracts" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-lg font-bold text-slate-100">
                  Declarative Contracts
                </h1>
                <p className="text-xs text-slate-400">
                  Adaptive policies evaluated each engine cycle. Active
                  contracts cannot be deleted or mutated.
                </p>
              </div>
              <div className="flex items-center space-x-3">
                <button
                  onClick={reloadFromDisk}
                  disabled={contractsLoading}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs font-mono text-slate-300 transition"
                >
                  {contractsLoading ? "Reloading..." : "Reload from Disk"}
                </button>
                <button
                  onClick={openCreateModal}
                  className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 rounded text-xs font-mono font-bold text-white transition"
                >
                  + New Contract
                </button>
              </div>
            </div>

            {/* Load Errors Banner */}
            {loadIssues.length > 0 && (
              <div className="bg-rose-950/50 border border-rose-800 rounded p-4 text-xs font-mono space-y-2">
                <div className="font-bold text-rose-300 uppercase">
                  Contract Load Warnings ({loadIssues.length})
                </div>
                {loadIssues.map((issue, idx) => (
                  <div key={idx} className="text-rose-200">
                    <span className="font-bold">{issue.file}:</span>{" "}
                    {issue.error}
                  </div>
                ))}
              </div>
            )}

            {/* Contracts Table */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950 text-slate-400 font-mono uppercase text-[11px] border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-3">Contract / State</th>
                    <th className="px-4 py-3">Target Match</th>
                    <th className="px-4 py-3">WHEN (Trigger)</th>
                    <th className="px-4 py-3">DO (Action)</th>
                    <th className="px-4 py-3">UNTIL (Restore)</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 font-mono">
                  {contracts.map((cs) => {
                    const c = cs.contract;
                    const isActive =
                      cs.lifecycle === "active" ||
                      cs.lifecycle === "activating";
                    const isError = cs.lifecycle === "error";

                    return (
                      <tr
                        key={c.id}
                        className="hover:bg-slate-800/40 transition"
                      >
                        {/* Contract ID and State */}
                        <td className="px-4 py-3.5 space-y-1">
                          <div className="flex items-center space-x-2">
                            <span className="font-bold text-slate-200 text-sm">
                              {c.name}
                            </span>
                            <span
                              className={`px-1.5 py-0.2 rounded text-[10px] font-bold uppercase ${
                                cs.lifecycle === "active"
                                  ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                                  : cs.lifecycle === "error"
                                    ? "bg-rose-950 text-rose-300 border border-rose-800"
                                    : "bg-slate-800 text-slate-400 border border-slate-700"
                              }`}
                            >
                              {cs.lifecycle}
                            </span>
                          </div>
                          <div className="text-slate-500 text-[11px]">
                            {c.id}
                          </div>
                          {cs.last_error && (
                            <div
                              className="text-rose-400 text-[11px] max-w-xs truncate"
                              title={cs.last_error}
                            >
                              Err: {cs.last_error}
                            </div>
                          )}
                        </td>

                        {/* Target Match */}
                        <td className="px-4 py-3.5 space-y-1">
                          {c.target.match.executable && (
                            <div>
                              <span className="text-slate-500">exe: </span>
                              <span className="text-slate-300 font-bold">
                                {c.target.match.executable}
                              </span>
                            </div>
                          )}
                          {c.target.match.command_contains && (
                            <div>
                              <span className="text-slate-500">cmd: </span>
                              <span className="text-slate-400">
                                {c.target.match.command_contains}
                              </span>
                            </div>
                          )}
                          <div className="text-slate-500 text-[10px]">
                            {cs.matched_pids.length > 0 ? (
                              <span className="text-cyan-400">
                                PIDs: {cs.matched_pids.join(", ")}
                              </span>
                            ) : (
                              "No live matches"
                            )}
                          </div>
                        </td>

                        {/* WHEN */}
                        <td className="px-4 py-3.5 space-y-0.5">
                          <div className="text-slate-300">
                            {c.trigger.metric} {c.trigger.operator}{" "}
                            {String(c.trigger.value)}
                          </div>
                          <div className="text-slate-500 text-[10px]">
                            for {c.trigger.for_seconds}s
                          </div>
                          {cs.trigger_satisfied !== undefined && (
                            <div
                              className={`text-[10px] ${
                                cs.trigger_satisfied
                                  ? "text-emerald-400"
                                  : "text-slate-500"
                              }`}
                            >
                              satisfied: {String(cs.trigger_satisfied)}
                            </div>
                          )}
                        </td>

                        {/* DO */}
                        <td className="px-4 py-3.5 space-y-1">
                          {c.actions.map((act, i) => (
                            <span
                              key={i}
                              className="inline-block bg-slate-950 border border-slate-700 px-2 py-0.5 rounded text-[11px] text-cyan-300 mr-1"
                            >
                              {act.type === "nice" && `nice: ${act.value}`}
                              {act.type === "cpu_affinity" &&
                                `affinity: [${act.cpus.join(",")}]`}
                              {act.type === "suspend" && "SIGSTOP suspend"}
                              {act.type === "resume" && "SIGCONT resume"}
                              {act.type === "cpu_quota" &&
                                `quota: ${act.quota_percent}%`}
                            </span>
                          ))}
                        </td>

                        {/* UNTIL */}
                        <td className="px-4 py-3.5 space-y-0.5">
                          <div className="text-slate-300">
                            {c.restore.metric} {c.restore.operator}{" "}
                            {String(c.restore.value)}
                          </div>
                          <div className="text-slate-500 text-[10px]">
                            for {c.restore.for_seconds}s
                          </div>
                          {cs.restore_satisfied !== undefined && (
                            <div
                              className={`text-[10px] ${
                                cs.restore_satisfied
                                  ? "text-emerald-400"
                                  : "text-slate-500"
                              }`}
                            >
                              satisfied: {String(cs.restore_satisfied)}
                            </div>
                          )}
                        </td>

                        {/* Actions */}
                        <td className="px-4 py-3.5 text-right space-x-2">
                          {isError && (
                            <button
                              onClick={() => resetContract(c.id)}
                              className="px-2 py-1 bg-amber-900/60 hover:bg-amber-800 border border-amber-700 text-amber-200 rounded text-[11px]"
                            >
                              Reset
                            </button>
                          )}

                          <button
                            onClick={() => toggleEnabled(c.id, c.enabled)}
                            className={`px-2 py-1 border rounded text-[11px] ${
                              c.enabled
                                ? "bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700"
                                : "bg-slate-950 border-slate-800 text-slate-600 hover:text-slate-400"
                            }`}
                          >
                            {c.enabled ? "Disable" : "Enable"}
                          </button>

                          <button
                            onClick={() => openYamlModal(c)}
                            className="px-2 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 rounded text-[11px]"
                          >
                            YAML
                          </button>

                          <button
                            onClick={() => openEditModal(cs)}
                            disabled={isActive}
                            className={`px-2 py-1 border rounded text-[11px] ${
                              isActive
                                ? "bg-slate-950 border-slate-900 text-slate-700 cursor-not-allowed"
                                : "bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700"
                            }`}
                          >
                            Edit
                          </button>

                          <button
                            onClick={() => deleteContract(c.id)}
                            disabled={isActive}
                            className={`px-2 py-1 border rounded text-[11px] ${
                              isActive
                                ? "bg-slate-950 border-slate-900 text-slate-700 cursor-not-allowed"
                                : "bg-rose-950/60 hover:bg-rose-900 border-rose-800 text-rose-300"
                            }`}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {contracts.length === 0 && (
                    <tr>
                      <td
                        colSpan={6}
                        className="px-4 py-8 text-center text-slate-500 font-sans"
                      >
                        No contracts loaded in engine. Create one or load
                        example contracts.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* PROCESSES TAB */}
        {tab === "processes" && (
          <div className="space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div>
                <h1 className="text-lg font-bold text-slate-100">
                  Linux Process Observation
                </h1>
                <p className="text-xs text-slate-400 font-mono">
                  Read-only snapshot of visible processes with nice, affinity,
                  and ARC enforcement badges.
                </p>
              </div>
              <div className="flex items-center space-x-3">
                {procLoading && (
                  <span className="text-xs text-slate-400 font-mono">
                    Loading...
                  </span>
                )}
                <label className="flex items-center space-x-2 text-xs font-mono text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={onlyArcManaged}
                    onChange={(e) => setOnlyArcManaged(e.target.checked)}
                    className="rounded bg-slate-900 border-slate-700 text-cyan-600 focus:ring-0"
                  />
                  <span>ARC-Managed Only</span>
                </label>
                <input
                  type="text"
                  placeholder="Filter by PID, name, cmd..."
                  value={procFilter}
                  onChange={(e) => setProcFilter(e.target.value)}
                  className="px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 w-64"
                />
                <button
                  onClick={fetchProcesses}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs font-mono text-slate-300"
                >
                  Refresh
                </button>
              </div>
            </div>

            {/* Process List Table */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950 text-slate-400 font-mono uppercase text-[11px] border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-3">PID</th>
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">Command Line</th>
                    <th className="px-4 py-3">CPU%</th>
                    <th className="px-4 py-3">MEM%</th>
                    <th className="px-4 py-3">Nice</th>
                    <th className="px-4 py-3">Affinity</th>
                    <th className="px-4 py-3 text-right">ARC Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 font-mono">
                  {filteredProcesses.map((p) => (
                    <tr
                      key={p.pid}
                      className={`hover:bg-slate-800/40 transition ${
                        p.arc_managed ? "bg-cyan-950/20" : ""
                      }`}
                    >
                      <td className="px-4 py-2.5 font-bold text-slate-300">
                        {p.pid}
                      </td>
                      <td className="px-4 py-2.5 text-cyan-400 font-bold">
                        {p.name || "-"}
                      </td>
                      <td
                        className="px-4 py-2.5 text-slate-400 max-w-md truncate"
                        title={p.cmdline || ""}
                      >
                        {p.cmdline || "-"}
                      </td>
                      <td className="px-4 py-2.5 text-slate-300">
                        {p.cpu_percent !== null && p.cpu_percent !== undefined
                          ? `${p.cpu_percent.toFixed(1)}%`
                          : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-slate-300">
                        {p.memory_percent !== null &&
                        p.memory_percent !== undefined
                          ? `${p.memory_percent.toFixed(1)}%`
                          : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-slate-300">
                        {p.nice !== null && p.nice !== undefined ? p.nice : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-slate-400 text-[10px]">
                        {p.cpu_affinity && p.cpu_affinity.length > 0
                          ? `[${p.cpu_affinity.join(",")}]`
                          : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {p.arc_managed ? (
                          <span
                            className="bg-cyan-950 border border-cyan-800 text-cyan-300 text-[10px] px-2 py-0.5 rounded font-bold uppercase"
                            title={`Active contracts: ${p.active_contract_ids.join(", ")}`}
                          >
                            Managed
                          </span>
                        ) : (
                          <span className="text-slate-600 text-[10px]">
                            Normal
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {filteredProcesses.length === 0 && (
                    <tr>
                      <td
                        colSpan={8}
                        className="px-4 py-8 text-center text-slate-500 font-sans"
                      >
                        No matching processes found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* EVENTS TAB */}
        {tab === "events" && (
          <div className="space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div>
                <h1 className="text-lg font-bold text-slate-100">
                  Engine Audit Log
                </h1>
                <p className="text-xs text-slate-400 font-mono">
                  Immutable sequence of contract evaluations, snapshots,
                  mutations, and rollbacks.
                </p>
              </div>
              <div className="flex items-center space-x-3">
                <select
                  value={eventSeverity}
                  onChange={(e) => setEventSeverity(e.target.value)}
                  className="px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs font-mono text-slate-200 focus:outline-none"
                >
                  <option value="all">All Severities</option>
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="error">Error</option>
                </select>
                <input
                  type="text"
                  placeholder="Filter events..."
                  value={eventFilter}
                  onChange={(e) => setEventFilter(e.target.value)}
                  className="px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 w-64"
                />
                <button
                  onClick={fetchEvents}
                  disabled={eventsLoading}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs font-mono text-slate-300"
                >
                  {eventsLoading ? "Refreshing..." : "Refresh"}
                </button>
              </div>
            </div>

            {/* Events List */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden divide-y divide-slate-800 font-mono text-xs">
              {filteredEvents.map((ev) => (
                <div
                  key={ev.seq}
                  className="p-3.5 hover:bg-slate-800/40 transition flex items-start space-x-4"
                >
                  <span className="text-slate-500 text-[11px] w-12 text-right">
                    #{ev.seq}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase shrink-0 ${
                      ev.severity === "error"
                        ? "bg-rose-950 text-rose-300 border border-rose-800"
                        : ev.severity === "warning"
                          ? "bg-amber-950 text-amber-300 border border-amber-800"
                          : "bg-cyan-950 text-cyan-300 border border-cyan-800"
                    }`}
                  >
                    {ev.type}
                  </span>
                  <div className="flex-1 space-y-1">
                    <div className="text-slate-200">{ev.message}</div>
                    <div className="flex items-center space-x-4 text-slate-500 text-[11px]">
                      {ev.contract_id && (
                        <span>Contract: {ev.contract_id}</span>
                      )}
                      {ev.pid && <span>PID: {ev.pid}</span>}
                      <span>Epoch: {ev.timestamp.toFixed(2)}s</span>
                    </div>
                  </div>
                </div>
              ))}
              {filteredEvents.length === 0 && (
                <div className="p-8 text-center text-slate-500 font-sans">
                  No events match the selected criteria.
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* CREATE / EDIT / YAML MODAL */}
      {showModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-lg max-w-2xl w-full p-6 space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-200">
                {modalMode === "create" && "Create New Policy Contract"}
                {modalMode === "edit" &&
                  `Edit Contract: ${selectedContract?.id}`}
                {modalMode === "yaml" &&
                  `Contract Definition YAML: ${selectedContract?.id}`}
              </h3>
              <button
                onClick={() => setShowModal(false)}
                className="text-slate-400 hover:text-slate-200 text-lg leading-none"
              >
                ✕
              </button>
            </div>

            {formError && (
              <div className="bg-rose-950/50 border border-rose-800 rounded p-3 text-xs font-mono text-rose-300">
                {formError}
              </div>
            )}

            {modalMode === "yaml" ? (
              <div className="space-y-4">
                <pre className="bg-slate-950 p-4 rounded border border-slate-800 text-xs font-mono text-cyan-300 overflow-x-auto">
                  {rawYaml}
                </pre>
                <div className="text-right">
                  <button
                    onClick={() => setShowModal(false)}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-xs font-mono text-slate-200 rounded"
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : (
              <form
                onSubmit={handleFormSubmit}
                className="space-y-4 text-xs font-mono"
              >
                {/* ID & Name */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 mb-1">
                      ID (hyphen-case)
                    </label>
                    <input
                      type="text"
                      required
                      disabled={modalMode === "edit"}
                      value={formId}
                      onChange={(e) => setFormId(e.target.value)}
                      placeholder="e.g. compile-worker-relief"
                      className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200 focus:border-cyan-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 mb-1">
                      Human Name
                    </label>
                    <input
                      type="text"
                      required
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      placeholder="e.g. Background Worker Throttle"
                      className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200 focus:border-cyan-500 focus:outline-none"
                    />
                  </div>
                </div>

                {/* Target Match */}
                <div className="border border-slate-800 p-3 rounded space-y-2 bg-slate-950/40">
                  <div className="font-bold text-slate-300 uppercase text-[11px]">
                    Process Target Match
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-slate-400 mb-1">
                        Executable Name
                      </label>
                      <input
                        type="text"
                        value={formExecutable}
                        onChange={(e) => setFormExecutable(e.target.value)}
                        placeholder="e.g. python"
                        className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200 focus:border-cyan-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-400 mb-1">
                        Command Line Contains
                      </label>
                      <input
                        type="text"
                        value={formCommand}
                        onChange={(e) => setFormCommand(e.target.value)}
                        placeholder="e.g. worker_task"
                        className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200 focus:border-cyan-500 focus:outline-none"
                      />
                    </div>
                  </div>
                </div>

                {/* WHEN Trigger */}
                <div className="border border-slate-800 p-3 rounded space-y-2 bg-slate-950/40">
                  <div className="font-bold text-slate-300 uppercase text-[11px]">
                    Trigger Condition (WHEN)
                  </div>
                  <div className="grid grid-cols-4 gap-2">
                    <div>
                      <label className="block text-slate-400 mb-1">
                        Metric
                      </label>
                      <select
                        value={formTriggerMetric}
                        onChange={(e) => setFormTriggerMetric(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                      >
                        <option value="system.cpu.percent">
                          system.cpu.percent
                        </option>
                        <option value="system.memory.percent">
                          system.memory.percent
                        </option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-slate-400 mb-1">
                        Operator
                      </label>
                      <select
                        value={formTriggerOp}
                        onChange={(e) => setFormTriggerOp(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                      >
                        <option value="gt">&gt;</option>
                        <option value="gte">&gt;=</option>
                        <option value="lt">&lt;</option>
                        <option value="lte">&lt;=</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-slate-400 mb-1">
                        Value (%)
                      </label>
                      <input
                        type="number"
                        required
                        value={formTriggerVal}
                        onChange={(e) => setFormTriggerVal(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-400 mb-1">
                        For (Seconds)
                      </label>
                      <input
                        type="number"
                        required
                        value={formTriggerSec}
                        onChange={(e) => setFormTriggerSec(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                      />
                    </div>
                  </div>
                </div>

                {/* DO Action */}
                <div className="border border-slate-800 p-3 rounded space-y-2 bg-slate-950/40">
                  <div className="font-bold text-slate-300 uppercase text-[11px]">
                    Action (DO)
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-slate-400 mb-1">
                        Action Type
                      </label>
                      <select
                        value={formActionType}
                        onChange={(e) =>
                          setFormActionType(
                            e.target.value as typeof formActionType,
                          )
                        }
                        className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                      >
                        <option value="nice">nice (Priority adjustment)</option>
                        <option value="cpu_affinity">
                          cpu_affinity (Core pinning)
                        </option>
                        <option value="suspend">suspend (SIGSTOP)</option>
                        <option value="resume">resume (SIGCONT)</option>
                        <option value="cpu_quota">
                          cpu_quota (Cgroups v2 cpu.max)
                        </option>
                      </select>
                    </div>
                    <div>
                      {formActionType === "nice" && (
                        <>
                          <label className="block text-slate-400 mb-1">
                            Nice Value (-20 to 19)
                          </label>
                          <input
                            type="number"
                            value={formNiceVal}
                            onChange={(e) => setFormNiceVal(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                          />
                        </>
                      )}
                      {formActionType === "cpu_affinity" && (
                        <>
                          <label className="block text-slate-400 mb-1">
                            CPUs (comma separated)
                          </label>
                          <input
                            type="text"
                            value={formAffinityCpus}
                            onChange={(e) =>
                              setFormAffinityCpus(e.target.value)
                            }
                            placeholder="0, 1"
                            className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                          />
                        </>
                      )}
                      {formActionType === "cpu_quota" && (
                        <>
                          <label className="block text-slate-400 mb-1">
                            Quota Percent (1-100)
                          </label>
                          <input
                            type="number"
                            value={formQuotaVal}
                            onChange={(e) => setFormQuotaVal(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                          />
                        </>
                      )}
                      {(formActionType === "suspend" ||
                        formActionType === "resume") && (
                        <div className="text-slate-500 pt-6">
                          No additional parameters required
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* UNTIL Restore */}
                <div className="border border-slate-800 p-3 rounded space-y-2 bg-slate-950/40">
                  <div className="font-bold text-slate-300 uppercase text-[11px]">
                    Restoration Condition (UNTIL)
                  </div>
                  <div className="grid grid-cols-4 gap-2">
                    <div>
                      <label className="block text-slate-400 mb-1">
                        Metric
                      </label>
                      <select
                        value={formRestoreMetric}
                        onChange={(e) => setFormRestoreMetric(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                      >
                        <option value="system.cpu.percent">
                          system.cpu.percent
                        </option>
                        <option value="system.memory.percent">
                          system.memory.percent
                        </option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-slate-400 mb-1">
                        Operator
                      </label>
                      <select
                        value={formRestoreOp}
                        onChange={(e) => setFormRestoreOp(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                      >
                        <option value="lt">&lt;</option>
                        <option value="lte">&lt;=</option>
                        <option value="gt">&gt;</option>
                        <option value="gte">&gt;=</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-slate-400 mb-1">
                        Value (%)
                      </label>
                      <input
                        type="number"
                        required
                        value={formRestoreVal}
                        onChange={(e) => setFormRestoreVal(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                      />
                    </div>
                    <div>
                      <label className="block text-slate-400 mb-1">
                        For (Seconds)
                      </label>
                      <input
                        type="number"
                        required
                        value={formRestoreSec}
                        onChange={(e) => setFormRestoreSec(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-end space-x-3 pt-3">
                  <button
                    type="button"
                    onClick={() => setShowModal(false)}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded font-bold"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded font-bold"
                  >
                    {modalMode === "create" ? "Create Policy" : "Save Changes"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
