import React, { useState } from 'react';
import { AppProvider } from './context';
import Dashboard from './pages/Dashboard';
import Interactive from './pages/Interactive';
import History from './pages/History';

type Tab = 'dashboard' | 'interactive' | 'history';

function App() {
  const [tab, setTab] = useState<Tab>('dashboard');

  return (
    <AppProvider>
      <div style={appStyle}>
        {/* Navigation */}
        <nav style={navStyle}>
          <div style={{ fontWeight: 700, fontSize: 16, color: '#3b82f6' }}>CodingKit</div>
          <div style={{ display: 'flex', gap: 4 }}>
            {(['dashboard', 'interactive', 'history'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                style={tabStyle(tab === t)}
              >
                {t === 'dashboard' ? 'Dashboard' : t === 'interactive' ? 'Interactive' : 'History'}
              </button>
            ))}
          </div>
        </nav>

        {/* Content */}
        <main>
          {tab === 'dashboard' && <Dashboard />}
          {tab === 'interactive' && <Interactive />}
          {tab === 'history' && <History />}
        </main>
      </div>
    </AppProvider>
  );
}

const appStyle: React.CSSProperties = {
  minHeight: '100vh',
  backgroundColor: '#f3f4f6',
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
};

const navStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '8px 24px',
  backgroundColor: '#fff',
  borderBottom: '1px solid #e5e7eb',
};

const tabStyle = (active: boolean): React.CSSProperties => ({
  padding: '6px 16px',
  border: 'none',
  borderRadius: 6,
  backgroundColor: active ? '#3b82f6' : 'transparent',
  color: active ? '#fff' : '#374151',
  fontWeight: active ? 600 : 400,
  cursor: 'pointer',
  fontSize: 14,
  transition: 'all 0.15s',
});

export default App;