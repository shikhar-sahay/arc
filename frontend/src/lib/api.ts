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
  detail: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = (await res.json()) as ApiError;
      detail = err.detail || detail;
    } catch {
      // Ignore parse error
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async getStatus(): Promise<EngineStatus> {
    const res = await fetch("/api/status");
    return handleResponse<EngineStatus>(res);
  },

  async getSystem(): Promise<SystemTelemetry> {
    const res = await fetch("/api/system");
    return handleResponse<SystemTelemetry>(res);
  },

  async getContracts(): Promise<ContractListResponse> {
    const res = await fetch("/api/contracts");
    return handleResponse<ContractListResponse>(res);
  },

  async getProcesses(limit = 300): Promise<ProcessListResponse> {
    const res = await fetch(`/api/processes?limit=${limit}`);
    return handleResponse<ProcessListResponse>(res);
  },

  async getEvents(limit = 200): Promise<EventListResponse> {
    const res = await fetch(`/api/events?limit=${limit}`);
    return handleResponse<EventListResponse>(res);
  },

  async validateContract(
    payload: unknown,
  ): Promise<{ valid: boolean; error?: string }> {
    const res = await fetch("/api/contracts/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleResponse<{ valid: boolean; error?: string }>(res);
  },

  async createContract(contract: unknown): Promise<ContractStatus> {
    const res = await fetch("/api/contracts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(contract),
    });
    return handleResponse<ContractStatus>(res);
  },

  async updateContract(id: string, contract: unknown): Promise<ContractStatus> {
    const res = await fetch(`/api/contracts/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(contract),
    });
    return handleResponse<ContractStatus>(res);
  },

  async deleteContract(id: string): Promise<void> {
    const res = await fetch(`/api/contracts/${id}`, { method: "DELETE" });
    return handleResponse<void>(res);
  },

  async toggleEnabled(id: string, enabled: boolean): Promise<ContractStatus> {
    const res = await fetch(`/api/contracts/${id}/enabled`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    return handleResponse<ContractStatus>(res);
  },

  async resetContract(id: string): Promise<void> {
    const res = await fetch(`/api/contracts/${id}/reset`, { method: "POST" });
    return handleResponse<void>(res);
  },

  async reloadContracts(): Promise<{ status: string; contract_count: number }> {
    const res = await fetch("/api/engine/reload", { method: "POST" });
    return handleResponse<{ status: string; contract_count: number }>(res);
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
}): Omit<Contract, "version"> & { version: 1 } {
  return {
    version: 1,
    id: fields.id.trim(),
    name: fields.name.trim(),
    description: fields.description.trim() || null,
    enabled: true,
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
      value: parseFloat(fields.triggerVal),
      for_seconds: parseFloat(fields.triggerSec),
    },
    actions: fields.actions,
    restore: {
      metric: fields.restoreMetric,
      operator: fields.restoreOp,
      value: parseFloat(fields.restoreVal),
      for_seconds: parseFloat(fields.restoreSec),
    },
  };
}
