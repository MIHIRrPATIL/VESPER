import React, { useState, useEffect } from 'react';
import BorderGlow from './ui/BorderGlow';
import { Calendar, Clock, Globe, RefreshCw } from 'lucide-react';

export type ChronometerMode = 'minimal' | 'accent' | 'dock';

const MODES: ChronometerMode[] = ['minimal', 'accent', 'dock'];

export const DesignerChronometer: React.FC = () => {
  const [time, setTime] = useState(new Date());
  const [use24Hour, setUse24Hour] = useState(false);
  const [mode, setMode] = useState<ChronometerMode>(() => {
    const saved = localStorage.getItem('vesper_chronometer_mode') as ChronometerMode;
    return MODES.includes(saved) ? saved : 'minimal';
  });

  useEffect(() => {
    const timer = setInterval(() => {
      setTime(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const setModeAndSave = (nextMode: ChronometerMode) => {
    setMode(nextMode);
    localStorage.setItem('vesper_chronometer_mode', nextMode);
  };

  const handleCycleNextMode = (e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const currentIndex = MODES.indexOf(mode);
    const nextMode = MODES[(currentIndex + 1) % MODES.length];
    setModeAndSave(nextMode);
  };

  const rawHours = time.getHours();
  const displayHours = use24Hour ? rawHours : (rawHours % 12 || 12);
  const hourStr = String(displayHours).padStart(2, '0');
  const digit1 = hourStr[0];
  const digit2 = hourStr[1];
  const minutes = String(time.getMinutes()).padStart(2, '0');
  const seconds = String(time.getSeconds()).padStart(2, '0');
  const period = rawHours >= 12 ? 'PM' : 'AM';

  const dayName = time.toLocaleDateString('en-US', { weekday: 'long' }).toUpperCase();
  const monthName = time.toLocaleDateString('en-US', { month: 'long' }).toUpperCase();
  const monthShort = time.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
  const dayNum = String(time.getDate()).padStart(2, '0');
  const year = time.getFullYear();

  // Day of year and week number for technical chronometer metadata
  const startOfYear = new Date(time.getFullYear(), 0, 1);
  const dayOfYear = Math.floor((time.getTime() - startOfYear.getTime()) / (1000 * 60 * 60 * 24)) + 1;
  const weekNumber = Math.ceil(dayOfYear / 7);

  // Timezone calculation
  const timezoneOffset = -time.getTimezoneOffset();
  const offsetSign = timezoneOffset >= 0 ? '+' : '-';
  const offsetHours = String(Math.floor(Math.abs(timezoneOffset) / 60)).padStart(2, '0');
  const offsetMins = String(Math.abs(timezoneOffset) % 60).padStart(2, '0');
  const tzString = `UTC${offsetSign}${offsetHours}:${offsetMins}`;

  return (
    <div className="designer-chronometer-wrapper w-full max-w-5xl mt-12 sm:mt-16 mb-8 relative group/chrono">
      {/* Layout Mode Segmented Control & Cycle Switcher */}
      <div className="absolute -top-3.5 right-2 z-30 flex items-center gap-1 p-0.5 rounded-full bg-[#121212]/90 border border-white/10 backdrop-blur-md shadow-lg opacity-80 hover:opacity-100 transition-opacity">
        <button
          type="button"
          onClick={() => setModeAndSave('minimal')}
          className={`px-2.5 py-0.5 rounded-full text-[9px] font-mono tracking-widest transition-all cursor-pointer ${
            mode === 'minimal'
              ? 'bg-white/15 text-[#E8E3DA] font-semibold border border-white/15 shadow-sm'
              : 'text-[#8E8A83] hover:text-[#D1CFC0]'
          }`}
          title="Minimal: Big centered time without borders"
        >
          MINIMAL
        </button>
        <button
          type="button"
          onClick={() => setModeAndSave('accent')}
          className={`px-2.5 py-0.5 rounded-full text-[9px] font-mono tracking-widest transition-all cursor-pointer ${
            mode === 'accent'
              ? 'bg-white/15 text-[#E8E3DA] font-semibold border border-white/15 shadow-sm'
              : 'text-[#8E8A83] hover:text-[#D1CFC0]'
          }`}
          title="Accent: Oversized leading hour digit"
        >
          ACCENT
        </button>
        <button
          type="button"
          onClick={() => setModeAndSave('dock')}
          className={`px-2.5 py-0.5 rounded-full text-[9px] font-mono tracking-widest transition-all cursor-pointer ${
            mode === 'dock'
              ? 'bg-white/15 text-[#E8E3DA] font-semibold border border-white/15 shadow-sm'
              : 'text-[#8E8A83] hover:text-[#D1CFC0]'
          }`}
          title="Dock: Modular card with borders and glow"
        >
          DOCK
        </button>
        <button
          type="button"
          onClick={(e) => handleCycleNextMode(e)}
          className="px-1.5 py-0.5 text-[#8E8A83] hover:text-[#E8E3DA] transition-colors ml-0.5 flex items-center cursor-pointer"
          title="Cycle to next layout"
        >
          <RefreshCw size={9} />
        </button>
      </div>

      {/* ==================================================================
          LAYOUT 1: PURE BORDERLESS MINIMAL
          Big font centered time on top, date and day centered below
          ================================================================== */}
      {mode === 'minimal' && (
        <div className="w-full flex flex-col items-center justify-center py-2 select-none">
          {/* Big Centered Time Lockup */}
          <div
            className="flex items-baseline justify-center cursor-pointer group transition-transform hover:scale-[1.01]"
            onClick={() => setUse24Hour((prev) => !prev)}
            title="Click to toggle 12h / 24h format"
          >
            <span className="digit-huge-minimal text-[#E8E3DA] leading-none inline-block drop-shadow-sm">
              {hourStr}
            </span>

            {/* Subtle Pulsing Colon */}
            <span className="digit-colon-huge font-mono text-[#8E8A83]/50 self-center mx-2.5 sm:mx-3.5 animate-pulse">
              :
            </span>

            {/* Minutes */}
            <span className="digit-huge-minimal text-[#E8E3DA] leading-none inline-block drop-shadow-sm">
              {minutes}
            </span>

            {/* Seconds & Period Stack */}
            <div className="flex flex-col justify-end self-end pb-2.5 sm:pb-3.5 ml-3 sm:ml-4 font-mono leading-tight">
              <span className="text-[#8E8A83] font-medium tracking-wider text-xs sm:text-sm">.{seconds}</span>
              {!use24Hour && (
                <span className="text-[#D1CFC0] font-semibold tracking-widest text-[10px] sm:text-xs uppercase mt-0.5">
                  {period}
                </span>
              )}
            </div>
          </div>

          {/* Date, Day, and Metadata below the big time */}
          <div className="flex flex-col items-center justify-center mt-3 sm:mt-4 gap-1.5 text-center">
            {/* Primary Day and Full Date */}
            <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-3 text-xs sm:text-sm font-sans tracking-[0.2em] text-[#E8E3DA] uppercase">
              <span className="font-semibold">{dayName}</span>
              <span className="text-white/20 font-normal">·</span>
              <span className="font-mono text-[#D1CFC0] tracking-wider text-xs sm:text-sm">
                {dayNum} {monthName} {year}
              </span>
            </div>

            {/* Secondary Technical Cycle Telemetry */}
            <div className="flex items-center justify-center gap-2 text-[10px] sm:text-[11px] font-mono tracking-widest text-[#8E8A83]/70 uppercase">
              <span>WEEK {weekNumber}</span>
              <span className="text-white/10">//</span>
              <span>DAY {dayOfYear}</span>
              <span className="text-white/10">//</span>
              <span>{tzString}</span>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================
          LAYOUT 2: ASYMMETRIC ACCENT
          Oversized leading hour digit, borderless
          ================================================================== */}
      {mode === 'accent' && (
        <div className="w-full flex flex-col items-center justify-center py-2 select-none">
          {/* Asymmetric Centered Time Lockup */}
          <div
            className="flex items-baseline justify-center cursor-pointer group transition-transform hover:scale-[1.01]"
            onClick={() => setUse24Hour((prev) => !prev)}
            title="Click to toggle 12h / 24h format"
          >
            {/* The oversized first hour digit */}
            <span className="digit-hero-minimal text-[#E8E3DA] leading-none inline-block drop-shadow-sm">
              {digit1}
            </span>

            {/* The second hour digit */}
            {digit2 && (
              <span className="digit-sub-minimal text-[#D1CFC0]/90 leading-none self-end pb-1.5 ml-1 inline-block">
                {digit2}
              </span>
            )}

            {/* Subtle Pulsing Colon */}
            <span className="digit-colon-minimal font-mono text-[#8E8A83]/50 self-end pb-2 mx-2 animate-pulse">
              :
            </span>

            {/* Minutes */}
            <span className="digit-minutes-minimal font-mono font-light text-[#E8E3DA] leading-none self-end pb-1.5 tracking-tight">
              {minutes}
            </span>

            {/* Seconds & Period Stack */}
            <div className="flex flex-col justify-end self-end pb-2 ml-3 font-mono text-xs leading-tight">
              <span className="text-[#8E8A83] font-medium tracking-wider">.{seconds}</span>
              {!use24Hour && (
                <span className="text-[#D1CFC0] font-semibold tracking-widest text-[10px] uppercase mt-0.5">
                  {period}
                </span>
              )}
            </div>
          </div>

          {/* Date, Day, and Metadata */}
          <div className="flex flex-wrap items-center justify-center gap-2.5 sm:gap-4 mt-3 sm:mt-3.5 text-[11px] sm:text-xs font-mono tracking-widest text-[#8E8A83]">
            <span className="text-[#E8E3DA] font-sans font-medium tracking-[0.22em] uppercase">
              {dayName}
            </span>
            <span className="text-[#8E8A83]/30">/</span>
            <span className="text-[#D1CFC0] font-mono tracking-wider">
              {dayNum} {monthShort} {year}
            </span>
            <span className="text-[#8E8A83]/30">/</span>
            <span className="text-[#8E8A83]/70">
              WEEK {weekNumber} // DAY {dayOfYear}
            </span>
            <span className="text-[#8E8A83]/30">/</span>
            <span className="text-[#8E8A83]/70">
              {tzString}
            </span>
          </div>
        </div>
      )}

      {/* ==================================================================
          LAYOUT 3: MODULAR DOCK
          BorderGlow 3-column card with borders and hairline dividers
          ================================================================== */}
      {mode === 'dock' && (
        <BorderGlow
          className="w-full rounded-xl"
          glowColor="0 0 100"
          colors={['#ffffff', '#ffffff', '#ffffff']}
          backgroundColor="#161616"
          borderRadius={12}
          glowRadius={14}
          glowIntensity={0.2}
          coneSpread={50}
          fillOpacity={0.02}
        >
          <div className="designer-chronometer-inner flex flex-col md:flex-row items-center justify-between py-3.5 px-6 sm:px-8 gap-4 select-none">
            {/* Section 1: Hero Time */}
            <div 
              className="flex items-baseline cursor-pointer group transition-opacity hover:opacity-90"
              onClick={() => setUse24Hour((prev) => !prev)}
              title="Click to toggle 12h / 24h format"
            >
              <span className="digit-hero font-serif font-light text-[#E8E3DA] leading-none tracking-tighter inline-block">
                {digit1}
              </span>
              {digit2 && (
                <span className="digit-sub font-serif font-light text-[#D1CFC0]/90 leading-none self-end pb-1 ml-0.5 inline-block">
                  {digit2}
                </span>
              )}
              <span className="text-2xl sm:text-3xl font-mono text-[#8E8A83]/50 self-end pb-1.5 mx-1.5 animate-pulse">
                :
              </span>
              <span className="text-3xl sm:text-4xl md:text-4xl font-mono font-light text-[#E8E3DA] leading-none self-end pb-1 tracking-tight">
                {minutes}
              </span>
              <div className="flex flex-col justify-end self-end pb-1.5 ml-2.5 font-mono text-[11px] leading-tight">
                <span className="text-[#8E8A83] font-medium tracking-wider">.{seconds}</span>
                {!use24Hour && (
                  <span className="text-[#D1CFC0] font-semibold tracking-widest text-[9px] uppercase mt-0.5">
                    {period}
                  </span>
                )}
              </div>
            </div>

            {/* Hairline Divider */}
            <div className="hidden md:block h-10 w-[1px] bg-white/[0.08]" />

            {/* Section 2: Day of Week & Cycle metadata */}
            <div className="flex flex-col items-center md:items-start">
              <div className="flex items-center gap-1.5 text-[#8E8A83] text-[9px] font-mono tracking-[0.25em] uppercase mb-0.5">
                <Clock size={10} className="text-[#D1CFC0]/70" />
                <span>CURRENT CYCLE</span>
              </div>
              <span className="text-sm sm:text-base font-sans font-medium tracking-[0.18em] text-[#E8E3DA] uppercase">
                {dayName}
              </span>
              <span className="text-[10px] font-mono text-[#8E8A83]/70 tracking-widest mt-0.5">
                WEEK {weekNumber} // DAY {dayOfYear}
              </span>
            </div>

            {/* Hairline Divider */}
            <div className="hidden md:block h-10 w-[1px] bg-white/[0.08]" />

            {/* Section 3: Date & Timezone */}
            <div className="flex flex-col items-center md:items-end">
              <div className="flex items-center gap-1.5 text-[#8E8A83] text-[9px] font-mono tracking-[0.25em] uppercase mb-0.5">
                <Calendar size={10} className="text-[#D1CFC0]/70" />
                <span>CALENDAR DATE</span>
              </div>
              <span className="text-sm sm:text-base font-mono font-normal tracking-wider text-[#D1CFC0]">
                {dayNum} {monthShort} {year}
              </span>
              <div className="flex items-center gap-1 text-[10px] font-mono text-[#8E8A83]/70 tracking-wider mt-0.5">
                <Globe size={9} />
                <span>{tzString}</span>
              </div>
            </div>
          </div>
        </BorderGlow>
      )}
    </div>
  );
};

