import React, { useState } from 'react';
import { Sidebar } from './components/sidebar';
import { Dashboard } from './pages/Dashboard';
import { SonarAnalysis } from './pages/SonarAnalysis';

const App: React.FC = () => {
  const [activePage, setActivePage] = useState<string>('Dashboard');

  const renderPage = () => {
    switch (activePage) {
      case 'Sonar Analysis':
        return <SonarAnalysis />;
      case 'Dashboard':
      default:
        return <Dashboard onNavigate={setActivePage} />;
    }
  };

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', overflow: 'hidden', background: '#eef1f9' }}>
      <Sidebar active={activePage} onNavigate={setActivePage} />
      <main style={{ flex: 1, height: '100vh', overflow: 'hidden' }}>
        {renderPage()}
      </main>
    </div>
  );
};

export default App;