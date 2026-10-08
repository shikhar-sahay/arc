/** Format a Unix timestamp as a human-readable local time string. */
export function formatTimestamp(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000);
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

/** Format a Unix timestamp as a full date+time string. */
export function formatFullTimestamp(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

/** Format seconds ago from now. */
export function formatSecondsAgo(epochSeconds: number): string {
  const diff = Date.now() / 1000 - epochSeconds;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  return `${Math.round(diff / 3600)}h ago`;
}

export function formatCpuAffinity(cpus: number[] | null | undefined): string {
  if (!cpus?.length) return "--";
  const values = [...new Set(cpus)].sort((a, b) => a - b);
  const parts: string[] = [];
  let start = values[0];
  let end = start;
  for (const value of values.slice(1)) {
    if (value === end + 1) {
      end = value;
      continue;
    }
    parts.push(start === end ? `${start}` : `${start}–${end}`);
    start = end = value;
  }
  parts.push(start === end ? `${start}` : `${start}–${end}`);
  return parts.join(", ");
}

/** Convert an operator string to a human-readable symbol. */
export function opSymbol(op: string): string {
  switch (op) {
    case "gt":
      return ">";
    case "gte":
      return ">=";
    case "lt":
      return "<";
    case "lte":
      return "<=";
    case "eq":
      return "=";
    default:
      return op;
  }
}

/** Describe an action compactly. */
export function describeAction(act: {
  type: string;
  value?: number;
  cpus?: number[];
  quota_percent?: number;
}): string {
  switch (act.type) {
    case "nice":
      return `nice ${act.value! > 0 ? "+" : ""}${act.value}`;
    case "cpu_affinity":
      return `affinity [${act.cpus?.join(",")}]`;
    case "suspend":
      return "SIGSTOP suspend";
    case "resume":
      return "SIGCONT resume";
    case "cpu_quota":
      return `cpu.max ${act.quota_percent}%`;
    default:
      return act.type;
  }
}

export function isProtectedLifecycle(lifecycle: string): boolean {
  return ["activating", "active", "restoring"].includes(lifecycle);
}

export function lifecycleCounts(items: Array<{ lifecycle: string }>) {
  return {
    active: items.filter((item) => item.lifecycle === "active").length,
    activating: items.filter((item) => item.lifecycle === "activating").length,
    restoring: items.filter((item) => item.lifecycle === "restoring").length,
    error: items.filter((item) => item.lifecycle === "error").length,
    inactive: items.filter((item) => item.lifecycle === "inactive").length,
  };
}

/** Clamp a number to a range for display bars. */
export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
