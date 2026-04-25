export interface ServiceStatusItem {
  active: boolean;
  status: string;
  uptime: string;
}

export interface Overview {
  appName: string;
  demoMode: boolean;
  serviceStatus: {
    xray: ServiceStatusItem;
    argo: ServiceStatusItem;
    stack: { healthy: boolean };
  };
  activeNode: NodeItem | null;
  nodeCount: number;
  favoriteCount: number;
  traffic: {
    download_bps: number;
    upload_bps: number;
  };
  errorCount: number;
  autostart: {
    xray: boolean;
    argo: boolean;
  };
  generatedAt: number;
}

export interface NodeItem {
  id: string;
  scheme: string;
  address: string;
  port: number;
  username: string;
  network: string;
  security: string;
  encryption?: string;
  host: string;
  path: string;
  sni: string;
  flow: string;
  fingerprint: string;
  label: string;
  favorite: boolean;
  active: boolean;
  raw_link: string;
}

export interface TrafficPoint {
  ts: number;
  download_bps: number;
  upload_bps: number;
  node_id?: string;
  service: string;
}

export interface TrafficResponse {
  range: string;
  series: TrafficPoint[];
  services: string[];
  nodes: string[];
}

export interface LogEntry {
  id?: number;
  ts: number;
  source?: string;
  line?: string;
  level?: string;
  action?: string;
  message?: string;
  metadata?: Record<string, unknown>;
}

export interface LogsResponse {
  source: string;
  entries: LogEntry[];
}

export interface SettingsResponse {
  ipWhitelist: string;
  sampleIntervalSeconds: number;
  bindHost: string;
  bindPort: number;
  demoMode: boolean;
  clashSubscriptionUrl: string;
  shadowrocketSubscriptionUrl: string;
  auditLogs: LogEntry[];
}
