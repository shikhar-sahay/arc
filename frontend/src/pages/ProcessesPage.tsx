import { useMemo, useState } from "react";
import { ChevronDown, Cpu, RefreshCw, Search, X } from "lucide-react";
import { ProcessItem } from "../types";

type SortKey = "pid" | "cpu" | "memory" | "nice" | "name";
interface Props {
  processes: ProcessItem[];
  totalObserved: number;
  loading: boolean;
  onRefresh: () => void;
}

export function ProcessesPage({
  processes,
  totalObserved,
  loading,
  onRefresh,
}: Props) {
  const [query, setQuery] = useState("");
  const [managedOnly, setManagedOnly] = useState(false);
  const [sort, setSort] = useState<SortKey>("cpu");
  const [descending, setDescending] = useState(true);
  const [selected, setSelected] = useState<ProcessItem | null>(null);
  const rows = useMemo(
    () =>
      processes
        .filter((process) => {
          const text = query.toLowerCase();
          return (
            (!managedOnly || process.arc_managed) &&
            (!text ||
              String(process.pid).includes(text) ||
              (process.name ?? "").toLowerCase().includes(text) ||
              (process.cmdline ?? "").toLowerCase().includes(text))
          );
        })
        .sort((a, b) => {
          const value = (item: ProcessItem): string | number =>
            sort === "pid"
              ? item.pid
              : sort === "cpu"
                ? (item.cpu_percent ?? -1)
                : sort === "memory"
                  ? (item.memory_percent ?? -1)
                  : sort === "nice"
                    ? (item.nice ?? 0)
                    : (item.name ?? "").toLowerCase();
          return (
            (value(a) < value(b) ? -1 : value(a) > value(b) ? 1 : 0) *
            (descending ? -1 : 1)
          );
        }),
    [processes, query, managedOnly, sort, descending],
  );
  const changeSort = (key: SortKey) => {
    if (sort === key) setDescending(!descending);
    else {
      setSort(key);
      setDescending(key !== "name");
    }
  };

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <div className="page-kicker">Observation</div>
          <h1 className="page-title">Processes</h1>
          <p className="page-description">
            A read-only Linux process snapshot. Resource changes remain
            contract-driven.
          </p>
        </div>
        <div className="page-actions">
          <span className="badge">
            {rows.length} shown · {totalObserved} observed
          </span>
          <button className="button" onClick={onRefresh} disabled={loading}>
            <RefreshCw size={13} />
            {loading ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </header>
      <div className="toolbar">
        <Search size={14} style={{ color: "var(--faint)" }} />
        <input
          className="field"
          style={{ flex: 1, minWidth: 220 }}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search PID, process name, or command"
          aria-label="Search processes"
        />
        <label className="button">
          <input
            type="checkbox"
            checked={managedOnly}
            onChange={(event) => setManagedOnly(event.target.checked)}
          />
          Managed by ARC
        </label>
      </div>
      <div className="split-view">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <Sortable
                  label="PID"
                  value="pid"
                  current={sort}
                  descending={descending}
                  onClick={changeSort}
                />
                <Sortable
                  label="Process"
                  value="name"
                  current={sort}
                  descending={descending}
                  onClick={changeSort}
                />
                <th>Command</th>
                <Sortable
                  label="CPU"
                  value="cpu"
                  current={sort}
                  descending={descending}
                  onClick={changeSort}
                />
                <Sortable
                  label="Memory"
                  value="memory"
                  current={sort}
                  descending={descending}
                  onClick={changeSort}
                />
                <Sortable
                  label="Nice"
                  value="nice"
                  current={sort}
                  descending={descending}
                  onClick={changeSort}
                />
                <th>Affinity</th>
                <th>ARC</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((process) => (
                <tr
                  key={process.pid}
                  className={selected?.pid === process.pid ? "selected" : ""}
                  onClick={() => setSelected(process)}
                  tabIndex={0}
                  onKeyDown={(event) =>
                    event.key === "Enter" && setSelected(process)
                  }
                >
                  <td className="mono">{process.pid}</td>
                  <td>
                    <strong style={{ color: "#e3e4e6", fontWeight: 600 }}>
                      {process.name || "Unknown"}
                    </strong>
                  </td>
                  <td>
                    <div className="truncate" title={process.cmdline ?? ""}>
                      {process.cmdline || "Not available"}
                    </div>
                  </td>
                  <td
                    className="mono"
                    style={{
                      color:
                        (process.cpu_percent ?? 0) > 60
                          ? "var(--amber)"
                          : "inherit",
                    }}
                  >
                    {process.cpu_percent?.toFixed(1) ?? "--"}%
                  </td>
                  <td className="mono">
                    {process.memory_percent?.toFixed(1) ?? "--"}%
                  </td>
                  <td className="mono">{process.nice ?? "--"}</td>
                  <td className="mono">
                    {process.cpu_affinity?.join(", ") ?? "--"}
                  </td>
                  <td>
                    {process.arc_managed ? (
                      <span className="badge green">Managed</span>
                    ) : (
                      <span className="panel-subtle">No</span>
                    )}
                  </td>
                </tr>
              ))}
              {!rows.length && (
                <tr>
                  <td colSpan={8}>
                    <div className="empty">
                      <div>
                        <div className="empty-icon">
                          <Cpu size={18} />
                        </div>
                        <strong>
                          {loading
                            ? "Loading processes"
                            : "No matching processes"}
                        </strong>
                        <p>
                          {query || managedOnly
                            ? "Adjust the current filters."
                            : "No process snapshot is available from the backend."}
                        </p>
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {selected && (
          <aside className="panel inspector" aria-label="Process details">
            <div className="panel-header">
              <div className="panel-title">
                <Cpu size={14} />
                {selected.name || "Process"}
              </div>
              <button
                className="button icon-button"
                onClick={() => setSelected(null)}
                aria-label="Close process details"
              >
                <X size={14} />
              </button>
            </div>
            <div className="panel-body">
              <dl className="inspector-grid">
                <dt>PID</dt>
                <dd className="mono">{selected.pid}</dd>
                <dt>CPU</dt>
                <dd className="mono">
                  {selected.cpu_percent?.toFixed(1) ?? "--"}%
                </dd>
                <dt>Memory</dt>
                <dd className="mono">
                  {selected.memory_percent?.toFixed(2) ?? "--"}%
                </dd>
                <dt>Nice</dt>
                <dd className="mono">{selected.nice ?? "Unavailable"}</dd>
                <dt>CPU affinity</dt>
                <dd className="mono">
                  {selected.cpu_affinity?.join(", ") ?? "Unavailable"}
                </dd>
                <dt>ARC state</dt>
                <dd>
                  {selected.arc_managed ? (
                    <span className="badge green">Managed</span>
                  ) : (
                    "Not managed"
                  )}
                </dd>
              </dl>
              <div style={{ marginTop: 18 }}>
                <div className="page-kicker">Command</div>
                <div className="details">
                  {selected.cmdline || "Command line unavailable"}
                </div>
              </div>
              {selected.active_contract_ids.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div className="page-kicker">Associated contracts</div>
                  {selected.active_contract_ids.map((id) => (
                    <div className="list-primary mono" key={id}>
                      {id}
                    </div>
                  ))}
                </div>
              )}
              <p
                className="panel-subtle"
                style={{ marginTop: 18, lineHeight: 1.5 }}
              >
                This inspector is read-only. ARC applies resource changes only
                through validated contracts.
              </p>
            </div>
          </aside>
        )}
      </div>
    </main>
  );
}

function Sortable({
  label,
  value,
  current,
  descending,
  onClick,
}: {
  label: string;
  value: SortKey;
  current: SortKey;
  descending: boolean;
  onClick: (key: SortKey) => void;
}) {
  return (
    <th>
      <button
        onClick={() => onClick(value)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 4,
          color: current === value ? "#d9dade" : "inherit",
        }}
      >
        {label}
        <ChevronDown
          size={10}
          style={{
            transform:
              current === value && !descending ? "rotate(180deg)" : "none",
            opacity: current === value ? 1 : 0.35,
          }}
        />
      </button>
    </th>
  );
}
