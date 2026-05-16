// ---- Health ----
export interface HealthStatus {
  status: string;
  upstream: string;
}

// ---- Port process ----
export interface PortProcess {
  pid: string;
  raw_output: string;
}

// ---- Config ----
export interface GatewayConfig {
  model_map: Record<string, string>;
  visible_models: string[];
  default_model: string;
  force_anthropic_version: string | null;
  enable_cors: boolean;
  upstream_url: string;
}

// ---- Log ----
export interface LogContent {
  filename: string;
  content: string;
  line_count: number;
}

// ---- Log list entry ----
export interface LogListEntry {
  filename: string;
  size: number;
}

// ---- Raw config (for editing with encoding) ----
export interface RawConfigResponse {
  content: string;
  encoding_used: string;
}

// ---- Claude config discovery ----
export interface ClaudeConfigCandidate {
  path: string;
  exists: boolean;
  likely_config: boolean;
}

// ---- Proxy start result ----
export interface StartProxyResult {
  success: boolean;
  pid: number;
  python: string;
  dir: string;
  log: string;
}

// ---- Hook shape ----
export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}
