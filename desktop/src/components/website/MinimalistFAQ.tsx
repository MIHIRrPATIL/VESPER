import React, { useState } from 'react';

interface FAQItem {
  question: string;
  answer: string;
}

const FAQ_ITEMS: FAQItem[] = [
  {
    question: 'How does VESPER preserve conversational privacy?',
    answer:
      'VESPER operates as a local-first companion. All real-time sensory data—including webcam frames for gesture classification, microphone audio streams, and window perception—are processed entirely on your local machine. No voice recordings or visual frames are transmitted to external servers.',
  },
  {
    question: 'Can the optical gestures trigger accidentally while typing?',
    answer:
      'VESPER employs an adaptive confidence threshold coupled with a physical or software Safety Lock. In addition, gestures must sustain stability across consecutive video frames to register, eliminating false triggers from regular keyboard usage.',
  },
  {
    question: 'How does the ten-specialist cognitive swarm coordinate tasks?',
    answer:
      'Incoming prompts pass through a lightweight 3-tier semantic router. High-level planning decomposes tasks into sub-intents (such as code inspection, media playback, or academic research), which are dispatched concurrently to isolated micro-specialists before synthesis.',
  },
  {
    question: 'Can I toggle directly between the website and the live workstation deck?',
    answer:
      'Yes. Pressing ⌘K or clicking Launch Workstation at any time instantly opens the full-screen two-tone Command Deck workstation, maintaining uninterrupted WebSocket and camera connections.',
  },
];

export const MinimalistFAQ: React.FC = () => {
  const [openIdx, setOpenIdx] = useState<number | null>(0);

  const toggleItem = (idx: number) => {
    setOpenIdx(openIdx === idx ? null : idx);
  };

  return (
    <section id="faq" className="faq-section">
      <div className="section-label-header">
        <span className="section-eyebrow">Documentation & Protocols</span>
        <h2 className="section-editorial-title">
          Frequently asked questions.
        </h2>
      </div>

      <div className="faq-list">
        {FAQ_ITEMS.map((item, idx) => {
          const isOpen = openIdx === idx;
          return (
            <div key={idx} className="faq-item">
              <button
                type="button"
                className="faq-trigger"
                onClick={() => toggleItem(idx)}
                aria-expanded={isOpen}
              >
                <span>{item.question}</span>
                <span className="faq-icon-glyph">{isOpen ? '−' : '+'}</span>
              </button>
              {isOpen && <div className="faq-answer">{item.answer}</div>}
            </div>
          );
        })}
      </div>
    </section>
  );
};
