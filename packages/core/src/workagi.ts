import { AgiTerminal } from "./terminal.js";
import { AgiRenderedTerminal } from "./rendered-terminal.js";
import { AgiApiClient } from "./api-client.js";
import type {
  TerminalOptions,
  RenderedTerminalOptions,
  TerminalInstance,
} from "./types.js";

export const WorkAGI = {
  /**
   * Create a REST API client for session management.
   *
   * @example
   * const api = WorkAGI.api("https://server:8600", "your-api-key");
   * const session = await api.createSession({ user_id: "user-1" });
   *
   * const term = WorkAGI.terminal({
   *   container: "#terminal",
   *   endpoint: "https://server:8600",
   *   apiKey: "your-api-key",
   *   sessionId: session.session_id,
   * });
   */
  api(endpoint: string, apiKey: string): AgiApiClient {
    return new AgiApiClient(endpoint, apiKey);
  },

  /**
   * Create a headless terminal connection (no rendering).
   * Use this when you handle rendering yourself.
   */
  connect(options: TerminalOptions): TerminalInstance {
    return new AgiTerminal(options);
  },

  /**
   * Mount a fully rendered terminal with xterm.js.
   */
  terminal(options: RenderedTerminalOptions): AgiRenderedTerminal {
    return new AgiRenderedTerminal(options);
  },

};
