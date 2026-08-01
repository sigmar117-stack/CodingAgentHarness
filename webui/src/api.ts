// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface StatusResponse {
  state: string;
  session_id: string;
  current_turn: number;
  total_turns: number;
  task: string;
}

export interface ToolInfo {
  name: string;
  description: string;
  risk_level: string;
}

export interface SessionSummary {
  session_id: string;
  created_at: string;
  updated_at: string;
  status: string;
  task_description: string;
  total_turns: number;
  total_tool_calls: number;
  summary: string;
}

export interface SessionDetail extends SessionSummary {
  turns: TurnRecordModel[];
}

export interface TurnRecordModel {
  turn_number: number;
  llm_response: string | null;
  tool_calls: ToolCallData[];
  tool_results: ToolResultData[];
  guardrail_result: GuardrailResultData | null;
  approval_decision: string | null;
  has_test_result: boolean;
  classification: string | null;
  timestamp: string | null;
}

export interface ToolCallData {
  name: string;
  arguments: Record<string, unknown>;
  id: string;
}

export interface ToolResultData {
  success: boolean;
  output: string;
  error: string | null;
}

export interface GuardrailResultData {
  is_dangerous: boolean;
  risk_reason: string;
}

export interface WSMessage {
  type: 'state_change' | 'turn_complete' | 'approval_request' | 'error' | 'log' | 'pong';
  data: Record<string, unknown>;
  timestamp: string;
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  getStatus: () => request<StatusResponse>('/status'),

  runTask: (task: string, planOnly = false) =>
    request<{ session_id: string; status: string; message: string }>('/run', {
      method: 'POST',
      body: JSON.stringify({ task, plan_only: planOnly }),
    }),

  cancelTask: () =>
    request<{ status: string; message: string }>('/cancel', { method: 'POST' }),

  listSessions: () => request<SessionSummary[]>('/sessions'),

  getSession: (id: string) => request<SessionDetail>(`/sessions/${id}`),

  deleteSession: (id: string) =>
    request<{ status: string; message: string }>(`/sessions/${id}`, { method: 'DELETE' }),

  approve: (sessionId: string, decision: string, modifiedParams?: Record<string, unknown>) =>
    request<{ status: string; decision: string }>('/approve', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        decision,
        modified_params: modifiedParams,
      }),
    }),

  listTools: () => request<ToolInfo[]>('/tools'),

  getVersion: () => request<{ version: string }>('/version'),
};

// ---------------------------------------------------------------------------
// WebSocket connection
// ---------------------------------------------------------------------------

type MessageHandler = (msg: WSMessage) => void;

export function connectWebSocket(onMessage: MessageHandler): () => void {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}${BASE}/ws`;
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  function connect() {
    if (closed) return;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected');
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        onMessage(msg);
      } catch (e) {
        console.error('Failed to parse WS message:', e);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      if (!closed) {
        reconnectTimer = setTimeout(connect, 2000);
      }
    };

    ws.onerror = () => {
      ws?.close();
    };
  }

  connect();

  return () => {
    closed = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    ws?.close();
  };
}