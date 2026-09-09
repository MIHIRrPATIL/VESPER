"use client";

import { useEffect, useState, useRef } from "react";
import { motion, Transition } from "motion/react";
import { cn } from "../../lib/utils";

export interface CascadePageTransitionProps {
  trigger: number;
  onViewSwap?: () => void;
  className?: string;
  panelClassName?: string;
  columns?: number;
  colors?: string[];
  duration?: number;
  staggerDelay?: number;
  ease?: Transition["ease"];
  direction?: "top" | "bottom" | "left" | "right";
  exitOpposite?: boolean;
  mode?: "in-to-out" | "out-to-in";
  showLeadingStroke?: boolean;
  showTrailingStroke?: boolean;
  strokeWidth?: number;
  leadingStrokeColors?: string[];
  trailingStrokeColors?: string[];
}

// Calibrated VESPER luxury dark tech palette: obsidian, graphite, carbon slate
const defaultVesperPalette = [
  "#141414",
  "#181818",
  "#1c1c1c",
  "#222222",
  "#262626",
  "#2c2c2c",
  "#262626",
  "#222222",
  "#1c1c1c",
  "#181818",
  "#161616",
  "#141414",
];

const defaultLeadingStroke = [
  "#E8E3DA",
  "#D1CFC0",
  "#8E8A83",
  "#5C5A56",
  "#D1CFC0",
  "#FFFFFF",
  "#E8E3DA",
  "#D1CFC0",
  "#5C5A56",
  "#8E8A83",
  "#D1CFC0",
  "#E8E3DA",
];

