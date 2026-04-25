import type { LogsResponse, NodeItem, Overview, SettingsResponse, TrafficResponse } from "./types";

export class ApiError extends Error {
  status: number;
  details?: Record<string, unknown>;

  constructor(message: string, status: number, details?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });

  if (!response.ok) {
    let message = response.statusText;
    let details: Record<string, unknown> | undefined;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") {
        message = data.detail;
      } else if (data.detail && typeof data.detail === "object") {
        details = data.detail;
        message = String(data.detail.message ?? message);
      } else {
        message = data.message ?? message;
      }
    } catch {
      // noop
    }
    throw new ApiError(message, response.status, details);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (password: string) => request<{ ok: boolean }>("/api/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  session: () => request<{ ok: boolean; username: string; expiresAt: number }>("/api/auth/session"),
  overview: () => request<Overview>("/api/overview"),
  nodes: () => request<{ items: NodeItem[] }>("/api/nodes"),
  activateNode: (nodeId: string) => request<{ ok: boolean }>(`/api/nodes/${nodeId}/activate`, { method: "POST" }),
  favoriteNode: (nodeId: string, favorite: boolean) =>
    request<{ ok: boolean }>(`/api/nodes/${nodeId}/favorite`, { method: "POST", body: JSON.stringify({ favorite }) }),
  renameNode: (nodeId: string, label: string) =>
    request<{ ok: boolean }>(`/api/nodes/${nodeId}/rename`, { method: "POST", body: JSON.stringify({ label }) }),
  traffic: (range: string, nodeId?: string, service?: string) => {
    const search = new URLSearchParams({ range });
    if (nodeId) search.set("node_id", nodeId);
    if (service) search.set("service", service);
    return request<TrafficResponse>(`/api/traffic?${search.toString()}`);
  },
  logs: (source = "combined", query = "", limit = 200) => {
    const search = new URLSearchParams({ source, query, limit: String(limit) });
    return request<LogsResponse>(`/api/logs?${search.toString()}`);
  },
  action: (action: string, target: string) =>
    request<{ ok: boolean; message: string }>(`/api/actions/${action}`, { method: "POST", body: JSON.stringify({ target }) }),
  latencyTest: (nodeId?: string) =>
    request<Record<string, unknown>>("/api/diagnostics/latency-test", { method: "POST", body: JSON.stringify({ node_id: nodeId }) }),
  latencyMap: () => request<{ items: Array<{ node_id: string; label: string; ok: boolean; median_ms?: number; samples?: number[]; message?: string }> }>("/api/diagnostics/latency-map"),
  siteLatency: () =>
    request<{
      items: Array<{
        name: string;
        host: string;
        ip: string;
        dns_ms?: number | null;
        tcp_ms?: number | null;
        tls_ms?: number | null;
        total_ms?: number | null;
        ok: boolean;
        message?: string;
      }>;
    }>("/api/diagnostics/site-latency"),
  dnsCheck: (nodeId?: string) =>
    request<Record<string, unknown>>("/api/diagnostics/dns-check", { method: "POST", body: JSON.stringify({ node_id: nodeId }) }),
  configValidate: () => request<Record<string, unknown>>("/api/diagnostics/config-validate", { method: "POST" }),
  settings: () => request<SettingsResponse>("/api/settings"),
  updateSettings: (payload: { password?: string; ipWhitelist: string }) =>
    request<{ ok: boolean }>("/api/settings", { method: "PUT", body: JSON.stringify(payload) }),
};
