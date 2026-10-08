import { useState, useMemo } from "react";
import { ArcEvent } from "../types";
import { SeverityBadge } from "../components/Badge";
import { formatFullTimestamp, formatSecondsAgo } from "../lib/utils";

interface EventsPageProps {
  events: ArcEvent[];
  loading: boolean;
  onRefresh: () => void;
}

export function EventsPage({ events, loading, onRefresh }: EventsPageProps) {
  const [filterText, setFilterText] = useState("");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [contractFilter, setContractFilter] = useState("all");
  const [expandedSeq, setExpandedSeq] = useState<Set<number>>(new Set());

  // Extract unique contract IDs from events
  const uniqueContractIds = useMemo(() => {
    const ids = new Set<string>();
    for (const ev of events) {
      if (ev.contract_id) {
        ids.add(ev.contract_id);
      }
    }
    return Array.from(ids).sort();
  }, [events]);

  const toggleExpand = (seq: number) => {
    setExpandedSeq((prev) => {
      const next = new Set(prev);
      if (next.has(seq)) {
        next.delete(seq);
      } else {
        next.add(seq);
      }
      return next;
    });
  };

  const filteredEvents = useMemo(() => {
    return events.filter((ev) => {
      if (severityFilter !== "all" && ev.severity !== severityFilter) {
        return false;
      }
      if (contractFilter !== "all" && ev.contract_id !== contractFilter) {
        return false;
      }
      if (!filterText) return true;
      const q = filterText.toLowerCase();
      return (
        ev.message.toLowerCase().includes(q) ||
        ev.type.toLowerCase().includes(q) ||
        (ev.contract_id && ev.contract_id.toLowerCase().includes(q)) ||
        (ev.pid !== undefined &&
          ev.pid !== null &&
          String(ev.pid).includes(q)) ||
        String(ev.seq).includes(q)
      );
    });
  }, [events, severityFilter, contractFilter, filterText]);

  // Counts by severity
  const severityCounts = useMemo(() => {
    let error = 0;
    let warning = 0;
    let info = 0;
    for (const ev of events) {
      if (ev.severity === "error") error++;
      else if (ev.severity === "warning") warning++;
      else info++;
    }
    return { error, warning, info, total: events.length };
  }, [events]);

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-lg font-bold text-slate-100">
              Engine Audit Log
            </h1>
            <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
              {filteredEvents.length} / {events.length} events
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Immutable timeline of policy evaluations, state snapshots, resource
            mutations, and rollbacks.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={onRefresh}
            disabled={loading}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs font-mono text-slate-200 transition flex items-center space-x-1.5 disabled:opacity-50"
          >
            <span>{loading ? "Refreshing..." : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* Filter / Controls Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 flex flex-wrap items-center gap-3">
        {/* Search Input */}
        <div className="flex-1 min-w-[220px]">
          <input
            type="text"
            placeholder="Search by message, PID, type, contract ID..."
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            className="w-full px-3 py-1.5 bg-slate-950 border border-slate-800 rounded text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>

        {/* Severity Selector */}
        <div className="flex items-center space-x-1 bg-slate-950 border border-slate-800 rounded p-0.5 text-xs font-mono">
          <button
            onClick={() => setSeverityFilter("all")}
            className={`px-2.5 py-1 rounded transition ${
              severityFilter === "all"
                ? "bg-slate-800 text-slate-100 font-bold"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            All ({severityCounts.total})
          </button>
          <button
            onClick={() => setSeverityFilter("info")}
            className={`px-2.5 py-1 rounded transition ${
              severityFilter === "info"
                ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800/60"
                : "text-slate-400 hover:text-cyan-300"
            }`}
          >
            Info ({severityCounts.info})
          </button>
          <button
            onClick={() => setSeverityFilter("warning")}
            className={`px-2.5 py-1 rounded transition ${
              severityFilter === "warning"
                ? "bg-amber-950 text-amber-300 font-bold border border-amber-800/60"
                : "text-slate-400 hover:text-amber-300"
            }`}
          >
            Warn ({severityCounts.warning})
          </button>
          <button
            onClick={() => setSeverityFilter("error")}
            className={`px-2.5 py-1 rounded transition ${
              severityFilter === "error"
                ? "bg-rose-950 text-rose-300 font-bold border border-rose-800/60"
                : "text-slate-400 hover:text-rose-300"
            }`}
          >
            Error ({severityCounts.error})
          </button>
        </div>

        {/* Contract Filter Dropdown */}
        {uniqueContractIds.length > 0 && (
          <div className="flex items-center space-x-2">
            <span className="text-[11px] font-mono text-slate-400">
              Contract:
            </span>
            <select
              value={contractFilter}
              onChange={(e) => setContractFilter(e.target.value)}
              className="px-2.5 py-1.5 bg-slate-950 border border-slate-800 rounded text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
            >
              <option value="all">All Contracts</option>
              {uniqueContractIds.map((cid) => (
                <option key={cid} value={cid}>
                  {cid}
                </option>
              ))}
            </select>
          </div>
        )}

        {(filterText ||
          severityFilter !== "all" ||
          contractFilter !== "all") && (
          <button
            onClick={() => {
              setFilterText("");
              setSeverityFilter("all");
              setContractFilter("all");
            }}
            className="text-xs font-mono text-slate-400 hover:text-slate-200 underline ml-auto"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Events List */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden divide-y divide-slate-800/80 font-mono text-xs">
        {filteredEvents.map((ev) => {
          const isExpanded = expandedSeq.has(ev.seq);
          const hasDetails = ev.details && Object.keys(ev.details).length > 0;

          return (
            <div
              key={ev.seq}
              className={`p-3.5 hover:bg-slate-800/40 transition ${
                hasDetails ? "cursor-pointer" : ""
              } ${isExpanded ? "bg-slate-800/30" : ""}`}
              onClick={() => hasDetails && toggleExpand(ev.seq)}
            >
              <div className="flex items-start space-x-3">
                {/* Sequence number */}
                <span className="text-slate-500 text-[11px] w-12 text-right shrink-0 pt-0.5">
                  #{ev.seq}
                </span>

                {/* Severity Badge */}
                <div className="shrink-0 pt-0.5">
                  <SeverityBadge severity={ev.severity} />
                </div>

                {/* Event Type */}
                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase shrink-0 bg-slate-950 text-slate-300 border border-slate-800 pt-0.5">
                  {ev.type}
                </span>

                {/* Main Content */}
                <div className="flex-1 min-w-0 space-y-1">
                  <div className="text-slate-200 font-sans text-xs leading-relaxed font-medium">
                    {ev.message}
                  </div>

                  {/* Metadata Row */}
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-slate-500 text-[11px]">
                    {ev.contract_id && (
                      <span className="text-cyan-400/90">
                        Contract:{" "}
                        <span className="font-bold">{ev.contract_id}</span>
                      </span>
                    )}
                    {ev.pid !== undefined && ev.pid !== null && (
                      <span className="text-amber-400/90">
                        PID: <span className="font-bold">{ev.pid}</span>
                      </span>
                    )}
                    <span
                      title={`Timestamp: ${ev.timestamp}s`}
                      className="text-slate-400"
                    >
                      {formatFullTimestamp(ev.timestamp)} (
                      {formatSecondsAgo(ev.timestamp)})
                    </span>

                    {hasDetails && (
                      <span className="text-slate-400 text-[10px] underline ml-auto">
                        {isExpanded ? "hide details ▲" : "view details ▼"}
                      </span>
                    )}
                  </div>

                  {/* Expanded Structured Details */}
                  {isExpanded && hasDetails && (
                    <div
                      className="mt-2.5 p-3 rounded bg-slate-950/70 border border-slate-800/80 space-y-1.5 text-xs"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                        Structured Event Details
                      </div>
                      <pre className="text-[11px] text-slate-300 overflow-x-auto whitespace-pre-wrap font-mono">
                        {JSON.stringify(ev.details, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {filteredEvents.length === 0 && (
          <div className="p-12 text-center text-slate-500 font-sans">
            <div className="text-sm font-semibold text-slate-400">
              No events found
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Try adjusting your filter query or severity selection.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
