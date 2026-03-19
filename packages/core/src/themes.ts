import type { TerminalTheme } from "./types.js";

export const DARK_THEME: TerminalTheme = {
  background: "#1a1b26",
  foreground: "#c0caf5",
  cursor: "#c0caf5",
  selectionBackground: "#33467c",
  black: "#15161e",
  red: "#f7768e",
  green: "#9ece6a",
  yellow: "#e0af68",
  blue: "#7aa2f7",
  magenta: "#bb9af7",
  cyan: "#7dcfff",
  white: "#a9b1d6",
  brightBlack: "#414868",
  brightRed: "#f7768e",
  brightGreen: "#9ece6a",
  brightYellow: "#e0af68",
  brightBlue: "#7aa2f7",
  brightMagenta: "#bb9af7",
  brightCyan: "#7dcfff",
  brightWhite: "#c0caf5",
};

export const LIGHT_THEME: TerminalTheme = {
  background: "#f5f5f5",
  foreground: "#343b58",
  cursor: "#343b58",
  selectionBackground: "#b4d5fe",
  black: "#0f0f14",
  red: "#8c4351",
  green: "#33635c",
  yellow: "#8f5e15",
  blue: "#34548a",
  magenta: "#5a4a78",
  cyan: "#0f4b6e",
  white: "#343b58",
  brightBlack: "#9699a3",
  brightRed: "#8c4351",
  brightGreen: "#33635c",
  brightYellow: "#8f5e15",
  brightBlue: "#34548a",
  brightMagenta: "#5a4a78",
  brightCyan: "#0f4b6e",
  brightWhite: "#343b58",
};

export function resolveTheme(theme?: "dark" | "light" | TerminalTheme): TerminalTheme {
  if (!theme || theme === "dark") return DARK_THEME;
  if (theme === "light") return LIGHT_THEME;
  return theme; // Custom theme object
}
