import { useState } from "react";
import { ProcessItem } from "../types";

interface ProcessesPageProps {
  processes: ProcessItem[];
  totalObserved: number;
  loading: boolean;
  onRefresh: () => void;
}

type SortKey = "pid" | "cpu" | "mem" | "nice" | "name";
type SortDir = "asc" | "desc";

export function ProcessesPage({
  processes,
  totalObserved,
  loading,
  onRefresh,
}: ProcessesPageProps) {
  const [filter, setFilter] = useState("");
  const [onlyManaged, setOnlyManaged] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("cpu");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  function sortIndicator(key: SortKey) {
    if (sortKey !== key) return <span className="text-slate-700 ml-1">↕</span>;
    return (
      <span className="text-cyan-400 ml-1">
        {sortDir === "desc" ? "↓" : "↑"}
      </span>
    );
  }

  const filtered = processes
    .filter((p) => {
      if (onlyManaged && !p.arc_managed) return false;
      if (!filter) return true;
      const q = filter.toLowerCase();
      return (
        String(p.pid).includes(q) ||
        (p.name ?? "").toLowerCase().includes(q) ||
        (p.cmdline ?? "").toLowerCase().includes(q)
      );
    })
    .sort((a, b) => {
      let va: number | string = 0;
      let vb: number | string = 0;
      switch (sortKey) {
        case "pid":
          va = a.pid;
          vb = b.pid;
          break;
        case "cpu":
          va = a.cpu_percent ?? -1;
          vb = b.cpu_percent ?? -1;
          break;
        case "mem":
          va = a.memory_percent ?? -1;
          vb = b.memory_percent ?? -1;
          break;
        case "nice":
          va = a.nice ?? 0;
          vb = b.nice ?? 0;
          break;
        case "name":
          va = (a.name ?? "").toLowerCase();
          vb = (b.name ?? "").toLowerCase();
          break;
      }
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <h1 className="text-base font-bold text-slate-100 font-mono">
            Linux Process Observation
          </h1>
          <p className="text-xs text-slate-500 mt-0.5 font-mono">
            Read-only snapshot. Mutation is contract-driven only.
            {totalObserved > 0 && (
              <span className="text-slate-600 ml-1">
                {totalObserved} processes observed, showing {processes.length}.
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {loading && (
            <span className="text-xs text-slate-500 font-mono animate-pulse">
              Updating...
            </span>
          )}
          <label className="flex items-center space-x-2 text-xs font-mono text-slate-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={onlyManaged}
              onChange={(e) => setOnlyManaged(e.target.checked)}
              className="rounded bg-slate-900 border-slate-600 text-cyan-600 focus:ring-0 focus:ring-offset-0"
            />
            <span>ARC-managed only</span>
          </label>
          <input
            type="text"
            aria-label="Filter processes"
            placeholder="Filter PID, name, cmd..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-600 w-56"
          />
          <button
            onClick={onRefresh}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs font-mono text-slate-300 transition"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Process table */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-950 text-slate-500 font-mono uppercase text-[10px] border-b border-slate-800">
            <tr>
              <th
                className="px-4 py-3 cursor-pointer hover:text-slate-300 select-none"
                onClick={() => toggleSort("pid")}
              >
                PID {sortIndicator("pid")}
              </th>
              <th
                className="px-4 py-3 cursor-pointer hover:text-slate-300 select-none"
                onClick={() => toggleSort("name")}
              >
                Name {sortIndicator("name")}
              </th>
              <th className="px-4 py-3">Command</th>
              <th
                className="px-4 py-3 cursor-pointer hover:text-slate-300 select-none"
                onClick={() => toggleSort("cpu")}
              >
                CPU% {sortIndicator("cpu")}
              </th>
              <th
                className="px-4 py-3 cursor-pointer hover:text-slate-300 select-none"
                onClick={() => toggleSort("mem")}
              >
                MEM% {sortIndicator("mem")}
              </th>
              <th
                className="px-4 py-3 cursor-pointer hover:text-slate-300 select-none"
                onClick={() => toggleSort("nice")}
              >
                Nice {sortIndicator("nice")}
              </th>
              <th className="px-4 py-3">Affinity</th>
              <th className="px-4 py-3 text-right">ARC</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 font-mono">
            {filtered.length === 0 ? (
              <tr>
                <td
                  colSpan={8}
                  className="px-4 py-10 text-center text-slate-600 font-sans"
                >
                  {loading
                    ? "Loading processes..."
                    : filter || onlyManaged
                      ? "No matching processes."
                      : "No processes observed. Is the backend running?"}
                </td>
              </tr>
            ) : (
              filtered.map((p) => (
                <tr
                  key={p.pid}
                  className={`hover:bg-slate-800/30 transition text-xs ${
                    p.arc_managed ? "bg-cyan-950/10" : ""
                  }`}
                >
                  <td className="px-4 py-2 font-bold text-slate-400">
                    {p.pid}
                  </td>
                  <td className="px-4 py-2 text-slate-200 font-bold">
                    {p.name ?? "-"}
                  </td>
                  <td
                    className="px-4 py-2 text-slate-500 max-w-xs truncate"
                    title={p.cmdline ?? ""}
                  >
                    {p.cmdline ? (
                      <span className="text-slate-500">{p.cmdline}</span>
                    ) : (
                      <span className="text-slate-700">-</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {p.cpu_percent !== null && p.cpu_percent !== undefined ? (
                      <span
                        className={
                          p.cpu_percent > 80
                            ? "text-rose-400"
                            : p.cpu_percent > 40
                              ? "text-amber-400"
                              : "text-slate-300"
                        }
                      >
                        {p.cpu_percent.toFixed(1)}%
                      </span>
                    ) : (
                      <span className="text-slate-700">-</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {p.memory_percent !== null &&
                    p.memory_percent !== undefined ? (
                      <span
                        className={
                          p.memory_percent > 50
                            ? "text-amber-400"
                            : "text-slate-300"
                        }
                      >
                        {p.memory_percent.toFixed(1)}%
                      </span>
                    ) : (
                      <span className="text-slate-700">-</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {p.nice !== null && p.nice !== undefined ? (
                      <span
                        className={
                          p.nice < 0
                            ? "text-cyan-400"
                            : p.nice > 0
                              ? "text-slate-500"
                              : "text-slate-400"
                        }
                      >
                        {p.nice > 0 ? `+${p.nice}` : p.nice}
                      </span>
                    ) : (
                      <span className="text-slate-700">-</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-[10px] text-slate-500">
                    {p.cpu_affinity && p.cpu_affinity.length > 0 ? (
                      `[${p.cpu_affinity.join(",")}]`
                    ) : (
                      <span className="text-slate-700">-</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {p.arc_managed ? (
                      <span
                        className="bg-cyan-950 border border-cyan-900 text-cyan-300 text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wide"
                        title={`Contracts: ${p.active_contract_ids.join(", ")}`}
                      >
                        Managed
                      </span>
                    ) : (
                      <span className="text-slate-700 text-[10px]">-</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {filtered.length > 0 && (
        <div className="text-[10px] text-slate-700 font-mono text-right">
          Showing {filtered.length} of {processes.length} processes
          {onlyManaged ? " (ARC-managed only)" : ""}
        </div>
      )}
    </div>
  );
}
