import type { TerminalTheme } from "./types.js";

// ---------------------------------------------------------------------------
// Light themes (default — service-friendly)
// ---------------------------------------------------------------------------

/** Clean white — blends into any light UI */
export const LIGHT_THEME: TerminalTheme = {
  background: "#ffffff",
  foreground: "#24292e",
  cursor: "#24292e",
  selectionBackground: "#c8d1dc",
  black: "#24292e",
  red: "#d73a49",
  green: "#22863a",
  yellow: "#b08800",
  blue: "#0366d6",
  magenta: "#6f42c1",
  cyan: "#1b7c83",
  white: "#d1d5da",
  brightBlack: "#959da5",
  brightRed: "#cb2431",
  brightGreen: "#28a745",
  brightYellow: "#dbab09",
  brightBlue: "#2188ff",
  brightMagenta: "#8a63d2",
  brightCyan: "#3192aa",
  brightWhite: "#fafbfc",
};

/** Warm off-white — softer, less clinical */
export const LIGHT_WARM: TerminalTheme = {
  background: "#faf8f5",
  foreground: "#3d3833",
  cursor: "#3d3833",
  selectionBackground: "#e8e0d4",
  black: "#3d3833",
  red: "#b04040",
  green: "#3a7a40",
  yellow: "#8a6520",
  blue: "#3060a0",
  magenta: "#7040a0",
  cyan: "#1a7070",
  white: "#d0ccc5",
  brightBlack: "#908880",
  brightRed: "#b04040",
  brightGreen: "#3a7a40",
  brightYellow: "#8a6520",
  brightBlue: "#3060a0",
  brightMagenta: "#7040a0",
  brightCyan: "#1a7070",
  brightWhite: "#f5f0eb",
};

/** Cool blue-grey — professional, corporate-friendly */
export const LIGHT_COOL: TerminalTheme = {
  background: "#f5f7fa",
  foreground: "#2d3748",
  cursor: "#2d3748",
  selectionBackground: "#d4e4f7",
  black: "#2d3748",
  red: "#c53030",
  green: "#276749",
  yellow: "#975a16",
  blue: "#2b6cb0",
  magenta: "#6b46c1",
  cyan: "#086f83",
  white: "#cbd5e0",
  brightBlack: "#a0aec0",
  brightRed: "#c53030",
  brightGreen: "#276749",
  brightYellow: "#975a16",
  brightBlue: "#2b6cb0",
  brightMagenta: "#6b46c1",
  brightCyan: "#086f83",
  brightWhite: "#edf2f7",
};

/** Light with subtle grey background — easier on the eyes */
export const LIGHT_SOFT: TerminalTheme = {
  background: "#f0f0f0",
  foreground: "#333333",
  cursor: "#333333",
  selectionBackground: "#cce0f0",
  black: "#333333",
  red: "#c0392b",
  green: "#27ae60",
  yellow: "#f39c12",
  blue: "#2980b9",
  magenta: "#8e44ad",
  cyan: "#16a085",
  white: "#bdc3c7",
  brightBlack: "#7f8c8d",
  brightRed: "#e74c3c",
  brightGreen: "#2ecc71",
  brightYellow: "#f1c40f",
  brightBlue: "#3498db",
  brightMagenta: "#9b59b6",
  brightCyan: "#1abc9c",
  brightWhite: "#ecf0f1",
};

// ---------------------------------------------------------------------------
// Dark theme (single option for dark-mode services)
// ---------------------------------------------------------------------------

export const DARK_THEME: TerminalTheme = {
  background: "#1e1e1e",
  foreground: "#d4d4d4",
  cursor: "#aeafad",
  selectionBackground: "#264f78",
  black: "#1e1e1e",
  red: "#f44747",
  green: "#6a9955",
  yellow: "#d7ba7d",
  blue: "#569cd6",
  magenta: "#c586c0",
  cyan: "#4ec9b0",
  white: "#d4d4d4",
  brightBlack: "#808080",
  brightRed: "#f44747",
  brightGreen: "#6a9955",
  brightYellow: "#d7ba7d",
  brightBlue: "#569cd6",
  brightMagenta: "#c586c0",
  brightCyan: "#4ec9b0",
  brightWhite: "#e5e5e5",
};

// ---------------------------------------------------------------------------
// Theme registry
// ---------------------------------------------------------------------------

export interface ThemeEntry {
  name: string;
  label: string;
  dark: boolean;
  theme: TerminalTheme;
}

export const THEME_PRESETS: ThemeEntry[] = [
  { name: "light", label: "Light", dark: false, theme: LIGHT_THEME },
  { name: "light-warm", label: "Light Warm", dark: false, theme: LIGHT_WARM },
  { name: "light-cool", label: "Light Cool", dark: false, theme: LIGHT_COOL },
  { name: "light-soft", label: "Light Soft", dark: false, theme: LIGHT_SOFT },
  { name: "dark", label: "Dark", dark: true, theme: DARK_THEME },
];

export function resolveTheme(theme?: string | TerminalTheme): TerminalTheme {
  if (!theme) return LIGHT_THEME;
  if (typeof theme === "object") return theme;
  const entry = THEME_PRESETS.find((t) => t.name === theme);
  return entry?.theme ?? LIGHT_THEME;
}
