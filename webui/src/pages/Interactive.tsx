import React, { useState } from 'react';
import { useAppContext } from '../context';
import { api } from '../api';
import StatusBadge from '../components/StatusBadge';

export default function Interactive() {
  const { state, dispatch } = useAppContext();
  const [task, setTask] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!task.trim()) return;
    setSubmitting(true);
    try {
      const res = await api.runTask(task);
      dispatch({ type: 'ADD_LOG', payload: `Task submitted: ${task.slice(0, 100)}` });
      dispatch({ type: 'ADD_LOG', payload: `Session: ${res.session_id}` });
      setTask('');
    } catch (err) {
      dispatch({ type: 'ADD_LOG', payload: `Error: ${err}` });
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async () => {
    try {
      await api.cancelTask();
      dispatch({ type: 'ADD_LOG', payload: 'Task cancelled' });
    } catch (err) {
      dispatch({ type: 'ADD_LOG', payload: `Cancel error: ${err}` });
    }
  };

  const isRunning = state.status.state === 'running';

  return (
    <div style={containerStyle}>
      <h1 style={{ margin: 0, marginBottom: 8 }}>Interactive</h1>
      <div style={{ marginBottom: 16 }}>
        <StatusBadge state={state.status.state} />
      </div>

      {/* Task input */}
      <div style={inputAreaStyle}>
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Enter a task description..."
          disabled={isRunning}
          rows={4}
          style={textareaStyle}
        />
        <div style={btnRowStyle}>
          <button
            onClick={handleSubmit}
            disabled={isRunning || !task.trim() || submitting}
            style={primaryBtnStyle}
          >
            {submitting ? 'Starting...' : '▶ Run Task'}
          </button>
          <button
            onClick={handleCancel}
            disabled={!isRunning}
            style={dangerBtnStyle}
          >
            ⏹ Cancel
          </button>
        </div>
      </div>

      {/* Status info */}
      {state.status.state !== 'idle' && (
        <div style={infoCardStyle}>
          <h3 style={{ margin: 0, marginBottom: 8, fontSize: 14 }}>Current Task</h3>
          <div style={{ fontSize: 13, color: '#374151' }}>{state.status.task}</div>
          <div style={infoRowStyle}>
            <span>Session: <code>{state.status.session_id?.slice(0, 12)}</code></span>
            <span>Turn: {state.status.current_turn}</span>
          </div>
        </div>
      )}

      {/* Log */}
      <div style={logStyle}>
        <h3 style={{ margin: '0 0 8px 0', fontSize: 14 }}>Log</h3>
        {state.logs.length === 0 && (
          <div style={{ color: '#9ca3af', fontSize: 12 }}>No log entries yet.</div>
        )}
        {state.logs.slice(-20).map((log, i) => (
          <div key={i} style={{ fontSize: 12, padding: '1px 0', wordBreak: 'break-all' }}>{log}</div>
        ))}
      </div>
    </div>
  );
}

const containerStyle: React.CSSProperties = {
  padding: 24,
  maxWidth: 700,
  margin: '0 auto',
};

const inputAreaStyle: React.CSSProperties = {
  backgroundColor: '#fff',
  border: '1px solid #e5e7eb',
  borderRadius: 8,
  padding: 16,
  marginBottom: 16,
};

const textareaStyle: React.CSSProperties = {
  width: '100%',
  resize: 'vertical',
  padding: 8,
  fontSize: 14,
  border: '1px solid #d1d5db',
  borderRadius: 4,
  fontFamily: 'inherit',
};

const btnRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 8,
  marginTop: 12,
};

const primaryBtnStyle: React.CSSProperties = {
  padding: '8px 20px',
  backgroundColor: '#3b82f6',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  fontWeight: 600,
  cursor: 'pointer',
  fontSize: 14,
};

const dangerBtnStyle: React.CSSProperties = {
  padding: '8px 20px',
  backgroundColor: '#ef4444',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  fontWeight: 600,
  cursor: 'pointer',
  fontSize: 14,
};

const infoCardStyle: React.CSSProperties = {
  backgroundColor: '#fff',
  border: '1px solid #e5e7eb',
  borderRadius: 8,
  padding: 16,
  marginBottom: 16,
};

const infoRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 16,
  fontSize: 12,
  color: '#6b7280',
  marginTop: 8,
};

const logStyle: React.CSSProperties = {
  backgroundColor: '#1f2937',
  color: '#e5e7eb',
  borderRadius: 8,
  padding: 12,
  fontFamily: 'monospace',
  maxHeight: 300,
  overflow: 'auto',
};