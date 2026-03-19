import { useRef, useEffect, useImperativeHandle, forwardRef } from "react";
import { AgiRenderedTerminal } from "@working-with-agi/sdk";

export interface AgiTerminalProps {
  /** agisdk-server base URL */
  endpoint: string;
  /** API key */
  apiKey?: string;
  /** Session ID (from REST API createSession) */
  sessionId?: string;
  /** Theme — preset name or custom theme object */
  theme?: "dark" | "light" | Record<string, string>;
  /** Font size */
  fontSize?: number;
  /** Font family */
  fontFamily?: string;
  /** Cursor style */
  cursorStyle?: "block" | "underline" | "bar";
  /** Enable WebGL renderer */
  webgl?: boolean;
  /** Container class name */
  className?: string;
  /** Container style */
  style?: React.CSSProperties;
  /** PTY output callback */
  onOutput?: (data: Uint8Array) => void;
  /** WebSocket connected */
  onConnect?: () => void;
  /** WebSocket disconnected */
  onDisconnect?: () => void;
}

export interface AgiTerminalHandle {
  focus: () => void;
  fit: () => void;
  write: (data: string | Uint8Array) => void;
}

export const AgiTerminal = forwardRef<AgiTerminalHandle, AgiTerminalProps>(
  function AgiTerminal(
    {
      endpoint,
      apiKey,
      sessionId,
      theme = "dark",
      fontSize,
      fontFamily,
      cursorStyle,
      webgl,
      className,
      style,
      onOutput,
      onConnect,
      onDisconnect,
    },
    ref,
  ) {
    const containerRef = useRef<HTMLDivElement>(null);
    const terminalRef = useRef<AgiRenderedTerminal | null>(null);

    // Create / recreate terminal on connection-level prop changes
    useEffect(() => {
      if (!containerRef.current) return;

      terminalRef.current = new AgiRenderedTerminal({
        container: containerRef.current,
        endpoint,
        apiKey,
        sessionId,
        theme,
        fontSize,
        fontFamily,
        cursorStyle,
        webgl,
        onOutput,
        onConnect,
        onDisconnect,
      });

      return () => {
        terminalRef.current?.dispose();
        terminalRef.current = null;
      };
    }, [endpoint, apiKey, sessionId]);

    // Watch theme changes
    useEffect(() => {
      if (terminalRef.current && theme) {
        terminalRef.current.setTheme(theme);
      }
    }, [theme]);

    // Watch fontSize changes
    useEffect(() => {
      if (terminalRef.current && fontSize) {
        terminalRef.current.terminal.options.fontSize = fontSize;
        terminalRef.current.fit();
      }
    }, [fontSize]);

    // Expose imperative API via ref
    useImperativeHandle(ref, () => ({
      focus: () => terminalRef.current?.focus(),
      fit: () => terminalRef.current?.fit(),
      write: (data: string | Uint8Array) => terminalRef.current?.write(data),
    }));

    return (
      <div
        ref={containerRef}
        className={className}
        style={{ width: "100%", height: "100%", ...style }}
      />
    );
  },
);