export function CascadePageTransition({
  trigger,
  onViewSwap,
  className,
  panelClassName,
  columns = 12,
  colors = defaultVesperPalette,
  duration = 0.44,
  staggerDelay = 0.024,
  ease = [0.76, 0, 0.24, 1],
  direction = "top",
  exitOpposite = true,
  mode = "in-to-out",
  showLeadingStroke = true,
  showTrailingStroke = false,
  strokeWidth = 2,
  leadingStrokeColors = defaultLeadingStroke,
  trailingStrokeColors = defaultLeadingStroke,
}: CascadePageTransitionProps) {
  const [transitionState, setTransitionState] = useState<"idle" | "entering" | "covered" | "exiting">("idle");
  const onViewSwapRef = useRef(onViewSwap);

  useEffect(() => {
    onViewSwapRef.current = onViewSwap;
  }, [onViewSwap]);

  useEffect(() => {
    if (trigger > 0) {
      setTransitionState("entering");

      const maxMultiplier = Math.floor((columns - 1) / 2);
      const maxStagger = maxMultiplier * staggerDelay;
      const totalAnimationTime = (duration + maxStagger) * 1000;

      const coverTimeout = setTimeout(() => {
        if (onViewSwapRef.current) {
          onViewSwapRef.current();
        }
        setTransitionState("covered");
      }, totalAnimationTime);

      const exitTimeout = setTimeout(() => {
        setTransitionState("exiting");
      }, totalAnimationTime + 60);

      const idleTimeout = setTimeout(() => {
        setTransitionState("idle");
      }, totalAnimationTime * 2 + 100);

      return () => {
        clearTimeout(coverTimeout);
        clearTimeout(exitTimeout);
        clearTimeout(idleTimeout);
      };
    }
  }, [trigger, columns, duration, staggerDelay]);

  if (transitionState === "idle") return null;

  const isVertical = direction === "top" || direction === "bottom";
  const isOutToIn = mode === "out-to-in";

  const getTransform = (state: "enter" | "exit") => {
    if (isVertical) {
      const isEnterBottom = direction === "bottom";
      if (state === "enter") {
        return { y: isEnterBottom ? "100%" : "-100%", x: "0%" };
      } else {
        return exitOpposite
          ? { y: isEnterBottom ? "-100%" : "100%", x: "0%" }
          : { y: isEnterBottom ? "100%" : "-100%", x: "0%" };
      }
    } else {
      const isEnterRight = direction === "right";
      if (state === "enter") {
        return { x: isEnterRight ? "100%" : "-100%", y: "0%" };
      } else {
        return exitOpposite
          ? { x: isEnterRight ? "-100%" : "100%", y: "0%" }
          : { x: isEnterRight ? "100%" : "-100%", y: "0%" };
      }
    }
  };

  const panels = Array.from({ length: columns }, (_, i) => i);

  return (
    <div
      key={trigger}
      className={cn(
        "pointer-events-none absolute inset-0 z-50 flex h-full w-full overflow-hidden",
        isVertical ? "flex-row" : "flex-col",
        className
      )}
    >
      {panels.map((i) => {
        const centerIndex = (columns - 1) / 2;
        const distanceFromCenter = Math.abs(i - centerIndex);
        const minDistance = columns % 2 === 0 ? 0.5 : 0;
        const delayMultiplier = distanceFromCenter - minDistance;
        const maxMultiplier = Math.floor((columns - 1) / 2);
        const finalDelayMultiplier = isOutToIn
          ? maxMultiplier - delayMultiplier
          : delayMultiplier;

        const delay = Math.max(0, finalDelayMultiplier * staggerDelay);
        const color = colors[i % colors.length];

        const leadingColor =
          leadingStrokeColors && leadingStrokeColors.length > 0
            ? leadingStrokeColors[i % leadingStrokeColors.length]
            : null;

        const trailingColor =
          trailingStrokeColors && trailingStrokeColors.length > 0
            ? trailingStrokeColors[i % trailingStrokeColors.length]
            : null;

        let leadingClasses = "absolute";
        let trailingClasses = "absolute";

        if (direction === "left") {
          leadingClasses += " right-0 top-0 bottom-0 shadow-[2px_0_12px_rgba(255,255,255,0.15)]";
          trailingClasses += " left-0 top-0 bottom-0";
        } else if (direction === "right") {
          leadingClasses += " left-0 top-0 bottom-0 shadow-[-2px_0_12px_rgba(255,255,255,0.15)]";
          trailingClasses += " right-0 top-0 bottom-0";
        } else if (direction === "top") {
          leadingClasses += " bottom-0 left-0 right-0 shadow-[0_2px_12px_rgba(255,255,255,0.15)]";
          trailingClasses += " top-0 left-0 right-0";
        } else if (direction === "bottom") {
          leadingClasses += " top-0 left-0 right-0 shadow-[0_-2px_12px_rgba(255,255,255,0.15)]";
          trailingClasses += " bottom-0 left-0 right-0";
        }

        const isCoveredOrEntering =
          transitionState === "entering" || transitionState === "covered";

        const initialPos = getTransform("enter");
        const targetPos = isCoveredOrEntering
          ? { x: "0%", y: "0%" }
          : getTransform("exit");

        return (
          <motion.div
            key={i}
            initial={initialPos}
            animate={targetPos}
            transition={{
              duration: duration,
              ease: ease,
              delay: delay,
            }}
            className={cn(
              "pointer-events-auto relative flex flex-1 items-center justify-center overflow-hidden border-r border-white/[0.03]",
              panelClassName
            )}
            style={{
              backgroundColor: color,
              width: isVertical ? `calc(${100 / columns}% + 0.5px)` : "100%",
              height: isVertical ? "100%" : `calc(${100 / columns}% + 0.5px)`,
              marginLeft: isVertical && i > 0 ? "-0.2px" : "0px",
              marginTop: !isVertical && i > 0 ? "-0.2px" : "0px",
            }}
          >
            {showLeadingStroke && leadingColor && (
              <div
                className={leadingClasses}
                style={{
                  backgroundColor: leadingColor,
                  ...(isVertical
                    ? { height: `${strokeWidth}px` }
                    : { width: `${strokeWidth}px` }),
                }}
              />
            )}

            {showTrailingStroke && trailingColor && (
              <div
                className={trailingClasses}
                style={{
                  backgroundColor: trailingColor,
                  ...(isVertical
                    ? { height: `${strokeWidth}px` }
                    : { width: `${strokeWidth}px` }),
                }}
              />
            )}
          </motion.div>
        );
      })}
    </div>
  );
}

export default CascadePageTransition;
