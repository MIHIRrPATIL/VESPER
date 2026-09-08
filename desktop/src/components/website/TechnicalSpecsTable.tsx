import React from 'react';

export const TechnicalSpecsTable: React.FC = () => {
  return (
    <section id="specs" className="specs-section">
      <div className="section-label-header">
        <span className="section-eyebrow">Technical Benchmarks</span>
        <h2 className="section-editorial-title">
          Deterministic latency and minimal resource overhead.
        </h2>
      </div>

      <div className="specs-document-card">
        <table className="specs-table">
          <thead>
            <tr>
              <th>SUBSYSTEM</th>
              <th>METRIC / ARCHITECTURE</th>
              <th>BENCHMARK</th>
              <th>NOTES</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="spec-category">Gateway Event Loop</td>
              <td>Asyncio WebSocket multiplexer</td>
              <td className="spec-benchmark">18ms loopback</td>
              <td>Zero external cloud hops for IPC</td>
            </tr>
            <tr>
              <td className="spec-category">Optical Gesture Sentry</td>
              <td>MediaPipe 21-point hand pipeline</td>
              <td className="spec-benchmark">16.6ms (60 FPS)</td>
              <td>Isolated web worker thread</td>
            </tr>
            <tr>
              <td className="spec-category">Speech Synthesizer</td>
              <td>Edge neural voice + Ducking engine</td>
              <td className="spec-benchmark">&lt; 250ms TTFB</td>
              <td>Instantaneous interrupt on barge-in</td>
            </tr>
            <tr>
              <td className="spec-category">Cognitive Swarm</td>
              <td>10 Micro-specialist architecture</td>
              <td className="spec-benchmark">10 concurrent</td>
              <td>Adaptive prompt steering via semantic router</td>
            </tr>
            <tr>
              <td className="spec-category">Memory Footprint</td>
              <td>Rust / Tauri runtime shell</td>
              <td className="spec-benchmark">&lt; 180MB RSS</td>
              <td>Hardware-accelerated 2D canvas avatar</td>
            </tr>
            <tr>
              <td className="spec-category">Persistence Engine</td>
              <td>Local SQLite vector store + WAL</td>
              <td className="spec-benchmark">0.8ms query</td>
              <td>Encrypted conversation & symbol index</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
};
