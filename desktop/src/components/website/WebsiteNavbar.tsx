import React from 'react';

interface WebsiteNavbarProps {
  onLaunchWorkstation: () => void;
}

export const WebsiteNavbar: React.FC<WebsiteNavbarProps> = ({ onLaunchWorkstation }) => {
  return (
    <header className="website-navbar">
      <div className="navbar-inner">
        {/* Brand Monogram & Title */}
        <div className="navbar-brand-group" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
          <div className="brand-monogram-box">
            <span>V</span>
          </div>
          <span className="brand-title-text">VESPER</span>
          <span className="pill-tag green">Core v2.4 Active</span>
        </div>

        {/* Editorial Nav Links */}
        <nav className="navbar-links">
          <a href="#overview" className="nav-link-item">Overview</a>
          <a href="#brandkit" className="nav-link-item">Identity</a>
          <a href="#bento" className="nav-link-item">Architecture</a>
          <a href="#specs" className="nav-link-item">Benchmarks</a>
          <a href="#faq" className="nav-link-item">Documentation</a>
        </nav>

        {/* Primary Action Button */}
        <div className="navbar-actions">
          <button
            type="button"
            className="launch-deck-btn"
            onClick={onLaunchWorkstation}
            title="Launch Workstation Companion Deck (⌘K)"
          >
            <span>Launch Workstation</span>
            <kbd className="physical-key">⌘</kbd>
            <kbd className="physical-key">K</kbd>
          </button>
        </div>
      </div>
    </header>
  );
};
