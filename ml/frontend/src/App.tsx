import React, { useState } from 'react';
import { LandingPage } from './pages/LandingPage';
import { SonarAnalysis } from './pages/SonarAnalysis';

const App: React.FC = () => {
  const [activePage, setActivePage] = useState<string>('Landing');

  if (activePage === 'Landing') {
    return <LandingPage onEnterApp={() => setActivePage('Dashboard')} />;
  }

  return (
    <SonarAnalysis />
  );
};

export default App;