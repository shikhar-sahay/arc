import { LifecycleState } from "../types";

interface LifecycleBadgeProps {
  lifecycle: LifecycleState;
  className?: string;
}

const lifecycleStyles: Record<LifecycleState, string> = {
  active: "green",
  activating: "blue",
  restoring: "blue",
  error: "red",
  inactive: "",
};

export function LifecycleBadge({
  lifecycle,
  className = "",
}: LifecycleBadgeProps) {
  const style = lifecycleStyles[lifecycle] ?? lifecycleStyles.inactive;
  return (
    <span className={`badge ${style} ${className}`}>
      {lifecycle === "activating" && <span className="status-dot warn" />}
      {lifecycle === "active" && <span className="status-dot ok" />}
      {lifecycle === "restoring" && <span className="status-dot warn" />}
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
  let style = "";
  if (lower === "error") style = "red";
  else if (lower === "warning") style = "amber";
  else if (lower === "info") style = "blue";
  return <span className={`badge ${style} ${className}`}>{severity}</span>;
}
