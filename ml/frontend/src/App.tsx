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
    <div className="app-container">
      <Sidebar active={activePage} onNavigate={setActivePage} />
      <main className="app-main">
        {renderPage()}
      </main>
    </div>
  );
};

export default App;