import React from 'react';
import { WebsiteNavbar } from './WebsiteNavbar';
import { WebsiteHero } from './WebsiteHero';
import { BrandkitIdentityBoard } from './BrandkitIdentityBoard';
import { BentoFeatureGrid } from './BentoFeatureGrid';
import { TechnicalSpecsTable } from './TechnicalSpecsTable';
import { MinimalistFAQ } from './MinimalistFAQ';
import { WebsiteFooter } from './WebsiteFooter';
import '../../styles/minimalist-website.css';

interface VesperWebsiteProps {
  onLaunchWorkstation: () => void;
}

export const VesperWebsite: React.FC<VesperWebsiteProps> = ({ onLaunchWorkstation }) => {
  return (
    <div className="vesper-website-root">
      {/* Editorial Sticky Navigation Bar */}
      <WebsiteNavbar onLaunchWorkstation={onLaunchWorkstation} />

      {/* Main Content Spine */}
      <main className="website-content-container">
        {/* Section 1: Hero with Faux-OS Window Chrome */}
        <WebsiteHero onLaunchWorkstation={onLaunchWorkstation} />

        {/* Section 2: Brandkit Identity & Core Metaphor Board */}
        <BrandkitIdentityBoard />

        {/* Section 3: Bento Feature Grid */}
        <BentoFeatureGrid />

        {/* Section 4: Technical Benchmarks Table */}
        <TechnicalSpecsTable />

        {/* Section 5: Minimalist Documentation FAQ */}
        <MinimalistFAQ />
      </main>

      {/* Section 6: Editorial Footer */}
      <WebsiteFooter onLaunchWorkstation={onLaunchWorkstation} />
    </div>
  );
};
