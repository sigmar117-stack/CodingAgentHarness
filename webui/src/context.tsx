import React, { createContext, useContext, useReducer, useCallback } from 'react';
import type { WSMessage, StatusResponse, TurnRecordModel } from './api';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

export interface AppState {
  status: StatusResponse;
  turns: TurnRecordModel[];
  logs: string[];
  pendingApproval: {
    name: string;
    arguments: Record<string, unknown>;
    id: string;
  } | null;
  connected: boolean;
}

const initialState: AppState = {
  status: { state: 'idle', session_id: '', current_turn: 0, total_turns: 0, task: '' },
  turns: [],
  logs: [],
  pendingApproval: null,
  connected: false,
};

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

type Action =
  | { type: 'SET_STATUS'; payload: StatusResponse }
  | { type: 'ADD_TURN'; payload: TurnRecordModel }
  | { type: 'ADD_LOG'; payload: string }
  | { type: 'SET_PENDING_APPROVAL'; payload: AppState['pendingApproval'] }
  | { type: 'SET_CONNECTED'; payload: boolean }
  | { type: 'CLEAR_TURNS' };

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_STATUS':
      return { ...state, status: action.payload };
    case 'ADD_TURN':
      return { ...state, turns: [...state.turns, action.payload] };
    case 'ADD_LOG':
      return { ...state, logs: [...state.logs.slice(-199), action.payload] };
    case 'SET_PENDING_APPROVAL':
      return { ...state, pendingApproval: action.payload };
    case 'SET_CONNECTED':
      return { ...state, connected: action.payload };
    case 'CLEAR_TURNS':
      return { ...state, turns: [], logs: [] };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface AppContextType {
  state: AppState;
  dispatch: React.Dispatch<Action>;
  handleWSMessage: (msg: WSMessage) => void;
}

const AppContext = createContext<AppContextType | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const handleWSMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'state_change':
        dispatch({
          type: 'SET_STATUS',
          payload: msg.data as unknown as StatusResponse,
        });
        dispatch({ type: 'ADD_LOG', payload: `State: ${msg.data.state}` });
        if (msg.data.state === 'running' || msg.data.state === 'idle') {
          dispatch({ type: 'CLEAR_TURNS' });
        }
        break;
      case 'turn_complete':
        dispatch({ type: 'ADD_TURN', payload: msg.data as unknown as TurnRecordModel });
        break;
      case 'approval_request':
        dispatch({
          type: 'SET_PENDING_APPROVAL',
          payload: msg.data.action as AppState['pendingApproval'],
        });
        dispatch({ type: 'ADD_LOG', payload: `⚠ Approval needed: ${(msg.data.action as { name: string }).name}` });
        break;
      case 'error':
        dispatch({ type: 'ADD_LOG', payload: `Error: ${msg.data.detail}` });
        break;
      case 'log':
        dispatch({ type: 'ADD_LOG', payload: String(msg.data.message) });
        break;
      case 'pong':
        break;
    }
  }, []);

  return (
    <AppContext.Provider value={{ state, dispatch, handleWSMessage }}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used within AppProvider');
  return ctx;
}