import { useState } from "react";
import { ContractStatus } from "../types";
import { LifecycleBadge } from "../components/Badge";
import { opSymbol, describeAction } from "../lib/utils";
import { api } from "../lib/api";
import { ContractEditor } from "../components/ContractEditor";

interface ContractsPageProps {
  contracts: ContractStatus[];
  loadIssues: Array<{ file: string; error: string }>;
  loading: boolean;
  onRefresh: () => void;
}

type ModalMode = "create" | "edit" | "view";

export function ContractsPage({
  contracts,
  loadIssues,
  loading,
  onRefresh,
}: ContractsPageProps) {
  const [modalMode, setModalMode] = useState<ModalMode>("create");
  const [selectedCs, setSelectedCs] = useState<ContractStatus | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState<string | null>(null);

  function openCreate() {
    setModalMode("create");
    setSelectedCs(null);
    setShowModal(true);
  }

  function openEdit(cs: ContractStatus) {
    setModalMode("edit");
    setSelectedCs(cs);
    setShowModal(true);
  }

  function openView(cs: ContractStatus) {
    setModalMode("view");
    setSelectedCs(cs);
    setShowModal(true);
  }

  function closeModal() {
    setShowModal(false);
    setSelectedCs(null);
  }

  async function handleToggleEnabled(cs: ContractStatus) {
    setActionError(null);
    setActionPending(`toggle-${cs.contract.id}`);
    try {
      await api.toggleEnabled(cs.contract.id, !cs.contract.enabled);
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Toggle failed");
    } finally {
      setActionPending(null);
    }
  }

  async function handleReset(cs: ContractStatus) {
    setActionError(null);
    setActionPending(`reset-${cs.contract.id}`);
    try {
      await api.resetContract(cs.contract.id);
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setActionPending(null);
    }
  }

  async function handleDelete(cs: ContractStatus) {
    if (
      !window.confirm(
        `Delete contract "${cs.contract.id}" from disk?\n\nThis cannot be undone.`,
      )
    )
      return;
    setActionError(null);
    setActionPending(`delete-${cs.contract.id}`);
    try {
      await api.deleteContract(cs.contract.id);
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setActionPending(null);
    }
  }

  async function handleReload() {
    setActionError(null);
    setActionPending("reload");
    try {
      await api.reloadContracts();
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Reload failed");
    } finally {
      setActionPending(null);
    }
  }

  const counts = {
    total: contracts.length,
    enabled: contracts.filter((cs) => cs.contract.enabled).length,
    active: contracts.filter(
      (cs) =>
        cs.lifecycle === "active" ||
        cs.lifecycle === "activating" ||
        cs.lifecycle === "restoring",
    ).length,
    error: contracts.filter((cs) => cs.lifecycle === "error").length,
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div>
          <h1 className="text-base font-bold text-slate-100 font-mono">
            Policy Contracts
          </h1>
          <p className="text-xs text-slate-500 mt-0.5 font-mono">
            Declarative policies evaluated each engine cycle. Active contracts
            are protected from mutation.
          </p>
          {/* Summary counts */}
          <div className="flex items-center space-x-4 mt-2 text-xs font-mono">
            <span className="text-slate-600">{counts.total} total</span>
            <span className="text-slate-400">{counts.enabled} enabled</span>
            {counts.active > 0 && (
              <span className="text-emerald-400">
                {counts.active} enforcing
              </span>
            )}
            {counts.error > 0 && (
              <span className="text-rose-400">{counts.error} error</span>
            )}
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={handleReload}
            disabled={actionPending === "reload"}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs font-mono text-slate-300 transition disabled:opacity-50"
          >
            {actionPending === "reload" ? "Reloading..." : "Reload from Disk"}
          </button>
          <button
            onClick={openCreate}
            className="px-3 py-1.5 bg-cyan-700 hover:bg-cyan-600 rounded text-xs font-mono font-bold text-white transition"
          >
            + New Contract
          </button>
        </div>
      </div>

      {/* Action error banner */}
      {actionError && (
        <div className="bg-rose-950/60 border border-rose-800 rounded p-3 text-xs font-mono text-rose-300 flex items-center justify-between">
          <span>{actionError}</span>
          <button
            onClick={() => setActionError(null)}
            className="text-rose-400 hover:text-rose-200 ml-4"
          >
            ✕
          </button>
        </div>
      )}

      {/* Load issues */}
      {loadIssues.length > 0 && (
        <div className="bg-amber-950/40 border border-amber-800 rounded p-4 text-xs font-mono space-y-1">
          <div className="font-bold text-amber-300 uppercase text-[11px] tracking-wide">
            Contract Load Warnings ({loadIssues.length})
          </div>
          {loadIssues.map((issue, idx) => (
            <div key={idx} className="text-amber-200/80">
              <span className="font-bold">{issue.file}:</span> {issue.error}
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {contracts.length === 0 && !loading && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-12 text-center space-y-3">
          <div className="text-slate-500 font-mono text-sm">
            No contracts loaded
          </div>
          <div className="text-slate-600 text-xs font-mono">
            Copy an example from{" "}
            <code className="text-slate-400">contracts/examples/</code> to{" "}
            <code className="text-slate-400">contracts/</code>, or create one
            here.
          </div>
          <button
            onClick={openCreate}
            className="mt-2 px-4 py-2 bg-cyan-700 hover:bg-cyan-600 rounded text-xs font-mono font-bold text-white"
          >
            + New Contract
          </button>
        </div>
      )}

      {/* Contract table */}
      {contracts.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950 text-slate-500 font-mono uppercase text-[10px] border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Contract</th>
                <th className="px-4 py-3">FOR (Target)</th>
                <th className="px-4 py-3">WHEN (Trigger)</th>
                <th className="px-4 py-3">DO (Action)</th>
                <th className="px-4 py-3">UNTIL (Restore)</th>
                <th className="px-4 py-3 text-right">Controls</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {contracts.map((cs) => {
                const c = cs.contract;
                const isBusy =
                  cs.lifecycle === "active" ||
                  cs.lifecycle === "activating" ||
                  cs.lifecycle === "restoring";
                const isError = cs.lifecycle === "error";

                return (
                  <tr
                    key={c.id}
                    className={`hover:bg-slate-800/30 transition font-mono ${
                      isBusy ? "bg-emerald-950/10" : ""
                    } ${isError ? "bg-rose-950/10" : ""}`}
                  >
                    {/* Contract ID + lifecycle */}
                    <td className="px-4 py-3.5 space-y-1.5 max-w-[240px]">
                      <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                        <LifecycleBadge lifecycle={cs.lifecycle} />
                        {!c.enabled && (
                          <span className="text-[10px] text-slate-600 border border-slate-800 px-1.5 py-0.5 rounded uppercase tracking-wide font-mono">
                            disabled
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => openView(cs)}
                        className="font-bold text-slate-200 text-sm hover:text-cyan-300 transition text-left"
                        title="View contract details"
                      >
                        {c.name}
                      </button>
                      <div className="text-slate-600 text-[10px]">{c.id}</div>
                      {c.description && (
                        <div
                          className="text-slate-500 text-[10px] truncate max-w-[200px]"
                          title={c.description}
                        >
                          {c.description}
                        </div>
                      )}
                      {cs.last_error && (
                        <div
                          className="text-rose-400 text-[10px] max-w-xs truncate"
                          title={cs.last_error}
                        >
                          error: {cs.last_error}
                        </div>
                      )}
                    </td>

                    {/* Target */}
                    <td className="px-4 py-3.5 space-y-1">
                      {c.target.match.executable && (
                        <div>
                          <span className="text-slate-600">exe: </span>
                          <span className="text-cyan-400 font-bold">
                            {c.target.match.executable}
                          </span>
                        </div>
                      )}
                      {c.target.match.command_contains && (
                        <div>
                          <span className="text-slate-600">cmd: </span>
                          <span className="text-slate-400">
                            {c.target.match.command_contains}
                          </span>
                        </div>
                      )}
                      {cs.matched_pids.length > 0 ? (
                        <div className="text-[10px] text-cyan-400">
                          PIDs: {cs.matched_pids.join(", ")}
                        </div>
                      ) : (
                        <div className="text-slate-700 text-[10px]">
                          no match
                        </div>
                      )}
                    </td>

                    {/* WHEN */}
                    <td className="px-4 py-3.5 space-y-0.5">
                      <div className="text-slate-300">{c.trigger.metric}</div>
                      <div className="text-cyan-300">
                        {opSymbol(c.trigger.operator)} {String(c.trigger.value)}
                      </div>
                      <div className="text-slate-600 text-[10px]">
                        for {c.trigger.for_seconds}s
                      </div>
                      {/* Trigger progress */}
                      {cs.trigger_raw !== null &&
                        cs.trigger_raw !== undefined &&
                        cs.lifecycle !== "active" && (
                          <div
                            className={`text-[10px] ${
                              cs.trigger_raw
                                ? "text-amber-400"
                                : "text-slate-600"
                            }`}
                          >
                            {cs.trigger_raw
                              ? "condition met"
                              : "condition clear"}
                            {cs.trigger_elapsed_seconds !== null &&
                              cs.trigger_elapsed_seconds !== undefined &&
                              cs.trigger_elapsed_seconds > 0 && (
                                <span className="ml-1 text-amber-300">
                                  {cs.trigger_elapsed_seconds.toFixed(1)}s /
                                  {c.trigger.for_seconds}s
                                </span>
                              )}
                          </div>
                        )}
                    </td>

                    {/* DO */}
                    <td className="px-4 py-3.5">
                      <div className="flex flex-col gap-1">
                        {c.actions.map((act, i) => (
                          <span
                            key={i}
                            className="inline-block bg-slate-950 border border-slate-700 px-2 py-0.5 rounded text-[11px] text-cyan-300"
                          >
                            {describeAction(
                              act as Parameters<typeof describeAction>[0],
                            )}
                          </span>
                        ))}
                      </div>
                    </td>

                    {/* UNTIL */}
                    <td className="px-4 py-3.5 space-y-0.5">
                      <div className="text-slate-300">{c.restore.metric}</div>
                      <div className="text-cyan-300">
                        {opSymbol(c.restore.operator)} {String(c.restore.value)}
                      </div>
                      <div className="text-slate-600 text-[10px]">
                        for {c.restore.for_seconds}s
                      </div>
                      {/* Restore progress */}
                      {cs.lifecycle === "active" &&
                        cs.restore_raw !== null &&
                        cs.restore_raw !== undefined && (
                          <div
                            className={`text-[10px] ${
                              cs.restore_raw
                                ? "text-emerald-400"
                                : "text-slate-600"
                            }`}
                          >
                            {cs.restore_raw
                              ? "condition met"
                              : "condition clear"}
                            {cs.restore_elapsed_seconds !== null &&
                              cs.restore_elapsed_seconds !== undefined &&
                              cs.restore_elapsed_seconds > 0 && (
                                <span className="ml-1 text-emerald-300">
                                  {cs.restore_elapsed_seconds.toFixed(1)}s /
                                  {c.restore.for_seconds}s
                                </span>
                              )}
                          </div>
                        )}
                    </td>

                    {/* Controls */}
                    <td className="px-4 py-3.5 text-right">
                      <div className="flex items-center justify-end flex-wrap gap-1">
                        {isError && (
                          <button
                            onClick={() => handleReset(cs)}
                            disabled={actionPending !== null}
                            title="Reset ERROR state back to inactive"
                            className="px-2 py-1 bg-amber-950/60 hover:bg-amber-900 border border-amber-700 text-amber-200 rounded text-[11px] font-mono disabled:opacity-50"
                          >
                            Reset
                          </button>
                        )}

                        <button
                          onClick={() => handleToggleEnabled(cs)}
                          disabled={actionPending !== null}
                          title={
                            c.enabled
                              ? "Disable this contract"
                              : "Enable this contract"
                          }
                          className={`px-2 py-1 border rounded text-[11px] font-mono disabled:opacity-50 ${
                            c.enabled
                              ? "bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700"
                              : "bg-slate-950 border-slate-800 text-slate-500 hover:text-slate-300"
                          }`}
                        >
                          {c.enabled ? "Disable" : "Enable"}
                        </button>

                        <button
                          onClick={() => openView(cs)}
                          title="View contract definition"
                          className="px-2 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 rounded text-[11px] font-mono"
                        >
                          View
                        </button>

                        <button
                          onClick={() => openEdit(cs)}
                          disabled={isBusy}
                          title={
                            isBusy
                              ? `Cannot edit while ${cs.lifecycle}`
                              : "Edit contract"
                          }
                          className={`px-2 py-1 border rounded text-[11px] font-mono ${
                            isBusy
                              ? "bg-slate-950 border-slate-900 text-slate-700 cursor-not-allowed"
                              : "bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700"
                          }`}
                        >
                          Edit
                        </button>

                        <button
                          onClick={() => handleDelete(cs)}
                          disabled={isBusy || actionPending !== null}
                          title={
                            isBusy
                              ? `Cannot delete while ${cs.lifecycle}`
                              : "Delete contract from disk"
                          }
                          className={`px-2 py-1 border rounded text-[11px] font-mono ${
                            isBusy
                              ? "bg-slate-950 border-slate-900 text-slate-700 cursor-not-allowed"
                              : "bg-rose-950/50 hover:bg-rose-900 border-rose-900 text-rose-400 disabled:opacity-50"
                          }`}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {showModal && (
        <ContractEditor
          mode={modalMode}
          contractStatus={selectedCs}
          onClose={closeModal}
          onSaved={onRefresh}
        />
      )}
    </div>
  );
}
