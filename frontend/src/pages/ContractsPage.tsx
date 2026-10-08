import { useState } from "react";
import {
  Eye,
  FileCode2,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { ContractStatus } from "../types";
import { api } from "../lib/api";
import { describeAction, isProtectedLifecycle, opSymbol } from "../lib/utils";
import { LifecycleBadge } from "../components/Badge";
import { ContractEditor } from "../components/ContractEditor";

interface Props {
  contracts: ContractStatus[];
  loadIssues: Array<{ file: string; error: string }>;
  loading: boolean;
  onRefresh: () => void;
}
type Mode = "create" | "edit" | "view";

export function ContractsPage({
  contracts,
  loadIssues,
  loading,
  onRefresh,
}: Props) {
  const [mode, setMode] = useState<Mode>("create");
  const [selected, setSelected] = useState<ContractStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const show = (next: Mode, item: ContractStatus | null = null) => {
    setMode(next);
    setSelected(item);
    setOpen(true);
  };
  const run = async (key: string, task: () => Promise<unknown>) => {
    setPending(key);
    setError(null);
    try {
      await task();
      await onRefresh();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Contract operation failed",
      );
    } finally {
      setPending(null);
    }
  };
  const remove = (item: ContractStatus) => {
    if (window.confirm(`Delete ${item.contract.id} from disk?`))
      void run(`delete-${item.contract.id}`, () =>
        api.deleteContract(item.contract.id),
      );
  };
  return (
    <main className="page">
      <header className="page-header">
        <div>
          <div className="page-kicker">Policy workspace</div>
          <h1 className="page-title">Resource contracts</h1>
          <p className="page-description">
            Declarative Linux policies connect a measured condition to process
            resource controls and exact restoration.
          </p>
        </div>
        <div className="page-actions">
          <button
            className="button"
            onClick={() => void run("reload", () => api.reloadContracts())}
            disabled={pending !== null}
          >
            <RefreshCw size={13} />
            {pending === "reload" ? "Reloading" : "Reload from disk"}
          </button>
          <button className="button primary" onClick={() => show("create")}>
            <Plus size={14} />
            Create contract
          </button>
        </div>
      </header>
      {error && (
        <div className="notice error" style={{ marginBottom: 10 }}>
          {error}
        </div>
      )}
      {loadIssues.map((issue) => (
        <div className="notice" style={{ marginBottom: 8 }} key={issue.file}>
          <strong>{issue.file}</strong>: {issue.error}
        </div>
      ))}
      {contracts.length ? (
        <div className="stack">
          {contracts.map((item) => {
            const contract = item.contract;
            const busy = isProtectedLifecycle(item.lifecycle);
            return (
              <article className="panel" key={contract.id}>
                <div className="panel-body">
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 14,
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          flexWrap: "wrap",
                        }}
                      >
                        <h2
                          style={{ margin: 0, fontSize: 14, fontWeight: 650 }}
                        >
                          {contract.name}
                        </h2>
                        <LifecycleBadge lifecycle={item.lifecycle} />
                        {!contract.enabled && (
                          <span className="badge">Disabled</span>
                        )}
                      </div>
                      <div
                        className="panel-subtle mono"
                        style={{ marginTop: 4 }}
                      >
                        {contract.id}
                      </div>
                      {contract.description && (
                        <p
                          className="page-description"
                          style={{ marginTop: 8 }}
                        >
                          {contract.description}
                        </p>
                      )}
                    </div>
                    <div className="page-actions">
                      <button
                        className="button icon-button"
                        onClick={() => show("view", item)}
                        aria-label={`Inspect ${contract.name}`}
                      >
                        <Eye size={13} />
                      </button>
                      <button
                        className="button icon-button"
                        onClick={() => show("edit", item)}
                        disabled={busy}
                        aria-label={`Edit ${contract.name}`}
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        className="button"
                        onClick={() =>
                          void run(`toggle-${contract.id}`, () =>
                            api.toggleEnabled(contract.id, !contract.enabled),
                          )
                        }
                        disabled={busy || pending !== null}
                      >
                        {contract.enabled ? "Disable" : "Enable"}
                      </button>
                      {item.lifecycle === "error" && (
                        <button
                          className="button"
                          onClick={() =>
                            void run(`reset-${contract.id}`, () =>
                              api.resetContract(contract.id),
                            )
                          }
                        >
                          <RotateCcw size={13} />
                          Reset
                        </button>
                      )}
                      <button
                        className="button icon-button danger"
                        onClick={() => remove(item)}
                        disabled={busy || pending !== null}
                        aria-label={`Delete ${contract.name}`}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))",
                      gap: 8,
                      marginTop: 16,
                    }}
                  >
                    <PolicyCell
                      label="When"
                      value={`${contract.trigger.metric} ${opSymbol(contract.trigger.operator)} ${String(contract.trigger.value)}`}
                      note={`for ${contract.trigger.for_seconds}s`}
                    />
                    <PolicyCell
                      label="Target"
                      value={
                        contract.target.match.executable || "Command match"
                      }
                      note={
                        contract.target.match.command_contains ||
                        "Executable match"
                      }
                    />
                    <PolicyCell
                      label="Actions"
                      value={contract.actions
                        .map((action) => describeAction(action))
                        .join(" · ")}
                      note={`${contract.actions.length} verified operation${contract.actions.length === 1 ? "" : "s"}`}
                    />
                    <PolicyCell
                      label="Restore"
                      value={`${contract.restore.metric} ${opSymbol(contract.restore.operator)} ${String(contract.restore.value)}`}
                      note={`for ${contract.restore.for_seconds}s, then restore exact prior state`}
                    />
                  </div>
                  {(item.matched_pids.length > 0 || item.last_error) && (
                    <div
                      className={item.last_error ? "notice error" : "notice"}
                      style={{ marginTop: 12 }}
                    >
                      {item.last_error ||
                        `Matched PIDs: ${item.matched_pids.join(", ")}`}
                    </div>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <section className="panel">
          <div className="empty">
            <div>
              <div className="empty-icon">
                <FileCode2 size={18} />
              </div>
              <strong>
                {loading
                  ? "Loading contracts"
                  : "Create your first resource contract"}
              </strong>
              <p>
                A contract states when a condition must hold, which processes it
                targets, what Linux resource controls ARC applies, and when
                exact prior state is restored.
              </p>
              {!loading && (
                <button
                  className="button primary"
                  onClick={() => show("create")}
                >
                  <Plus size={14} />
                  Create contract
                </button>
              )}
            </div>
          </div>
        </section>
      )}
      {open && (
        <ContractEditor
          mode={mode}
          contractStatus={selected}
          onClose={() => setOpen(false)}
          onSaved={onRefresh}
        />
      )}
    </main>
  );
}

function PolicyCell({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="core-tile">
      <div className="page-kicker">{label}</div>
      <div className="list-primary mono" title={value}>
        {value}
      </div>
      <div className="list-secondary">{note}</div>
    </div>
  );
}
