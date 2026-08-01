import React, { useState } from 'react';
import { api } from '../api';
import { useAppContext } from '../context';

interface Props {
  sessionId: string;
}

export default function ApprovalModal({ sessionId }: Props) {
  const { state, dispatch } = useAppContext();
  const [modifiedInput, setModifiedInput] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (!state.pendingApproval) return null;

  const action = state.pendingApproval;

  const handleDecision = async (decision: string) => {
    setSubmitting(true);
    try {
      const params = decision === 'modified' && modifiedInput
        ? { command: modifiedInput }
        : undefined;
      await api.approve(sessionId, decision, params);
      dispatch({ type: 'SET_PENDING_APPROVAL', payload: null });
      dispatch({ type: 'ADD_LOG', payload: `Approval: ${decision}` });
      setModifiedInput('');
    } catch (err) {
      dispatch({ type: 'ADD_LOG', payload: `Approval error: ${err}` });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        <h3 style={{ margin: 0, marginBottom: 8 }}>⚠ Dangerous Action</h3>
        <div style={{ marginBottom: 12 }}>
          <strong>Tool:</strong> {action.name}
        </div>
        <pre style={argPreStyle}>{JSON.stringify(action.arguments, null, 2)}</pre>

        {state.pendingApproval?.name === 'execute_command' && (
          <div style={{ marginTop: 8 }}>
            <label style={{ fontSize: 12, fontWeight: 600 }}>Modified command:</label>
            <input
              type="text"
              value={modifiedInput}
              onChange={(e) => setModifiedInput(e.target.value)}
              placeholder="Enter modified command..."
              style={inputStyle}
            />
          </div>
        )}

        <div style={btnGroupStyle}>
          <button
            onClick={() => handleDecision('approved')}
            disabled={submitting}
            style={{ ...btnStyle, backgroundColor: '#10b981' }}
          >
            ✅ Approve
          </button>
          <button
            onClick={() => handleDecision('rejected')}
            disabled={submitting}
            style={{ ...btnStyle, backgroundColor: '#ef4444' }}
          >
            ❌ Reject
          </button>
          <button
            onClick={() => handleDecision('modified')}
            disabled={submitting || !modifiedInput}
            style={{ ...btnStyle, backgroundColor: '#f59e0b' }}
          >
            ✏ Modify
          </button>
        </div>
      </div>
    </div>
  );
}

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0, left: 0, right: 0, bottom: 0,
  backgroundColor: 'rgba(0,0,0,0.5)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
};

const modalStyle: React.CSSProperties = {
  backgroundColor: '#fff',
  borderRadius: 12,
  padding: 24,
  maxWidth: 500,
  width: '90%',
  boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
};

const argPreStyle: React.CSSProperties = {
  fontSize: 12,
  backgroundColor: '#f3f4f6',
  padding: 8,
  borderRadius: 4,
  overflow: 'auto',
  maxHeight: 200,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '6px 8px',
  fontSize: 13,
  border: '1px solid #d1d5db',
  borderRadius: 4,
  marginTop: 4,
};

const btnGroupStyle: React.CSSProperties = {
  display: 'flex',
  gap: 8,
  marginTop: 16,
};

const btnStyle: React.CSSProperties = {
  flex: 1,
  padding: '8px 12px',
  border: 'none',
  borderRadius: 6,
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  fontSize: 13,
};