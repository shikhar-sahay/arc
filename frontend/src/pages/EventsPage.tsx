import { useMemo, useState } from "react";
import { ClipboardList, Filter, RefreshCw, Search } from "lucide-react";
import { ArcEvent } from "../types";
import { formatFullTimestamp, formatSecondsAgo } from "../lib/utils";

interface Props {
  events: ArcEvent[];
  loading: boolean;
  onRefresh: () => void;
}
function category(type: string) {
  if (type.includes("restor")) return "restoration";
  if (type.includes("activ")) return "activation";
  if (type.includes("enforcement") || type.includes("resource_action"))
    return "enforcement";
  if (type.includes("fail") || type.includes("error")) return "failure";
  if (type.includes("engine")) return "engine";
  return "evaluation";
}

export function EventsPage({ events, loading, onRefresh }: Props) {
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState("all");
  const [kind, setKind] = useState("all");
  const [contract, setContract] = useState("all");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const contracts = useMemo(
    () =>
      [
        ...new Set(
          events.flatMap((event) =>
            event.contract_id ? [event.contract_id] : [],
          ),
        ),
      ].sort(),
    [events],
  );
  const filtered = useMemo(
    () =>
      events.filter((event) => {
        const text = query.toLowerCase();
        return (
          (severity === "all" || event.severity === severity) &&
          (kind === "all" || category(event.type) === kind) &&
          (contract === "all" || event.contract_id === contract) &&
          (!text ||
            `${event.message} ${event.type} ${event.pid ?? ""} ${event.contract_id ?? ""}`
              .toLowerCase()
              .includes(text))
        );
      }),
    [events, query, severity, kind, contract],
  );
  const toggle = (seq: number) =>
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(seq)) next.delete(seq);
      else next.add(seq);
      return next;
    });
  return (
    <main className="page">
      <header className="page-header">
        <div>
          <div className="page-kicker">Observability</div>
          <h1 className="page-title">Audit Log</h1>
          <p className="page-description">
            Bounded in-memory lifecycle history. Events distinguish decisions,
            verified enforcement, restoration, and failures.
          </p>
        </div>
        <div className="page-actions">
          <span className="badge">
            {filtered.length} of {events.length}
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
          style={{ flex: 1, minWidth: 210 }}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search events, contracts, or PIDs"
        />
        <Filter size={13} style={{ color: "var(--faint)" }} />
        <select
          className="field"
          style={{ width: "auto" }}
          value={kind}
          onChange={(event) => setKind(event.target.value)}
        >
          <option value="all">All categories</option>
          {[
            "engine",
            "evaluation",
            "activation",
            "enforcement",
            "restoration",
            "failure",
          ].map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
        <select
          className="field"
          style={{ width: "auto" }}
          value={severity}
          onChange={(event) => setSeverity(event.target.value)}
        >
          <option value="all">All severity</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="error">Error</option>
        </select>
        {contracts.length > 0 && (
          <select
            className="field"
            style={{ width: "auto" }}
            value={contract}
            onChange={(event) => setContract(event.target.value)}
          >
            <option value="all">All contracts</option>
            {contracts.map((id) => (
              <option key={id}>{id}</option>
            ))}
          </select>
        )}
      </div>
      <section className="panel">
        <div className="timeline">
          {filtered.map((event) => {
            const detail =
              event.details && Object.keys(event.details).length > 0;
            const successful = [
              "contract_activated",
              "contract_restored",
              "resource_action_applied",
              "resource_restored",
            ].includes(event.type);
            return (
              <article className="timeline-event" key={event.seq}>
                <div className="timeline-node">
                  <span
                    className={
                      event.severity === "error"
                        ? "error"
                        : event.severity === "warning"
                          ? "warning"
                          : successful
                            ? "success"
                            : ""
                    }
                  />
                </div>
                <div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      flexWrap: "wrap",
                    }}
                  >
                    <span className="badge">{category(event.type)}</span>
                    <span className="timeline-message">{event.message}</span>
                  </div>
                  <div className="timeline-meta">
                    <span>{formatFullTimestamp(event.timestamp)}</span>
                    <span>{formatSecondsAgo(event.timestamp)}</span>
                    <span className="mono">#{event.seq}</span>
                    {event.contract_id && (
                      <span className="mono">contract {event.contract_id}</span>
                    )}
                    {event.pid != null && (
                      <span className="mono">PID {event.pid}</span>
                    )}
                    {detail && (
                      <button
                        onClick={() => toggle(event.seq)}
                        style={{ color: "var(--blue)" }}
                      >
                        {expanded.has(event.seq)
                          ? "Hide details"
                          : "Show details"}
                      </button>
                    )}
                  </div>
                  {detail && expanded.has(event.seq) && (
                    <pre className="details">
                      {JSON.stringify(event.details, null, 2)}
                    </pre>
                  )}
                </div>
              </article>
            );
          })}
          {!filtered.length && (
            <div className="empty">
              <div>
                <div className="empty-icon">
                  <ClipboardList size={18} />
                </div>
                <strong>
                  {events.length
                    ? "No events match these filters"
                    : "No engine events yet"}
                </strong>
                <p>
                  {events.length
                    ? "Clear or adjust the filters to broaden the timeline."
                    : "ARC keeps up to 500 transition events in memory. This is not durable storage."}
                </p>
              </div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
