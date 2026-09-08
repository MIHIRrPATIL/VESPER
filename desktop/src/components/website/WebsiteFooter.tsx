import React from 'react';

interface WebsiteFooterProps {
  onLaunchWorkstation: () => void;
}

export const WebsiteFooter: React.FC<WebsiteFooterProps> = ({ onLaunchWorkstation }) => {
  return (
    <footer className="website-footer">
      <div className="website-content-container">
        <div className="footer-top-row">
          <div className="navbar-brand-group" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <div className="brand-monogram-box">
              <span>V</span>
            </div>
            <span className="brand-title-text">VESPER</span>
            <span className="pill-tag green">Local Instrument</span>
          </div>

          <button
            type="button"
            className="hero-primary-btn"
            onClick={onLaunchWorkstation}
          >
            <span>Launch Command Deck</span>
            <kbd className="physical-key">⌘</kbd>
            <kbd className="physical-key">K</kbd>
          </button>
        </div>

        <div className="footer-bottom-row">
          <span>VESPER PROTOCOL · VERSION 2.4.0 · ARCHITECTURAL RELEASE</span>
          <span>ZERO-CLOUD EGRESS · LOCAL SILICON AGENT</span>
        </div>
      </div>
    </footer>
  );
};
