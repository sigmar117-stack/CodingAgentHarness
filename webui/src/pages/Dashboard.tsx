import React, { useEffect } from 'react';
import { useAppContext } from '../context';
import { api, connectWebSocket } from '../api';
import StatusBadge from '../components/StatusBadge';
import TurnLog from '../components/TurnLog';
import ApprovalModal from '../components/ApprovalModal';

export default function Dashboard() {
  const { state, handleWSMessage } = useAppContext();

  useEffect(() => {
    // Fetch initial status
    api.getStatus().then((s) => {
      handleWSMessage({ type: 'state_change', data: s as unknown as Record<string, unknown>, timestamp: '' });
    }).catch(() => {});

    // Connect WebSocket
    const disconnect = connectWebSocket(handleWSMessage);
    return disconnect;
  }, [handleWSMessage]);

  const recentTurns = state.turns.slice(-10);

  return (
    <div>
      {/* Header */}
      <div style={headerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h1 style={{ margin: 0, fontSize: 24 }}>CodingKit</h1>
          <StatusBadge state={state.status.state} />
        </div>
        {state.status.task && (
          <div style={{ fontSize: 14, color: '#374151', marginTop: 4 }}>
            {state.status.task}
          </div>
        )}
        <div style={statsStyle}>
          <span>Session: <code>{state.status.session_id?.slice(0, 8) || '—'}</code></span>
          <span>Turn: {state.status.current_turn}</span>
          <span>Total: {state.status.total_turns}</span>
        </div>
      </div>

      {/* Main content */}
      <div style={contentStyle}>
        {/* Turn log */}
        <div style={colStyle}>
          <h2 style={sectionTitle}>Turn Log</h2>
          {recentTurns.length === 0 && (
            <div style={{ color: '#9ca3af', fontSize: 14, textAlign: 'center', padding: 40 }}>
              No turns yet. Submit a task to get started.
            </div>
          )}
          {recentTurns.map((turn, i) => (
            <TurnLog key={i} turn={turn} />
          ))}
        </div>

        {/* Logs */}
        <div style={colStyle}>
          <h2 style={sectionTitle}>Log</h2>
          <div style={logContainerStyle}>
            {state.logs.length === 0 && (
              <div style={{ color: '#9ca3af', fontSize: 13, textAlign: 'center', padding: 20 }}>
                No log entries yet.
              </div>
            )}
            {state.logs.map((log, i) => (
              <div key={i} style={logEntryStyle}>{log}</div>
            ))}
          </div>
        </div>
      </div>

      {/* Approval modal */}
      <ApprovalModal sessionId={state.status.session_id} />
    </div>
  );
}

const headerStyle: React.CSSProperties = {
  padding: '16px 24px',
  borderBottom: '1px solid #e5e7eb',
  backgroundColor: '#fff',
};

const statsStyle: React.CSSProperties = {
  display: 'flex',
  gap: 16,
  fontSize: 12,
  color: '#6b7280',
  marginTop: 8,
};

const contentStyle: React.CSSProperties = {
  display: 'flex',
  gap: 16,
  padding: 16,
  maxWidth: 1400,
  margin: '0 auto',
};

const colStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
};

const sectionTitle: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 600,
  margin: '0 0 12px 0',
};

const logContainerStyle: React.CSSProperties = {
  backgroundColor: '#1f2937',
  color: '#e5e7eb',
  borderRadius: 8,
  padding: 12,
  fontFamily: 'monospace',
  fontSize: 12,
  maxHeight: 'calc(100vh - 200px)',
  overflow: 'auto',
};

const logEntryStyle: React.CSSProperties = {
  padding: '2px 0',
  lineHeight: 1.5,
  wordBreak: 'break-all',
};