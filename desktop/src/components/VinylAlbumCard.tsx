"use client";

import React, { useState, useEffect } from "react";
import { motion } from "motion/react";
import { Play, Pause, SkipBack, SkipForward, Disc3, Music2 } from "lucide-react";
import { cn } from "../lib/utils";
import { mediaService } from "../services/media-service";
import { NowPlayingTrack } from "../types/vesper";

export interface VinylAlbumCardProps {
  className?: string;
}

export function VinylAlbumCard({ className }: VinylAlbumCardProps) {
  const [track, setTrack] = useState<NowPlayingTrack>(mediaService.getTrack());
  const [isHovered, setIsHovered] = useState(false);
  const [isActionPending, setIsActionPending] = useState(false);
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    const unsub = mediaService.subscribe(() => {
      setTrack(mediaService.getTrack());
    });
    return () => unsub();
  }, []);

  useEffect(() => {
    setImgError(false);
  }, [track.art_url]);

  const handlePlayPause = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsActionPending(true);
    await mediaService.playPause();
    setIsActionPending(false);
  };

  const handleNext = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsActionPending(true);
    await mediaService.next();
    setIsActionPending(false);
  };

  const handlePrev = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsActionPending(true);
    await mediaService.previous();
    setIsActionPending(false);
  };

  const hasArt = Boolean(track.art_url && track.art_url.trim().length > 0 && !imgError);
  const isPlaying = track.is_playing;

  return (
    <div
      className={cn(
        "group relative flex flex-col items-center justify-center text-center select-none transition-all duration-300",
        className
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Vinyl Stage: Symmetrically centered h-48 w-48 box with vinyl completely inside sleeve when idle */}
      <div className="relative z-10 flex h-48 w-48 items-center justify-center">
        {/* Popping Vinyl Record (Centered inside behind sleeve at x:0, pops out to right on hover) */}
        <motion.div
          className="absolute inset-0 z-10 flex h-48 w-48 items-center justify-center overflow-hidden rounded-full border border-white/[0.14] bg-[#0d0d0d] shadow-2xl shadow-black/90"
          initial={{ x: 0 }}
          animate={{
            x: isHovered ? 100 : 0,
          }}
          transition={{ type: "spring", stiffness: 85, damping: 15, mass: 1 }}
        >
          {/* Inner rotating container (rotates continuously while playing, or 180deg spring on hover) */}
          <motion.div
            className="relative flex h-full w-full items-center justify-center"
            animate={{
              rotate: isPlaying ? 360 : isHovered ? 180 : 0,
            }}
            transition={
              isPlaying
                ? {
                    repeat: Infinity,
                    duration: 3.5,
                    ease: "linear",
                  }
                : {
                    type: "spring",
                    stiffness: 80,
                    damping: 15,
                    mass: 1,
                  }
            }
          >
            {/* Monochromatic Concentric Vinyl Grooves */}
            <div className="absolute inset-1 rounded-full border border-white/[0.08]" />
            <div className="absolute inset-2.5 rounded-full border border-white/[0.04]" />
            <div className="absolute inset-4 rounded-full border border-white/[0.08]" />
            <div className="absolute inset-6 rounded-full border border-white/[0.04]" />
            <div className="absolute inset-8 rounded-full border border-white/[0.08]" />
            <div className="absolute inset-10 rounded-full border border-white/[0.04]" />
            <div className="absolute inset-12 rounded-full border border-white/[0.08]" />
            <div className="absolute inset-14 rounded-full border border-white/[0.04]" />
            <div className="absolute inset-16 rounded-full border border-white/[0.08]" />

            {/* Vinyl Surface Brushed Sheen Highlight */}
            <div className="pointer-events-none absolute inset-0 rotate-45 bg-gradient-to-tr from-white/[0.08] via-transparent to-white/[0.04]" />
            <div className="pointer-events-none absolute inset-0 -rotate-45 bg-gradient-to-br from-white/[0.06] via-transparent to-white/[0.03]" />

            {/* Inner Record Label with Artwork */}
            <div className="relative flex h-18 w-18 items-center justify-center overflow-hidden rounded-full bg-[#181818] border border-white/[0.18]">
              {hasArt ? (
                <img
                  src={track.art_url}
                  alt="Vinyl center label"
                  onError={() => setImgError(true)}
                  className="absolute inset-0 h-full w-full object-cover scale-[1.08]"
                />
              ) : (
                <Disc3 size={24} className="text-[#8E8A83]" />
              )}
              {/* Center Spindle Hole */}
              <div className="z-10 h-3 w-3 rounded-full bg-[#0a0a0a] ring-1 ring-white/20 shadow-inner" />
            </div>
          </motion.div>
        </motion.div>

        {/* Front Sleeve Jacket: Symmetrically centered at inset-0 */}
        <motion.div
          className="absolute inset-0 z-20 h-48 w-48 overflow-hidden rounded-xl bg-[#181818] border border-white/[0.12] shadow-2xl shadow-black/80"
          initial={{ rotate: 0, scale: 1, x: 0 }}
          animate={{
            rotate: isHovered ? -4 : 0,
            scale: isHovered ? 0.98 : 1,
            x: isHovered ? -18 : 0,
          }}
          transition={{ type: "spring", stiffness: 150, damping: 20 }}
        >
          {hasArt ? (
            <img
              src={track.art_url}
              alt={track.album || track.title}
              onError={() => setImgError(true)}
              className="absolute inset-0 h-full w-full object-cover"
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full w-full bg-[#141414] text-[#8E8A83] p-4 text-center">
              <Music2 size={32} className="mb-2 text-[#8E8A83]" />
              <span className="font-mono text-[10px] uppercase tracking-wider text-[#8E8A83]">VESPER AUDIO</span>
            </div>
          )}
          {/* Subtle glossy sleeve edge reflection */}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-tr from-black/40 via-transparent to-white/[0.06]" />
        </motion.div>
      </div>

      {/* Centered Track Metadata & Audio Controls Bar */}
      <div className="z-20 mt-4 flex flex-col items-center justify-center w-52 px-1 text-center">
        <div className="flex flex-col items-center text-center w-full min-w-0 mb-1">
          <div className="flex items-center justify-center gap-1.5 max-w-full">
            <span className="font-sans text-sm font-semibold text-[#E8E3DA] truncate tracking-tight">
              {track.title || "No Media Playing"}
            </span>
          </div>
          <span className="font-sans text-xs text-[#8E8A83] truncate max-w-full font-medium mt-0.5">
            {track.artist || "Spotify / Audio Sink"}
          </span>
        </div>

        {/* Centered Monochromatic Playback Controls */}
        <div className="mt-2.5 flex items-center justify-center gap-2.5 bg-black/60 backdrop-blur-md px-3.5 py-1.5 rounded-xl border border-white/[0.08] shadow-lg">
          <button
            type="button"
            onClick={handlePrev}
            disabled={isActionPending}
            className="p-1.5 rounded-lg text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.08] transition-colors"
            title="Previous Track"
          >
            <SkipBack size={16} strokeWidth={2.2} />
          </button>

          <button
            type="button"
            onClick={handlePlayPause}
            disabled={isActionPending}
            className="p-2 rounded-lg bg-white/[0.10] text-[#E8E3DA] hover:bg-white/[0.18] hover:text-white transition-colors border border-white/[0.12]"
            title={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? (
              <Pause size={16} strokeWidth={2.5} />
            ) : (
              <Play size={16} strokeWidth={2.5} className="ml-0.5" />
            )}
          </button>

          <button
            type="button"
            onClick={handleNext}
            disabled={isActionPending}
            className="p-1.5 rounded-lg text-[#8E8A83] hover:text-[#E8E3DA] hover:bg-white/[0.08] transition-colors"
            title="Next Track"
          >
            <SkipForward size={16} strokeWidth={2.2} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default VinylAlbumCard;
