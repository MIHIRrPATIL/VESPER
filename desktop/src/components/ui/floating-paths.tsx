"use client";

import React from "react";
import { motion } from "motion/react";

export function FloatingPathsBackground({
  position,
  children,
  className,
  style,
}: {
  position: number;
  className?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}) {
  const paths = Array.from({ length:8 }, (_, i) => ({
    id: i,
    d: `M-${380 - i * 10 * position} -${189 + i * 12}C-${
      380 - i * 10 * position
    } -${189 + i * 12} -${312 - i * 10 * position} ${216 - i * 12} ${
      152 - i * 10 * position
    } ${343 - i * 12}C${616 - i * 10 * position} ${470 - i * 12} ${
      684 - i * 10 * position
    } ${875 - i * 12} ${684 - i * 10 * position} ${875 - i * 12}`,
    color: `rgba(15,23,42,${0.1 + i * 0.05})`,
    width: 0.5 + i * 0.05,
  }));

  return (
    <div className={className} style={{ width: '100%', position: 'relative', minHeight: '100vh', ...style }}>
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, pointerEvents: 'none', overflow: 'hidden', transform: 'translateZ(0)' }}>
        <svg
          style={{ width: '100%', height: '100%', color: "var(--foreground)", willChange: "transform" }}
          viewBox="0 0 696 316"
          fill="none"
        >
          {paths.map((path) => (
            <motion.path
              key={path.id}
              d={path.d}
              stroke="currentColor"
              strokeWidth={path.width}
              strokeOpacity={0.15 + path.id * 0.02}
              initial={{ pathLength: 0.3, opacity: 0.3 }}
              animate={{
                pathLength: 1,
                opacity: [0.2, 0.45, 0.2],
                pathOffset: [0, 1, 0],
              }}
              transition={{
                duration: 60 + Math.random() * 30,
                repeat: Number.POSITIVE_INFINITY,
                ease: "linear",
              }}
              style={{ willChange: "opacity, stroke-dashoffset" }}
            />
          ))}
        </svg>
      </div>
      {children}
    </div>
  );
}
