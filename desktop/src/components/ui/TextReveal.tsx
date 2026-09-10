"use client";

import React, { useRef, useState, useEffect } from "react";
import {
  motion,
  useScroll,
  useTransform,
  type MotionValue,
} from "motion/react";
import { cn } from "../../lib/utils";

export interface TextRevealProps {
  paragraphs?: string[];
  text?: string;
  className?: string;
  paragraphClassName?: string;
  containerRef?: React.RefObject<HTMLElement | null>;
  speechProgress?: MotionValue<number>;
  autoScroll?: boolean;
  highlightColor?: string;
  lightWatermarkColor?: string;
  darkWatermarkColor?: string;
  lightTextColor?: string;
  darkTextColor?: string;
}

export const TextReveal = ({
  paragraphs = [],
  text = "",
  className = "",
  paragraphClassName = "",
  containerRef,
  speechProgress,
  autoScroll = true,
  highlightColor = "#FFFFFF",
  lightWatermarkColor = "#8E8A83",
  darkWatermarkColor = "#8E8A83",
  lightTextColor = "#E8E3DA",
  darkTextColor = "#E8E3DA",
}: TextRevealProps) => {
  const targetRef = useRef<HTMLDivElement>(null);
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    const checkDark = () => {
      const darkActive =
        document.documentElement.classList.contains("dark") ||
        document.body.classList.contains("dark") ||
        !!targetRef.current?.closest(".dark") ||
        document.querySelector(".dark") !== null;
      setIsDark(darkActive);
    };
    checkDark();

    const observer = new MutationObserver(checkDark);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => observer.disconnect();
  }, []);

  const { scrollYProgress } = useScroll({
    target: targetRef,
    container: containerRef,
    offset: ["start 0.8", "end 0.3"],
  });

  // If speechProgress is provided (driven by TTS playback), use it; otherwise use scroll
  const activeProgress = speechProgress || scrollYProgress;

  // Derive paragraph array
  let derivedParagraphs = paragraphs;
  if (derivedParagraphs.length === 0 && text.trim().length > 0) {
    // Split by double newline, or split long text into cohesive sentence groupings
    const rawBlocks = text.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean);
    if (rawBlocks.length > 0) {
      derivedParagraphs = rawBlocks;
    } else {
      derivedParagraphs = [text.trim()];
    }
  }

  if (derivedParagraphs.length === 0) {
    return null;
  }

  return (
    <div ref={targetRef} className={cn("py-4", className)}>
      <div className="mx-auto w-full space-y-6">
        {derivedParagraphs.map((paragraph, index) => (
          <Paragraph
            key={index}
            paragraph={paragraph}
            progress={activeProgress}
            index={index}
            total={derivedParagraphs.length}
            isDark={isDark}
            paragraphClassName={paragraphClassName}
            highlightColor={highlightColor}
            lightWatermarkColor={lightWatermarkColor}
            darkWatermarkColor={darkWatermarkColor}
            lightTextColor={lightTextColor}
            darkTextColor={darkTextColor}
            autoScroll={autoScroll}
          />
        ))}
      </div>
    </div>
  );
};

interface ParagraphProps {
  paragraph: string;
  progress: MotionValue<number>;
  index: number;
  total: number;
  isDark: boolean;
  paragraphClassName?: string;
  highlightColor: string;
  lightWatermarkColor: string;
  darkWatermarkColor: string;
  lightTextColor: string;
  darkTextColor: string;
  autoScroll?: boolean;
}

