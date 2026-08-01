import React, { useEffect, useState } from 'react';
import { api, SessionSummary, SessionDetail } from '../api';

export default function History() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selected, setSelected] = useState<SessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSessions = async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.listSessions();
      setSessions(list);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSessions();
  }, []);

  const handleSelect = async (id: string) => {
    try {
      const detail = await api.getSession(id);
      setSelected(detail);
    } catch (err) {
      setError(String(err));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.session_id !== id));
      if (selected?.session_id === id) setSelected(null);
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div style={containerStyle}>
      <h1 style={{ margin: 0, marginBottom: 16 }}>History</h1>

      {error && (
        <div style={errorStyle}>
          Error: {error}
          <button onClick={() => setError(null)} style={{ marginLeft: 12, cursor: 'pointer' }}>Dismiss</button>
        </div>
      )}

      <div style={layoutStyle}>
        {/* Session list */}
        <div style={listStyle}>
          <div style={listHeaderStyle}>
            <h2 style={{ margin: 0, fontSize: 16 }}>Sessions</h2>
            <button onClick={loadSessions} style={refreshBtnStyle} disabled={loading}>
              {loading ? '...' : '↻'}
            </button>
          </div>

          {loading && <div style={{ padding: 20, textAlign: 'center', color: '#9ca3af' }}>Loading...</div>}

          {!loading && sessions.length === 0 && (
            <div style={{ padding: 20, textAlign: 'center', color: '#9ca3af' }}>
              No sessions found.
            </div>
          )}

          {sessions.map((s) => (
            <div
              key={s.session_id}
              onClick={() => handleSelect(s.session_id)}
              style={sessionCardStyle(selected?.session_id === s.session_id)}
            >
              <div style={{ fontWeight: 600, fontSize: 13 }}>{s.task_description || 'Untitled'}</div>
              <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                <span style={statusDotStyle(s.status)} />
                {s.status} — {new Date(s.created_at).toLocaleString()} — {s.total_turns} turns
              </div>
            </div>
          ))}
        </div>

        {/* Session detail */}
        <div style={detailStyle}>
          {selected ? (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2 style={{ margin: 0, fontSize: 16 }}>Session Detail</h2>
                <button onClick={() => handleDelete(selected.session_id)} style={deleteBtnStyle}>
                  Delete
                </button>
              </div>
              <div style={metaStyle}>
                <div><strong>ID:</strong> <code>{selected.session_id}</code></div>
                <div><strong>Status:</strong> {selected.status}</div>
                <div><strong>Created:</strong> {new Date(selected.created_at).toLocaleString()}</div>
                <div><strong>Turns:</strong> {selected.total_turns}</div>
                <div><strong>Tool calls:</strong> {selected.total_tool_calls}</div>
                {selected.summary && <div><strong>Summary:</strong> {selected.summary}</div>}
              </div>

              {selected.turns.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <h3 style={{ fontSize: 14, margin: '0 0 8px 0' }}>Turns</h3>
                  {selected.turns.map((turn, i) => (
                    <div key={i} style={turnCardStyle}>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>Turn #{turn.turn_number}</div>
                      {turn.llm_response && (
                        <pre style={preStyle}>{turn.llm_response}</pre>
                      )}
                      {turn.tool_calls.length > 0 && (
                        <div style={{ fontSize: 12, marginTop: 4 }}>
                          Tools: {turn.tool_calls.map((t) => t.name).join(', ')}
                        </div>
                      )}
                      {turn.approval_decision && (
                        <div style={{ fontSize: 12, color: '#f59e0b', marginTop: 2 }}>
                          Approval: {turn.approval_decision}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: '#9ca3af', textAlign: 'center', padding: 40 }}>
              Select a session to view details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const containerStyle: React.CSSProperties = {
  padding: 24,
  maxWidth: 1200,
  margin: '0 auto',
};

const errorStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  color: '#dc2626',
  padding: '8px 12px',
  borderRadius: 6,
  marginBottom: 12,
  fontSize: 13,
};

const layoutStyle: React.CSSProperties = {
  display: 'flex',
  gap: 16,
  height: 'calc(100vh - 140px)',
};

const listStyle: React.CSSProperties = {
  width: 350,
  flexShrink: 0,
  overflow: 'auto',
  backgroundColor: '#fff',
  borderRadius: 8,
  border: '1px solid #e5e7eb',
};

const listHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '12px 16px',
  borderBottom: '1px solid #e5e7eb',
};

const refreshBtnStyle: React.CSSProperties = {
  background: 'none',
  border: '1px solid #d1d5db',
  borderRadius: 4,
  cursor: 'pointer',
  fontSize: 16,
  padding: '2px 8px',
};

const sessionCardStyle = (selected: boolean): React.CSSProperties => ({
  padding: '10px 16px',
  borderBottom: '1px solid #f3f4f6',
  cursor: 'pointer',
  backgroundColor: selected ? '#eff6ff' : '#fff',
  transition: 'background-color 0.1s',
});

const statusDotStyle = (status: string): React.CSSProperties => ({
  display: 'inline-block',
  width: 8,
  height: 8,
  borderRadius: '50%',
  backgroundColor: status === 'completed' ? '#10b981' : status === 'cancelled' ? '#ef4444' : '#6b7280',
  marginRight: 4,
});

const detailStyle: React.CSSProperties = {
  flex: 1,
  overflow: 'auto',
  backgroundColor: '#fff',
  borderRadius: 8,
  border: '1px solid #e5e7eb',
  padding: 16,
};

const metaStyle: React.CSSProperties = {
  marginTop: 12,
  fontSize: 13,
  lineHeight: 1.8,
};

const turnCardStyle: React.CSSProperties = {
  border: '1px solid #f3f4f6',
  borderRadius: 6,
  padding: 10,
  marginBottom: 8,
  backgroundColor: '#fafafa',
};

const preStyle: React.CSSProperties = {
  fontSize: 12,
  backgroundColor: '#f3f4f6',
  padding: 6,
  borderRadius: 4,
  margin: '4px 0 0 0',
  overflow: 'auto',
  maxHeight: 100,
};

const deleteBtnStyle: React.CSSProperties = {
  background: 'none',
  border: '1px solid #ef4444',
  color: '#ef4444',
  borderRadius: 4,
  padding: '4px 12px',
  cursor: 'pointer',
  fontSize: 12,
  fontWeight: 600,
};