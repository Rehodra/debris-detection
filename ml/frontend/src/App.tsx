import React, { useState } from 'react';
import { Sidebar } from './components/sidebar';
import { Navbar } from './components/Navbar';
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

  if (activePage === 'Dashboard') {
    return (
      <div className="app-container-vertical">
        <Navbar active={activePage} onNavigate={setActivePage} />
        <main className="app-main">
          {renderPage()}
        </main>
      </div>
    );
  }

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