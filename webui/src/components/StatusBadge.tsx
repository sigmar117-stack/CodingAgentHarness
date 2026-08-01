import React from 'react';

const colors: Record<string, string> = {
  idle: '#6b7280',
  running: '#3b82f6',
  paused: '#f59e0b',
  completed: '#10b981',
  cancelled: '#ef4444',
  error: '#ef4444',
};

interface Props {
  state: string;
}

export default function StatusBadge({ state }: Props) {
  const color = colors[state] || '#6b7280';
  const label = state.charAt(0).toUpperCase() + state.slice(1);

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 12px',
        borderRadius: 20,
        fontSize: 13,
        fontWeight: 600,
        color: '#fff',
        backgroundColor: color,
      }}
    >
      <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#fff', opacity: state === 'running' ? 0.8 : 0.5 }} />
      {label}
    </span>
  );
}