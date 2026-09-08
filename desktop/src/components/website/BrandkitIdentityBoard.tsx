import React from 'react';

export const BrandkitIdentityBoard: React.FC = () => {
  return (
    <section id="brandkit" className="brandkit-section">
      <div className="section-label-header">
        <span className="section-eyebrow">Identity System & Core Metaphor</span>
        <h2 className="section-editorial-title">
          The evening star: quiet, orienting, and always present.
        </h2>
      </div>

      <div className="brandkit-grid-3col">
        {/* Panel 01: The Symbol */}
        <div className="brandkit-card">
          <div className="brandkit-card-top">
            <span className="brandkit-num">01 / SYMBOL</span>
            <div className="brandkit-visual-glyph">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M4 4L12 20L20 4" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="12" cy="12" r="8" strokeDasharray="3 3" />
              </svg>
            </div>
          </div>
          <div>
            <h3 className="brandkit-title">Orbital Monogram</h3>
            <p className="brandkit-desc">
              The Latin initial intersecting a 28-degree tilted celestial orbit. Represents
              continual peripheral awareness without cognitive disruption.
            </p>
          </div>
        </div>

        {/* Panel 02: Silicon Sovereignty */}
        <div className="brandkit-card">
          <div className="brandkit-card-top">
            <span className="brandkit-num">02 / LOCALITY</span>
            <div className="brandkit-visual-glyph">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="12" cy="12" r="3" />
                <path d="M12 3V6M12 18V21M3 12H6M18 12H21" />
              </svg>
            </div>
          </div>
          <div>
            <h3 className="brandkit-title">Zero-Cloud Egress</h3>
            <p className="brandkit-desc">
              All neural speech synthesis, gesture classification, and semantic vector indexing
              execute on local silicon. Zero conversational telemetry leaves your machine.
            </p>
          </div>
        </div>

        {/* Panel 03: Spatial Fluidity */}
        <div className="brandkit-card">
          <div className="brandkit-card-top">
            <span className="brandkit-num">03 / SPATIALITY</span>
            <div className="brandkit-visual-glyph">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M12 2v20M2 12h20" strokeDasharray="2 2" />
                <circle cx="12" cy="12" r="6" />
                <circle cx="12" cy="12" r="2" />
              </svg>
            </div>
          </div>
          <div>
            <h3 className="brandkit-title">Touchless Perception</h3>
            <p className="brandkit-desc">
              Control music playback, mute microphones, and dismiss interruptions using natural
              physical gestures captured by a dedicated 60fps optical tracking sentry.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};