const Paragraph = ({
  paragraph,
  progress,
  index,
  total,
  isDark,
  paragraphClassName,
  highlightColor,
  lightWatermarkColor,
  darkWatermarkColor,
  lightTextColor,
  darkTextColor,
  autoScroll,
}: ParagraphProps) => {
  const paragraphRef = useRef<HTMLParagraphElement>(null);
  const words = paragraph.split(" ");
  const paragraphStart = index / total;
  const paragraphEnd = (index + 1) / total;
  const hasScrolledRef = useRef(false);

  useEffect(() => {
    if (!autoScroll) return;

    const unsubscribe = progress.on("change", (currentProgress) => {
      if (
        currentProgress >= paragraphStart &&
        currentProgress < paragraphEnd &&
        !hasScrolledRef.current
      ) {
        hasScrolledRef.current = true;
        paragraphRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "nearest",
        });
      } else if (currentProgress < paragraphStart) {
        hasScrolledRef.current = false;
      }
    });

    return () => unsubscribe();
  }, [progress, paragraphStart, paragraphEnd, autoScroll]);

  return (
    <p
      ref={paragraphRef}
      className={cn(
        "text-left text-lg md:text-xl leading-relaxed font-sans font-normal transition-colors",
        paragraphClassName,
      )}
    >
      {words.map((word, wIndex) => {
        const wordStartFraction = wIndex / words.length;
        const wordEndFraction = (wIndex + 1) / words.length;
        const wordGlobalStart =
          paragraphStart + wordStartFraction * (paragraphEnd - paragraphStart);
        const wordGlobalEnd =
          paragraphStart + wordEndFraction * (paragraphEnd - paragraphStart);

        return (
          <Word
            key={wIndex}
            progress={progress}
            range={[wordGlobalStart, wordGlobalEnd]}
            isDark={isDark}
            highlightColor={highlightColor}
            lightWatermarkColor={lightWatermarkColor}
            darkWatermarkColor={darkWatermarkColor}
            lightTextColor={lightTextColor}
            darkTextColor={darkTextColor}
          >
            {word}
          </Word>
        );
      })}
    </p>
  );
};

interface WordProps {
  children: string;
  progress: MotionValue<number>;
  range: [number, number];
  isDark: boolean;
  highlightColor: string;
  lightWatermarkColor: string;
  darkWatermarkColor: string;
  lightTextColor: string;
  darkTextColor: string;
}

const Word = ({
  children,
  progress,
  range,
  isDark,
  highlightColor,
  lightWatermarkColor,
  darkWatermarkColor,
  lightTextColor,
  darkTextColor,
}: WordProps) => {
  const characters = children.split("");

  return (
    <span className="relative mr-1.5 inline-block md:mr-2">
      {characters.map((char, i) => {
        const charStart =
          range[0] + (i / characters.length) * (range[1] - range[0]);
        const charEnd =
          range[0] + ((i + 1) / characters.length) * (range[1] - range[0]);

        return (
          <Character
            key={i}
            progress={progress}
            range={[charStart, charEnd]}
            isDark={isDark}
            highlightColor={highlightColor}
            lightWatermarkColor={lightWatermarkColor}
            darkWatermarkColor={darkWatermarkColor}
            lightTextColor={lightTextColor}
            darkTextColor={darkTextColor}
          >
            {char}
          </Character>
        );
      })}
    </span>
  );
};

interface CharacterProps {
  children: string;
  progress: MotionValue<number>;
  range: [number, number];
  isDark: boolean;
  highlightColor: string;
  lightWatermarkColor: string;
  darkWatermarkColor: string;
  lightTextColor: string;
  darkTextColor: string;
}

const Character = ({
  children,
  progress,
  range,
  isDark,
  highlightColor,
  lightWatermarkColor,
  darkWatermarkColor,
  lightTextColor,
  darkTextColor,
}: CharacterProps) => {
  const rangeStart = range[0];
  const rangeEnd = range[1];

  const startColor = isDark ? darkWatermarkColor : lightWatermarkColor;
  const midColor = highlightColor;
  const endColor = isDark ? darkTextColor : lightTextColor;

  const color = useTransform(
    progress,
    [
      rangeStart,
      rangeStart + 0.05 * (rangeEnd - rangeStart),
      rangeStart + 0.75 * (rangeEnd - rangeStart),
      rangeEnd,
    ],
    [startColor, startColor, midColor, endColor],
  );

  const opacity = useTransform(
    progress,
    [0, rangeStart, rangeEnd],
    [0.72, 0.72, 1],
  );

  return (
    <motion.span
      style={{
        color,
        opacity,
      }}
      className="inline-block transition-none"
    >
      {children}
    </motion.span>
  );
};

export default TextReveal;
