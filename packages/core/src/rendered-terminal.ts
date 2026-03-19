import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import { AgiTerminal } from "./terminal.js";
import { resolveTheme } from "./themes.js";
import type { RenderedTerminalOptions, TerminalInstance } from "./types.js";

/**
 * A fully rendered terminal that combines xterm.js with
 * the agiterm-server WebSocket connection.
 *
 * Theme can be:
 *   - "dark" / "light" (built-in presets)
 *   - A custom TerminalTheme object
 *
 * Usage:
 *   const term = new AgiRenderedTerminal({
 *     container: "#terminal",
 *     endpoint: "https://your-server:8600",
 *     apiKey: "your-api-key",
 *     sessionId: "sdk-abc123",
 *     theme: { background: "#000", foreground: "#0f0", cursor: "#0f0" },
 *   });
 */
export class AgiRenderedTerminal {
  private connection: AgiTerminal;
  private xterm: Terminal;
  private fitAddon: FitAddon;
  private container: HTMLElement;
  private resizeObserver: ResizeObserver | null = null;

  constructor(options: RenderedTerminalOptions) {
    const el =
      typeof options.container === "string"
        ? document.querySelector<HTMLElement>(options.container)
        : options.container;

    if (!el) {
      throw new Error(`WorkAGI: container not found: ${options.container}`);
    }

    this.container = el;

    // Resolve theme — string preset or custom object
    const theme = resolveTheme(options.theme);

    // Create xterm.js instance
    this.xterm = new Terminal({
      fontSize: options.fontSize ?? 14,
      fontFamily:
        options.fontFamily ??
        "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Menlo, monospace",
      cursorStyle: options.cursorStyle ?? "block",
      cursorBlink: true,
      theme,
      allowProposedApi: true,
    });

    this.fitAddon = new FitAddon();
    this.xterm.loadAddon(this.fitAddon);
    this.xterm.open(this.container);

    // WebGL renderer
    if (options.webgl !== false) {
      try {
        this.xterm.loadAddon(new WebglAddon());
      } catch {
        // Fall back to canvas
      }
    }

    this.fitAddon.fit();

    // Connect to agiterm-server
    this.connection = new AgiTerminal({
      ...options,
      onOutput: (data) => {
        this.xterm.write(data);
        options.onOutput?.(data);
      },
      onConnect: () => {
        const dims = this.fitAddon.proposeDimensions();
        if (dims) {
          this.connection.resize(dims.cols, dims.rows);
        }
        options.onConnect?.();
      },
      onDisconnect: options.onDisconnect,
      onError: options.onError,
    });

    // Forward user keyboard input to PTY
    this.xterm.onData((data) => {
      this.connection.sendInput(data);
    });

    this.xterm.onBinary((data) => {
      const bytes = new Uint8Array(data.length);
      for (let i = 0; i < data.length; i++) {
        bytes[i] = data.charCodeAt(i);
      }
      this.connection.sendInputBytes(bytes);
    });

    // Notify server of terminal resize
    this.xterm.onResize(({ cols, rows }) => {
      this.connection.resize(cols, rows);
    });

    // Auto-fit on container resize
    this.resizeObserver = new ResizeObserver(() => {
      try {
        this.fitAddon.fit();
      } catch {
        // Ignore
      }
    });
    this.resizeObserver.observe(this.container);
  }

  get ws(): TerminalInstance {
    return this.connection;
  }

  get terminal(): Terminal {
    return this.xterm;
  }

  /** Update theme at runtime */
  setTheme(theme: "dark" | "light" | Record<string, string>): void {
    const resolved = resolveTheme(theme);
    this.xterm.options.theme = resolved;
    // Force full redraw so the WebGL renderer picks up the new palette
    this.xterm.refresh(0, this.xterm.rows - 1);
    // Update the container background to match (xterm only paints inside the
    // viewport element; the outer container keeps its old colour otherwise)
    this.container.style.backgroundColor = resolved.background ?? "";
  }

  write(data: string | Uint8Array): void {
    this.xterm.write(data);
  }

  focus(): void {
    this.xterm.focus();
  }

  fit(): void {
    this.fitAddon.fit();
  }

  dispose(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.xterm.dispose();
    this.connection.dispose();
  }
}
