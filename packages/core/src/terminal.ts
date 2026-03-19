import type { TerminalOptions, TerminalInstance } from "./types.js";

/**
 * Headless terminal connection to an agisdk-server.
 *
 * Protocol:
 *   - Binary frames: raw PTY I/O
 *   - Text frames: JSON control messages
 *     - {"type": "resize", "cols": 80, "rows": 24}
 *     - {"type": "ping"} → {"type": "pong"}
 */
export class AgiTerminal implements TerminalInstance {
  private ws: WebSocket | null = null;
  private options: TerminalOptions;

  constructor(options: TerminalOptions) {
    this.options = options;
    this.connect();
  }

  private connect(): void {
    const endpoint = this.options.endpoint.replace(/\/$/, "");
    const sessionId = this.options.sessionId ?? "";
    const protocol = endpoint.startsWith("https") ? "wss:" : "ws:";
    const host = endpoint.replace(/^https?:\/\//, "");

    // agisdk WebSocket: /ws/sdk/{session_id}?api_key=xxx
    const params = new URLSearchParams();
    if (this.options.apiKey) {
      params.set("api_key", this.options.apiKey);
    }
    const qs = params.toString() ? `?${params.toString()}` : "";
    const url = `${protocol}//${host}/ws/sdk/${sessionId}${qs}`;

    this.ws = new WebSocket(url);
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      this.options.onConnect?.();
    };

    this.ws.onclose = () => {
      this.options.onDisconnect?.();
    };

    this.ws.onerror = (event) => {
      this.options.onError?.(event);
    };

    this.ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        // Binary frame: PTY output
        const data = new Uint8Array(event.data);
        this.options.onOutput?.(data);
      } else {
        // Text frame: control message
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "pong") {
            // Ping response, ignore
          }
        } catch {
          // Ignore malformed messages
        }
      }
    };
  }

  sendInput(data: string): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    const encoder = new TextEncoder();
    this.ws.send(encoder.encode(data));
  }

  sendInputBytes(data: Uint8Array): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(data);
  }

  resize(cols: number, rows: number): void {
    this.sendControl({ type: "resize", cols, rows });
  }

  sendControl(message: Record<string, unknown>): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify(message));
  }

  dispose(): void {
    this.ws?.close();
    this.ws = null;
  }
}
