import { useEffect, useState } from "react";

interface HealthState {
  app: string;
  status: string;
  platform: string;
}

interface SystemState {
  cpu_percent: number;
  memory_percent: number;
  cpu_count: number;
}

type BackendState =
  | { kind: "loading" }
  | { kind: "ok"; health: HealthState }
  | { kind: "error"; message: string };

const API_BASE = import.meta.env.VITE_ARC_API_URL ?? "";

export default function App() {
  const [backend, setBackend] = useState<BackendState>({ kind: "loading" });
  const [system, setSystem] = useState<SystemState | null>(null);
  const [contractCount, setContractCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      try {
        const response = await fetch(`${API_BASE}/api/health`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const health = (await response.json()) as HealthState;
        if (!cancelled) {
          setBackend({ kind: "ok", health });
        }
      } catch (error) {
        if (!cancelled) {
          setBackend({
            kind: "error",
            message:
              error instanceof Error
                ? error.message
                : "Could not reach the backend.",
          });
        }
      }
    }

    async function loadEngineState() {
      try {
        const [systemResponse, contractsResponse] = await Promise.all([
          fetch(`${API_BASE}/api/system`),
          fetch(`${API_BASE}/api/contracts`),
        ]);
        if (cancelled) {
          return;
        }
        if (systemResponse.ok) {
          setSystem((await systemResponse.json()) as SystemState);
        }
        if (contractsResponse.ok) {
          const payload = (await contractsResponse.json()) as {
            count: number;
          };
          setContractCount(payload.count);
        }
      } catch {
        // Live values stay unavailable. Health box already covers errors.
      }
    }

    void loadHealth();
    void loadEngineState();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6">
      <section className="w-full max-w-xl rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          Operating Systems Project
        </p>
        <h1 className="mt-2 text-3xl font-bold text-slate-900">ARC</h1>
        <p className="text-lg text-slate-700">
          Adaptive Resource Contract Engine
        </p>
        <p className="mt-4 text-slate-600">
          ARC is an event-driven Linux policy engine that applies user-defined
          resource contracts when runtime conditions hold, and restores prior
          resource state when they no longer apply.
        </p>
        <div className="mt-6 rounded-md bg-slate-100 p-4">
          <h2 className="text-sm font-semibold text-slate-800">
            Backend connectivity
          </h2>
          {backend.kind === "loading" && (
            <p className="mt-1 text-sm text-slate-600">
              Checking backend health...
            </p>
          )}
          {backend.kind === "ok" && (
            <p className="mt-1 text-sm text-slate-700">
              Connected: {backend.health.app} reports status{" "}
              <span className="font-mono">{backend.health.status}</span> on
              platform{" "}
              <span className="font-mono">{backend.health.platform}</span>.
            </p>
          )}
          {backend.kind === "error" && (
            <p className="mt-1 text-sm text-slate-700">
              Backend not reachable ({backend.message}). Start the API with{" "}
              <span className="font-mono">
                uvicorn arc.api.app:app --port 8000
              </span>{" "}
              from backend/.
            </p>
          )}
        </div>
        <div className="mt-6 rounded-md bg-slate-100 p-4">
          <h2 className="text-sm font-semibold text-slate-800">
            Live engine state (read-only)
          </h2>
          {system === null && contractCount === null ? (
            <p className="mt-1 text-sm text-slate-600">
              Waiting for live values...
            </p>
          ) : (
            <p className="mt-1 text-sm text-slate-700">
              CPU{" "}
              <span className="font-mono">
                {system === null ? "n/a" : `${system.cpu_percent.toFixed(1)}%`}
              </span>
              , memory{" "}
              <span className="font-mono">
                {system === null
                  ? "n/a"
                  : `${system.memory_percent.toFixed(1)}%`}
              </span>
              , contracts loaded{" "}
              <span className="font-mono">
                {contractCount === null ? "n/a" : contractCount}
              </span>
              .
            </p>
          )}
        </div>
        <p className="mt-4 text-xs text-slate-500">
          Temporary scaffolding page. Engine monitoring and contract views
          arrive in later passes.
        </p>
      </section>
    </main>
  );
}
