/**
 * VESPER Mobile Design System Tokens.
 *
 * Direct translation of the Desktop Workstation theme:
 * - Two-Tone Palette: Obsidian Dark (#141414) + Warm Bone White (#E8E3DA)
 * - Restrained Accents: Sage/Emerald (#10B981), Amber (#F59E0B), Warm Coral (#F26A4B)
 * - Hairline Structural Outlines (#2C2C2C)
 * - Technical Monospace Meta-Data & Editorial Headers
 */

import { Platform } from "react-native";

export const theme = {
  colors: {
    // Canvas & Surfaces
    bg: "#141414",
    background: "#141414",
    card: "#1C1C1C",
    cardElevated: "#222222",
    cardSubtle: "#181818",
    cardSubdued: "#181818",
    cardHover: "#282828",

    // Structural Hairlines & Borders
    border: "#2C2C2C",
    borderSubtle: "#242424",
    borderActive: "#D1CFC0",
    borderFocus: "#E8E3DA",

    // Typography
    textPrimary: "#E8E3DA",
    boneWhite: "#E8E3DA",
    textSecondary: "#D1CFC0",
    textMuted: "#8E8A83",
    textGhost: "#4A4A48",

    // Semantic Accents (strictly restrained)
    accent: "#F26A4B",        // Coral for alerts, debits, primary actions
    coral: "#F26A4B",
    success: "#10B981",       // Emerald for connected, healthy, synced
    emerald: "#10B981",
    warning: "#F59E0B",       // Amber for scanning, pending, reconnecting
    amber: "#F59E0B",
    error: "#EF4444",         // Crimson for disconnected, critical faults
    crimson: "#EF4444",
    rose: "#F43F5E",
    info: "#60A5FA",          // Subdued blue for informational badges
  },

  fonts: {
    mono: Platform.select({ ios: "Menlo", default: "monospace" }),
    sans: Platform.select({ ios: "System", default: "sans-serif" }),
    serif: Platform.select({ ios: "Georgia", default: "serif" }),
  },

  radii: {
    xs: 4,
    sm: 6,
    md: 8,
    lg: 12,
    full: 9999,
  },

  spacing: {
    xxs: 2,
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 20,
    xxl: 24,
    macro: 32,
  },
};
