import React from 'react';
import { LandingNavbar } from '../components/LandingNavbar';
import { LandingHero } from '../components/LandingHero';
import { HowItWorks } from '../components/HowItWorks';
import { AccidentSection } from '../components/AccidentSection';
import { LandingFooter } from '../components/LandingFooter';

interface LandingPageProps {
  onEnterApp?: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onEnterApp }) => {
  return (
    <div>
      <LandingNavbar onEnterApp={onEnterApp} />
      <LandingHero onEnterApp={onEnterApp} />
      <HowItWorks />
      <AccidentSection />
      <LandingFooter />
    </div>
  );
};

export default LandingPage;