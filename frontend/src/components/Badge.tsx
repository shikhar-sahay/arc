import { LifecycleState } from "../types";

interface LifecycleBadgeProps {
  lifecycle: LifecycleState;
  className?: string;
}

const lifecycleStyles: Record<LifecycleState, string> = {
  active: "bg-emerald-950 text-emerald-300 border-emerald-800",
  activating: "bg-cyan-950 text-cyan-300 border-cyan-800",
  restoring: "bg-indigo-950 text-indigo-300 border-indigo-800",
  error: "bg-rose-950 text-rose-300 border-rose-800",
  inactive: "bg-slate-800 text-slate-400 border-slate-700",
};

export function LifecycleBadge({
  lifecycle,
  className = "",
}: LifecycleBadgeProps) {
  const style = lifecycleStyles[lifecycle] ?? lifecycleStyles.inactive;
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wide font-mono ${style} ${className}`}
    >
      {lifecycle === "activating" && (
        <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse mr-1" />
      )}
      {lifecycle === "active" && (
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse mr-1" />
      )}
      {lifecycle === "restoring" && (
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse mr-1" />
      )}
      {lifecycle}
    </span>
  );
}

interface SeverityBadgeProps {
  severity: string;
  className?: string;
}

export function SeverityBadge({
  severity,
  className = "",
}: SeverityBadgeProps) {
  const lower = severity.toLowerCase();
  let style = "bg-slate-800 text-slate-400 border-slate-700";
  if (lower === "error") style = "bg-rose-950 text-rose-300 border-rose-800";
  else if (lower === "warning")
    style = "bg-amber-950 text-amber-300 border-amber-800";
  else if (lower === "info")
    style = "bg-cyan-950 text-cyan-300 border-cyan-800";
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wide font-mono ${style} ${className}`}
    >
      {severity}
    </span>
  );
}
