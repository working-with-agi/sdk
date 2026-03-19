import { HttpClient } from "./http-client.js";
import type { CreateSessionParams, SessionInfo, ToolInfo, AddPaneParams, PaneInfo, LayoutTree } from "./types.js";

/**
 * REST API client for agiterm-server.
 * Manages sessions and tool discovery.
 */
export class AgiApiClient extends HttpClient {
  /** List available AI CLI tools. */
  async listTools(): Promise<Record<string, ToolInfo>> {
    return this.fetch("/api/v1/tools");
  }

  /** Create a new terminal session. */
  async createSession(params: CreateSessionParams): Promise<SessionInfo> {
    return this.fetch("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  /** List all sessions for the authenticated tenant. */
  async listSessions(): Promise<SessionInfo[]> {
    return this.fetch("/api/v1/sessions");
  }

  /** Destroy a terminal session. */
  async destroySession(sessionId: string): Promise<void> {
    await this.fetch(`/api/v1/sessions/${sessionId}`, {
      method: "DELETE",
    });
  }

  /** Resize a session's PTY. */
  async resizeSession(sessionId: string, cols: number, rows: number): Promise<void> {
    await this.fetch(`/api/v1/sessions/${sessionId}/resize?cols=${cols}&rows=${rows}`, {
      method: "POST",
    });
  }

  /** Add a pane to a session workspace. */
  async addPane(sessionId: string, params: AddPaneParams = {}): Promise<PaneInfo> {
    return this.fetch(`/api/v1/sessions/${sessionId}/panes`, {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  /** Remove a pane from a session workspace. */
  async removePane(sessionId: string, paneId: string): Promise<void> {
    await this.fetch(`/api/v1/sessions/${sessionId}/panes/${paneId}`, {
      method: "DELETE",
    });
  }

  /** Get the current layout tree for a session workspace. */
  async getLayout(sessionId: string): Promise<LayoutTree> {
    return this.fetch(`/api/v1/sessions/${sessionId}/layout`);
  }

  /** Health check. */
  async health(): Promise<{ status: string }> {
    return this.fetch("/api/v1/health");
  }
}
