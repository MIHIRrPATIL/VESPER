import React from "react";
import { Terminal, Wrench, Cpu, CheckCircle2, ChevronRight } from "lucide-react";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@/components/ui/drawer";

export interface ToolCallItem {
  id: string;
  name: string;
  args?: Record<string, any>;
  status?: "pending" | "running" | "completed" | "failed";
  timestamp?: string;
  durationMs?: number;
}

export interface SmoothDrawerProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  description?: string;
  toolCalls?: ToolCallItem[];
  triggerText?: string;
  primaryButtonText?: string;
  secondaryButtonText?: string;
  onPrimaryAction?: () => void;
  onSecondaryAction?: () => void;
  children?: React.ReactNode;
}

const drawerVariants = {
  hidden: {
    y: "100%",
    opacity: 0,
    rotateX: 4,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 30,
    },
  },
  visible: {
    y: 0,
    opacity: 1,
    rotateX: 0,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 30,
      mass: 0.8,
      staggerChildren: 0.07,
      delayChildren: 0.15,
    },
  },
};

const itemVariants = {
  hidden: {
    y: 18,
    opacity: 0,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 30,
    },
  },
  visible: {
    y: 0,
    opacity: 1,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 30,
      mass: 0.8,
    },
  },
};

export const SmoothDrawer: React.FC<SmoothDrawerProps> = ({
  title = "Tool Execution Stream",
  description = "Inspecting agent tool dispatches, RPC invocations, and runtime execution metrics.",
  toolCalls = [
    {
      id: "call-101",
      name: "media_player.control",
      args: { action: "play-pause", sink: "@DEFAULT_AUDIO_SINK@" },
      status: "completed",
      timestamp: "00:54:12",
      durationMs: 42,
    },
    {
      id: "call-102",
      name: "system_telemetry.query",
      args: { metric: "dpms_display_state", display_count: 2 },
      status: "completed",
      timestamp: "00:54:13",
      durationMs: 18,
    },
    {
      id: "call-103",
      name: "chronometer.cycle_layout",
      args: { mode: "minimal", persist: true },
      status: "running",
      timestamp: "00:54:14",
      durationMs: 8,
    }
  ],
  triggerText = "Inspect Tool Calls",
  primaryButtonText = "Execute Directive",
  secondaryButtonText = "Dismiss",
  onPrimaryAction,
  onSecondaryAction,
  children,
}) => {
  return (
    <Drawer>
      <DrawerTrigger asChild>
        {children || (
          <Button 
            variant="outline" 
            className="h-8 px-3 rounded-full text-xs font-mono tracking-wider border-white/10 bg-neutral-900/80 hover:bg-neutral-800 text-[#D1CFC0] hover:text-[#E8E3DA] transition-all cursor-pointer shadow-md"
          >
            <Wrench size={13} className="mr-1.5 text-[#8E8A83]" />
            <span>{triggerText}</span>
          </Button>
        )}
      </DrawerTrigger>
      <DrawerContent className="mx-auto max-w-lg rounded-t-2xl p-6 shadow-2xl bg-[#141414] border-white/10 text-[#E8E3DA]">
        <motion.div
          animate="visible"
          className="mx-auto w-full max-w-md space-y-5"
          initial="hidden"
          variants={drawerVariants as any}
        >
          {/* Header */}
          <motion.div variants={itemVariants as any}>
            <DrawerHeader className="space-y-2 px-0 text-left">
              <DrawerTitle className="flex items-center gap-2.5 font-sans font-semibold text-lg tracking-tight text-[#E8E3DA]">
                <div className="rounded-lg bg-white/[0.05] border border-white/10 p-1.5 flex items-center justify-center">
                  <Terminal size={18} className="text-[#E8E3DA]" />
                </div>
                <span>{title}</span>
              </DrawerTitle>
              <DrawerDescription className="text-xs font-sans text-[#8E8A83] leading-relaxed">
                {description}
              </DrawerDescription>
            </DrawerHeader>
          </motion.div>

          {/* Staggered Tool Call Items */}
          <motion.div variants={itemVariants as any} className="space-y-2">
            <div className="text-[10px] font-mono tracking-widest text-[#8E8A83]/70 uppercase px-1">
              ACTIVE TOOL PIPELINE ({toolCalls.length})
            </div>
            <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
              {toolCalls.map((call) => (
                <div
                  key={call.id}
                  className="flex items-center justify-between p-2.5 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:border-white/15 transition-all text-xs font-mono"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {call.status === "completed" ? (
                      <CheckCircle2 size={13} className="text-[#8E8A83] shrink-0" />
                    ) : (
                      <Cpu size={13} className="text-[#D1CFC0] animate-pulse shrink-0" />
                    )}
                    <span className="text-[#E8E3DA] truncate font-medium">{call.name}</span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-[#8E8A83] shrink-0">
                    {call.durationMs && <span>{call.durationMs}ms</span>}
                    <span className="px-1.5 py-0.5 rounded bg-white/[0.05] text-[#D1CFC0] uppercase text-[9px]">
                      {call.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* Footer & Actions */}
          <motion.div variants={itemVariants as any}>
            <DrawerFooter className="flex flex-col gap-2.5 px-0 pt-2">
              <button
                type="button"
                onClick={onPrimaryAction}
                className="group relative inline-flex h-10 w-full items-center justify-center overflow-hidden rounded-xl bg-white/10 hover:bg-white/15 border border-white/20 font-medium text-xs text-[#E8E3DA] tracking-wider transition-all duration-300 shadow-lg cursor-pointer"
              >
                <motion.span
                  className="absolute inset-0 translate-x-[-200%] bg-gradient-to-r from-transparent via-white/15 to-transparent"
                  transition={{
                    duration: 1.6,
                    ease: "easeInOut",
                    repeat: Number.POSITIVE_INFINITY,
                    repeatDelay: 2.5,
                  }}
                  animate={{
                    x: ["-200%", "200%"],
                  }}
                />
                <span className="relative flex items-center gap-1.5">
                  {primaryButtonText}
                  <ChevronRight size={13} className="transition-transform group-hover:translate-x-0.5" />
                </span>
              </button>
              <DrawerClose asChild>
                <Button
                  variant="outline"
                  onClick={onSecondaryAction}
                  className="h-9 w-full rounded-xl border-white/10 bg-transparent font-sans text-xs text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.04] transition-colors cursor-pointer"
                >
                  {secondaryButtonText}
                </Button>
              </DrawerClose>
            </DrawerFooter>
          </motion.div>
        </motion.div>
      </DrawerContent>
    </Drawer>
  );
};

export default SmoothDrawer;
