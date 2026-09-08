import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';

const GREETINGS = {
  morning: [
    "Good morning, Commander.",
    "System online. Ready for the day?",
    "Initialising morning protocols.",
    "The grid is awake.",
    "Dawn breaks across the network.",
    "Morning diagnostics cleared. Standing by.",
    "All threads synchronized and operational.",
    "Fresh day, fresh architecture.",
    "Sensors calibrated. Ready when you are.",
    "Neural channels primed for the morning run.",
    "Daylight detected. Telemetry nominal.",
    "A new cycle begins. What shall we engineer?",
    "Core buffers purged and ready for throughput.",
    "Morning sync complete. All nodes active.",
    "System load minimal. Optimal time to build.",
    "Sunrise protocol engaged. Systems at peak state.",
    "Local workspace mapped and indexed.",
    "Awake and listening on all frequencies.",
    "Morning briefing ready. Awaiting directive.",
    "The workstation is charged and responsive.",
    "Ready to turn chaos into clean architecture.",
    "Clean desk, clean mind, clean commit tree.",
    "Perception pipelines operational. Good morning.",
    "Subsystems initialized. Standing watch.",
    "Early bird execution window open."
  ],
  afternoon: [
    "Good afternoon. Status nominal.",
    "Mid-day systems check complete.",
    "Continuing operations.",
    "All telemetry optimal.",
    "High noon in the machine.",
    "Peak execution window active.",
    "Throughput steady. No thermal throttling.",
    "Deep work mode available. Focus engaged.",
    "Afternoon momentum: maintaining trajectory.",
    "Memory footprint stable. Ready for your next move.",
    "The grid hums at nominal frequency.",
    "Context window clean. What are we targeting?",
    "Subsystems synchronized. Ready for heavy compute.",
    "Good afternoon. Task backlog monitored and prioritized.",
    "Mid-day check: all background jobs healthy.",
    "Halfway through the cycle. Standing by.",
    "Steady progress on the wire.",
    "All cluster metrics operating within tolerance.",
    "Execution buffers clear. Feed me a directive.",
    "Focus window open. Ready to accelerate.",
    "Mid-day silence on the wire. Ideal for deep work.",
    "Pipelining tasks. Awaiting your lead.",
    "State intact. Workspace standing by.",
    "Afternoon compute resources at maximum availability.",
    "Telemetry stream unwavering. Ready to deploy."
  ],
  evening: [
    "Good evening. Telemetry looks stable.",
    "Winding down operations.",
    "Evening protocols engaged.",
    "The grid stabilizes for the night.",
    "Twilight descending. Switching to ambient profile.",
    "Evening cycle initiated. Ready for final passes.",
    "Dusk on the horizon. Still standing by.",
    "Reviewing day telemetry. Systems performed well.",
    "Good evening. Cleaning up lingering background jobs.",
    "The noise fades. Pure signal remains.",
    "Ambient telemetry active. Awaiting evening tasks.",
    "Approaching day's end. Commits looking solid.",
    "Evening calm across all monitored services.",
    "Ready to wrap up loose threads.",
    "Twilight brings clarity to the architecture.",
    "Night mode ready on demand. How are we looking?",
    "Day checkout in progress. Core daemons steady.",
    "Good evening. Ready for your closing thoughts.",
    "System metrics settling into evening cruise.",
    "The wire quiets down. Focus sharpens.",
    "Evening diagnostics passed without exception.",
    "Transitioning to night telemetry.",
    "Another solid cycle in the books.",
    "Still listening, still keeping watch.",
    "Sun down, systems steady. Standing by."
  ],
  night: [
    "Late night hacking?",
    "The grid is quiet. What's next?",
    "Midnight operations authorized.",
    "Silence on the wire.",
    "The world is asleep; the compiler is awake.",
    "Dark mode is not just a theme; it is a discipline.",
    "Past midnight. The purest ideas come alive now.",
    "Low latency, zero interruptions. Prime hacking hours.",
    "The quiet hours belong to the builders.",
    "Night owls build the future.",
    "All external traffic silenced. Just you and the code.",
    "Midnight diagnostics nominal. Standing vigil.",
    "Dead of night. Ghost in the shell.",
    "Whisper protocols active. Minimal logging.",
    "No meetings. No pings. Just raw creation.",
    "Late night session recognized. Watching your back.",
    "The network rests, but VESPER stays alert.",
    "Burning the midnight oil. Systems standing by.",
    "Quiet contemplation, sharp execution.",
    "Moonlight filtered through the screen. Ready.",
    "Zero noise floor. Time to solve the hard problems.",
    "The clock strikes late, but the thoughts run fast.",
    "Midnight telemetry locked. All lights low.",
    "Still here. Still monitoring. What are we solving?",
    "Deep night operations underway. Full compute allocated."
  ]
};

const getGreeting = () => {
  const hour = new Date().getHours();
  let timeOfDay: keyof typeof GREETINGS = 'morning';
  
  if (hour >= 12 && hour < 17) timeOfDay = 'afternoon';
  else if (hour >= 17 && hour < 22) timeOfDay = 'evening';
  else if (hour >= 22 || hour < 5) timeOfDay = 'night';
  
  const options = GREETINGS[timeOfDay];
  return options[Math.floor(Math.random() * options.length)];
};

export const DynamicGreeting: React.FC = () => {
  const [greeting, setGreeting] = useState('');

  useEffect(() => {
    setGreeting(getGreeting());
  }, []);

  if (!greeting) return null;

  // Split greeting into words for a staggered particle-like reveal
  const words = greeting.split(' ');

  return (
    <div className="dynamic-greeting-container">
      <div className="greeting-words-row">
        {words.map((word, i) => (
          <motion.span
            key={i}
            className="greeting-word"
            initial={{ opacity: 0, filter: 'blur(12px)', y: 20, scale: 0.9 }}
            animate={{ opacity: 1, filter: 'blur(0px)', y: 0, scale: 1 }}
            transition={{
              duration: 1.2,
              ease: [0.16, 1, 0.3, 1],
              delay: i * 0.12,
            }}
          >
            {word}&nbsp;
          </motion.span>
        ))}
      </div>
    </div>
  );
};
