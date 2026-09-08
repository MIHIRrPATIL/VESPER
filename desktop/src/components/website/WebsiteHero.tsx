import React from 'react';

const ProceduralAvatar: React.FC<{ state: string; latencyMs?: number }> = () => (
  <div className="agent-core-visual">
    <div className="agent-core-outer-ring" />
    <div className="agent-core-middle-ring" />
    <div className="agent-core-orb" />
  </div>
);

interface WebsiteHeroProps {
  onLaunchWorkstation: () => void;
}

export const WebsiteHero: React.FC<WebsiteHeroProps> = ({ onLaunchWorkstation }) => {
  return (
    <section id="overview" className="website-hero-section">
      {/* Category Tag */}
      <div className="hero-tag-row">
        <span className="pill-tag blue">Local-First Ambient Intelligence</span>
      </div>

      {/* Editorial Serif Hero Title */}
      <h1 className="hero-editorial-heading">
        A silent, touchless intelligence for your physical desk.
      </h1>

      {/* Editorial Subtext */}
      <p className="hero-editorial-subtext">
        VESPER coordinates ten autonomous subagent specialists, 21-landmark optical
        gesture perception, and zero-latency local speech synthesis into a singular, calm instrument.
      </p>

      {/* Hero Actions */}
      <div className="hero-action-buttons">
        <button
          type="button"
          className="hero-primary-btn"
          onClick={onLaunchWorkstation}
        >
          <span>Open Live Deck</span>
          <kbd className="physical-key">⌘</kbd>
          <kbd className="physical-key">K</kbd>
        </button>

        <a href="#specs" className="hero-secondary-btn">
          Explore Architecture & Specs
        </a>
      </div>

      {/* Faux-OS Window Chrome Preview */}
      <div className="faux-os-window-shell">
        <div className="faux-os-top-bar">
          <div className="window-controls-dots">
            <span className="window-dot" />
            <span className="window-dot" />
            <span className="window-dot" />
          </div>
          <span className="window-title-tag">vesper-desktop-01 · 2451×1293 · host:local</span>
          <span className="window-status-chip">ARMED · 18ms</span>
        </div>

        <div className="faux-os-window-body">
          <div className="preview-avatar-host">
            <ProceduralAvatar state="IDLE" latencyMs={18} />
          </div>

          <div className="preview-headline">
            "What can I help you shape today?"
          </div>

          {/* Dynamic Audio Visualizer Bar Preview */}
          <div className="audio-waveform-deck state-listening">
            {Array.from({ length: 18 }).map((_, i) => (
              <span
                key={i}
                className="waveform-bar"
                style={{ animationDelay: `${(i * 0.06).toFixed(2)}s` }}
              />
            ))}
          </div>

          <div className="preview-controls-row">
            <span className="preview-chip">Touchless Sentry Active</span>
            <span className="preview-chip">10 Specialists Synchronized</span>
            <span className="preview-chip">Zero Cloud Egress</span>
          </div>
        </div>
      </div>
    </section>
  );
};
