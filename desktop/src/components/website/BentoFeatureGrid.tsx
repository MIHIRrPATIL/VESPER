import React from 'react';

export const BentoFeatureGrid: React.FC = () => {
  return (
    <section id="bento" className="bento-section">
      <div className="section-label-header">
        <span className="section-eyebrow">System Architecture</span>
        <h2 className="section-editorial-title">
          Bespoke engineering for uninterrupted deep work.
        </h2>
      </div>

      <div className="bento-grid-container">
        {/* Card 1: 10-Specialist Cognitive Swarm (Col 8) */}
        <div className="bento-card col-8">
          <div className="bento-header">
            <span className="pill-tag blue">Multi-Agent Swarm</span>
            <h3 className="bento-title">Ten Autonomous Cognitive Specialists</h3>
            <p className="bento-summary">
              Instead of a single monolithic model, VESPER orchestrates dedicated micro-specialists
              coordinated through a proactive action queue and state machine.
            </p>
          </div>

          <div className="swarm-specialists-grid">
            <div className="specialist-mini-box">
              <span className="specialist-mini-name">RESEARCH</span>
              <span className="specialist-mini-role">Academic & Web Synthesis</span>
            </div>
            <div className="specialist-mini-box">
              <span className="specialist-mini-name">ARCHITECTURE</span>
              <span className="specialist-mini-role">Code & Refactor Analysis</span>
            </div>
            <div className="specialist-mini-box">
              <span className="specialist-mini-name">VISION</span>
              <span className="specialist-mini-role">Optical Screen & Canvas OCR</span>
            </div>
            <div className="specialist-mini-box">
              <span className="specialist-mini-name">MEDIA</span>
              <span className="specialist-mini-role">Playback & Volume Control</span>
            </div>
            <div className="specialist-mini-box">
              <span className="specialist-mini-name">TELEPHONY</span>
              <span className="specialist-mini-role">Twilio Call & Audio Relay</span>
            </div>
            <div className="specialist-mini-box">
              <span className="specialist-mini-name">PROACTIVE SENTRY</span>
              <span className="specialist-mini-role">Heap & System Monitoring</span>
            </div>
          </div>
        </div>

        {/* Card 2: Spatial Perception (Col 4) */}
        <div className="bento-card col-4">
          <div className="bento-header">
            <span className="pill-tag amber">Spatial Engine</span>
            <h3 className="bento-title">Touchless Optical Sentry</h3>
            <p className="bento-summary">
              Runs a lightweight MediaPipe worker at 60fps. Executes zero-contact commands
              without ever obscuring your desktop canvas.
            </p>
          </div>

          <div className="gesture-diagram-strip">
            <div className="gesture-point-metric">
              <span className="point-label">TRACKED NODES</span>
              <span className="point-value">21 Landmarks</span>
            </div>
            <div className="gesture-point-metric">
              <span className="point-label">FRAME PIPELINE</span>
              <span className="point-value">16.6ms / frame</span>
            </div>
          </div>
        </div>

        {/* Card 3: Neural Speech & Barge-in (Col 4) */}
        <div className="bento-card col-4">
          <div className="bento-header">
            <span className="pill-tag green">Audio Core</span>
            <h3 className="bento-title">Zero-Latency Barge-In</h3>
            <p className="bento-summary">
              Interruption is natural. Speech synthesizer instantaneously ducks output audio
              when your voice or palm gesture is detected.
            </p>
          </div>

          <div className="gesture-diagram-strip">
            <div className="gesture-point-metric">
              <span className="point-label">WAKE LATENCY</span>
              <span className="point-value">~18ms</span>
            </div>
            <div className="gesture-point-metric">
              <span className="point-label">AUDIO CHANNELS</span>
              <span className="point-value">Dual Ducking</span>
            </div>
          </div>
        </div>

        {/* Card 4: Multi-Node Sync Topology (Col 8) */}
        <div className="bento-card col-8">
          <div className="bento-header">
            <span className="pill-tag rose">Distributed Fabric</span>
            <h3 className="bento-title">Multi-Node Cluster Topology</h3>
            <p className="bento-summary">
              State seamlessly synchronizes across Hub-Central, Desktop-01, and Mobile companion nodes
              over multiplexed WebSocket channels with monotonic sequence numbers.
            </p>
          </div>

          <div className="swarm-specialists-grid">
            <div className="specialist-mini-box">
              <span className="specialist-mini-name">HUB-CENTRAL</span>
              <span className="specialist-mini-role">Primary Coordinator (0.2ms)</span>
            </div>
            <div className="specialist-mini-box">
              <span className="specialist-mini-name">DESKTOP-01</span>
              <span className="specialist-mini-role">High-Density Workstation</span>
            </div>
            <div className="specialist-mini-box">
              <span className="specialist-mini-name">MOBILE CLIENT</span>
              <span className="specialist-mini-role">Ambient Pocket Companion</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
