/**
 * ARC API client.
 *
 * All mutation is done through typed fetch wrappers here.
 * GET requests never trigger enforcement - that invariant is maintained by the backend.
 */

import {
  ContractStatus,
  Contract,
  EngineStatus,
  SystemTelemetry,
  ProcessItem,
  ArcEvent,
  ResourceLabState,
} from "../types";

export interface ContractListResponse {
  contracts: ContractStatus[];
  count: number;
  load_errors: Array<{ file: string; error: string }>;
}

export interface ProcessListResponse {
  processes: ProcessItem[];
  count: number;
  limit: number;
  total_observed: number;
}

export interface EventListResponse {
  events: ArcEvent[];
  count: number;
  limit: number;
}

export interface ApiError {
  detail: unknown;
}

function errorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (!item || typeof item !== "object") return String(item);
        const issue = item as { loc?: unknown[]; msg?: string };
        const location = issue.loc?.slice(1).join(".");
        return `${location ? `${location}: ` : ""}${issue.msg ?? "Invalid value"}`;
      })
      .join("; ");
  }
  return fallback;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = (await res.json()) as ApiError;
      detail = errorDetail(err.detail, detail);
    } catch {
      // Ignore parse error
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const API_BASE = (import.meta.env.VITE_ARC_API_URL ?? "").replace(/\/$/, "");

function endpoint(path: string): string {
  return `${API_BASE}${path}`;
}

export const api = {
  async getStatus(): Promise<EngineStatus> {
    const res = await fetch(endpoint("/api/status"));
    return handleResponse<EngineStatus>(res);
  },

  async getSystem(): Promise<SystemTelemetry> {
    const res = await fetch(endpoint("/api/system"));
    return handleResponse<SystemTelemetry>(res);
  },

  async getContracts(): Promise<ContractListResponse> {
    const res = await fetch(endpoint("/api/contracts"));
    return handleResponse<ContractListResponse>(res);
  },

  async getProcesses(limit = 300): Promise<ProcessListResponse> {
    const res = await fetch(endpoint(`/api/processes?limit=${limit}`));
    return handleResponse<ProcessListResponse>(res);
  },

  async getEvents(limit = 200): Promise<EventListResponse> {
    const res = await fetch(endpoint(`/api/events?limit=${limit}`));
    return handleResponse<EventListResponse>(res);
  },

  async validateContract(
    payload: unknown,
  ): Promise<{ valid: boolean; error?: string }> {
    const res = await fetch(endpoint("/api/contracts/validate"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleResponse<{ valid: boolean; error?: string }>(res);
  },

  async createContract(contract: unknown): Promise<ContractStatus> {
    const res = await fetch(endpoint("/api/contracts"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(contract),
    });
    return handleResponse<ContractStatus>(res);
  },

  async updateContract(id: string, contract: unknown): Promise<ContractStatus> {
    const res = await fetch(endpoint(`/api/contracts/${id}`), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(contract),
    });
    return handleResponse<ContractStatus>(res);
  },

  async deleteContract(id: string): Promise<void> {
    const res = await fetch(endpoint(`/api/contracts/${id}`), {
      method: "DELETE",
    });
    return handleResponse<void>(res);
  },

  async toggleEnabled(id: string, enabled: boolean): Promise<ContractStatus> {
    const res = await fetch(endpoint(`/api/contracts/${id}/enabled`), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    return handleResponse<ContractStatus>(res);
  },

  async resetContract(id: string): Promise<void> {
    const res = await fetch(endpoint(`/api/contracts/${id}/reset`), {
      method: "POST",
    });
    return handleResponse<void>(res);
  },

  async reloadContracts(): Promise<{ status: string; contract_count: number }> {
    const res = await fetch(endpoint("/api/engine/reload"), { method: "POST" });
    return handleResponse<{ status: string; contract_count: number }>(res);
  },

  async getResourceLab(): Promise<ResourceLabState> {
    return handleResponse<ResourceLabState>(
      await fetch(endpoint("/api/resource-lab")),
    );
  },

  async startResourceLab(workers: number): Promise<ResourceLabState> {
    return handleResponse<ResourceLabState>(
      await fetch(endpoint("/api/resource-lab/start"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workers }),
      }),
    );
  },

  async setResourceLabPressure(high: boolean): Promise<ResourceLabState> {
    return handleResponse<ResourceLabState>(
      await fetch(endpoint("/api/resource-lab/pressure"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ high }),
      }),
    );
  },

  async setResourceLabPolicy(enabled: boolean): Promise<ResourceLabState> {
    return handleResponse<ResourceLabState>(
      await fetch(endpoint("/api/resource-lab/policy"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      }),
    );
  },

  async stopResourceLab(): Promise<ResourceLabState> {
    return handleResponse<ResourceLabState>(
      await fetch(endpoint("/api/resource-lab/stop"), { method: "POST" }),
    );
  },
};

export function buildContractPayload(fields: {
  id: string;
  name: string;
  description: string;
  executable: string;
  command: string;
  triggerMetric: string;
  triggerOp: string;
  triggerVal: string;
  triggerSec: string;
  actions: Contract["actions"];
  restoreMetric: string;
  restoreOp: string;
  restoreVal: string;
  restoreSec: string;
  enabled?: boolean;
}): Omit<Contract, "version"> & { version: 1 } {
  return {
    version: 1,
    id: fields.id.trim(),
    name: fields.name.trim(),
    description: fields.description.trim() || null,
    enabled: fields.enabled ?? true,
    target: {
      type: "process",
      match: {
        executable: fields.executable.trim() || null,
        command_contains: fields.command.trim() || null,
      },
    },
    trigger: {
      metric: fields.triggerMetric,
      operator: fields.triggerOp,
      value:
        fields.triggerMetric === "target.process.present"
          ? fields.triggerVal === "true"
          : parseFloat(fields.triggerVal),
      for_seconds: parseFloat(fields.triggerSec),
    },
    actions: fields.actions,
    restore: {
      metric: fields.restoreMetric,
      operator: fields.restoreOp,
      value:
        fields.restoreMetric === "target.process.present"
          ? fields.restoreVal === "true"
          : parseFloat(fields.restoreVal),
      for_seconds: parseFloat(fields.restoreSec),
    },
  };
}
