export { AgiTerminal } from "./AgiTerminal.js";
export { default as AgiWorkspace } from "./AgiWorkspace.vue";
export { default as AgiPilot } from "./AgiPilot.vue";

// End-user facing aliases
export { default as WorkWithAI } from "./AgiWorkspace.vue";
export { default as PaneLayout } from "./PaneLayout.vue";
export type { PaneNode, PaneTerminalHandle } from "./PaneLayout.vue";
export type {
  TerminalOptions,
  RenderedTerminalOptions,
  TerminalInstance,
  CreateSessionParams,
  SessionInfo,
} from "@working-with-agi/sdk";

// Tmux components, stores, services, and types
export * from "./components/index.js";
