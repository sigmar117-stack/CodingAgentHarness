import React from 'react';
import type { TurnRecordModel } from '../api';

interface Props {
  turn: TurnRecordModel;
}

export default function TurnLog({ turn }: Props) {
  return (
    <div style={cardStyle}>
      <div style={headerStyle}>
        <strong>Turn #{turn.turn_number}</strong>
        {turn.approval_decision && (
          <span style={badgeStyle(turn.approval_decision === 'approved' ? '#10b981' : '#ef4444')}>
            {turn.approval_decision}
          </span>
        )}
        {turn.classification && (
          <span style={badgeStyle('#8b5cf6')}>{turn.classification}</span>
        )}
        {turn.guardrail_result?.is_dangerous && (
          <span style={badgeStyle('#f59e0b')}>Dangerous</span>
        )}
      </div>

      {turn.llm_response && (
        <div style={sectionStyle}>
          <div style={labelStyle}>LLM Response:</div>
          <pre style={preStyle}>{turn.llm_response}</pre>
        </div>
      )}

      {turn.tool_calls.length > 0 && (
        <div style={sectionStyle}>
          <div style={labelStyle}>Tool Calls:</div>
          {turn.tool_calls.map((tc, i) => (
            <div key={i} style={toolCallStyle}>
              <code>{tc.name}</code>
              <pre style={argStyle}>{JSON.stringify(tc.arguments, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}

      {turn.tool_results.length > 0 && (
        <div style={sectionStyle}>
          <div style={labelStyle}>Results:</div>
          {turn.tool_results.map((tr, i) => (
            <div key={i} style={resultStyle(tr.success)}>
              <span>{tr.success ? '✅' : '❌'} {tr.output?.slice(0, 200)}{tr.output?.length > 200 ? '...' : ''}</span>
              {tr.error && <div style={{ color: '#ef4444', fontSize: 12 }}>{tr.error}</div>}
            </div>
          ))}
        </div>
      )}

      {turn.guardrail_result?.is_dangerous && (
        <div style={sectionStyle}>
          <div style={labelStyle}>Guardrail:</div>
          <span style={{ color: '#f59e0b', fontSize: 12 }}>{turn.guardrail_result.risk_reason}</span>
        </div>
      )}

      {turn.timestamp && (
        <div style={tsStyle}>{new Date(turn.timestamp).toLocaleTimeString()}</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const cardStyle: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  borderRadius: 8,
  padding: 12,
  marginBottom: 8,
  backgroundColor: '#f9fafb',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  marginBottom: 8,
};

const badgeStyle = (color: string): React.CSSProperties => ({
  fontSize: 11,
  fontWeight: 600,
  padding: '2px 8px',
  borderRadius: 10,
  color: '#fff',
  backgroundColor: color,
});

const sectionStyle: React.CSSProperties = {
  marginTop: 8,
};

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: '#6b7280',
  textTransform: 'uppercase',
  marginBottom: 4,
};

const preStyle: React.CSSProperties = {
  fontSize: 12,
  backgroundColor: '#f3f4f6',
  padding: 8,
  borderRadius: 4,
  overflow: 'auto',
  maxHeight: 120,
  margin: 0,
};

const toolCallStyle: React.CSSProperties = {
  marginBottom: 4,
};

const argStyle: React.CSSProperties = {
  fontSize: 11,
  backgroundColor: '#f3f4f6',
  padding: 4,
  borderRadius: 4,
  margin: '2px 0 0 0',
  overflow: 'auto',
  maxHeight: 80,
};

const resultStyle = (success: boolean): React.CSSProperties => ({
  fontSize: 12,
  padding: '2px 4px',
  color: success ? '#059669' : '#dc2626',
});

const tsStyle: React.CSSProperties = {
  fontSize: 10,
  color: '#9ca3af',
  textAlign: 'right',
  marginTop: 4,
};