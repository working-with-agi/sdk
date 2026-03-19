import { useState, useEffect, useRef, useCallback } from "react";
import { AgiApiClient } from "@working-with-agi/sdk";
import type { TerminalTheme, ToolInfo } from "@working-with-agi/sdk";
import { AgiTerminal } from "@working-with-agi/react";
import type { AgiTerminalHandle } from "@working-with-agi/react";

const endpoint = window.location.origin;
const apiKey = "test-key-123";
const api = new AgiApiClient(endpoint, apiKey);

export function App() {
  const [tools, setTools] = useState<Record<string, ToolInfo>>({});
  const [sessionId, setSessionId] = useState("");
  const [selectedTool, setSelectedTool] = useState("");
  const [theme, setTheme] = useState<"dark" | "light" | TerminalTheme>("dark");
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [launching, setLaunching] = useState(false);
  const [prompt, setPrompt] = useState("");
  const termRef = useRef<AgiTerminalHandle>(null);

  useEffect(() => {
    api.listTools().then(setTools).catch((e) => setError(e.message));
  }, []);

  const launchSession = useCallback(
    async (tool: string) => {
      if (launching) return;
      setLaunching(true);
      setError("");
      setSelectedTool(tool);
      try {
        const session = await api.createSession({
          user_id: "demo-user",
          tool,
          sandbox: true,
          label: tools[tool]?.label ?? tool,
          prompt: prompt || undefined,
        });
        setSessionId(session.session_id);
      } catch (e: any) {
        setError(e.message);
        setSelectedTool("");
      } finally {
        setLaunching(false);
      }
    },
    [launching, tools],
  );

  const endSession = useCallback(async () => {
    if (sessionId) {
      try {
        await api.destroySession(sessionId);
      } catch {
        /* ignore */
      }
    }
    setSessionId("");
    setConnected(false);
    setSelectedTool("");
  }, [sessionId]);

  const addAgent = useCallback(
    async (role: string) => {
      if (!sessionId) return;
      try {
        await api.addPane(sessionId, { tool: "bash", role });
      } catch (e: any) {
        setError(e.message);
      }
    },
    [sessionId],
  );

  // Launcher
  if (!sessionId) {
    const available = Object.entries(tools).filter(([, info]) => info.available);
    return (
      <div style={styles.launcher}>
        <div style={styles.hero}>
          <h1 style={styles.title}>WorkWithAGI</h1>
          <p style={styles.subtitle}>React Demo — AI Terminal</p>
        </div>
        {available.length > 0 ? (
          <>
          <div style={styles.promptRow}>
            <input
              style={styles.promptInput}
              placeholder="Initial prompt (optional)"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && available.length > 0) {
                  launchSession(available[0][0]);
                }
              }}
            />
          </div>
          <div style={styles.toolGrid}>
            {available.map(([name, info]) => (
              <button
                key={name}
                style={styles.toolBtn}
                disabled={launching}
                onClick={() => launchSession(name)}
              >
                {info.label}
              </button>
            ))}
          </div>
          </>
        ) : (
          <p style={styles.hint}>
            {error
              ? `Server unavailable: ${error}`
              : "Connecting to server..."}
          </p>
        )}
        {error && available.length > 0 && <p style={styles.error}>{error}</p>}
      </div>
    );
  }

  // Terminal session
  return (
    <div style={styles.app}>
      <div style={styles.toolbar}>
        <span style={styles.brand}>WorkWithAGI</span>
        <span style={styles.sep} />
        <span style={{ ...styles.dot, background: connected ? "#9ece6a" : "#e0af68" }} />
        <span style={styles.toolName}>{tools[selectedTool]?.label ?? selectedTool}</span>
        <span style={styles.sessionLabel}>{sessionId.slice(0, 16)}</span>
        <span style={styles.sep} />
        {["developer", "reviewer", "tester"].map((role) => (
          <button key={role} style={styles.tb} onClick={() => addAgent(role)}>
            + {role}
          </button>
        ))}
        <span style={styles.sep} />
        <button style={styles.tb} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          {theme === "dark" ? "\u263E" : "\u2600"}
        </button>
        <button style={{ ...styles.tb, marginLeft: "auto" }} onClick={endSession}>
          End
        </button>
      </div>
      <div style={styles.terminal}>
        <AgiTerminal
          ref={termRef}
          endpoint={endpoint}
          apiKey={apiKey}
          sessionId={sessionId}
          theme={theme}
          fontSize={14}
          onConnect={() => setConnected(true)}
          onDisconnect={() => setConnected(false)}
        />
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  app: {
    width: "100vw",
    height: "100vh",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    fontFamily: '"Inter", system-ui, sans-serif',
    color: "#c0caf5",
  },
  launcher: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 24,
    height: "100vh",
    padding: 32,
    fontFamily: '"Inter", system-ui, sans-serif',
  },
  hero: { textAlign: "center" as const },
  title: { fontSize: 28, fontWeight: 700, color: "#7aa2f7", marginBottom: 8 },
  subtitle: { fontSize: 14, color: "#565f89" },
  toolGrid: { display: "flex", gap: 10, flexWrap: "wrap" as const, justifyContent: "center" },
  toolBtn: {
    padding: "10px 20px",
    borderRadius: 8,
    border: "none",
    background: "#7aa2f7",
    color: "#1a1b26",
    fontWeight: 600,
    fontSize: 14,
    cursor: "pointer",
  },
  error: { color: "#f7768e", fontSize: 13 },
  hint: { color: "#565f89", fontSize: 14 },
  promptRow: { width: "100%", maxWidth: 480 },
  promptInput: {
    width: "100%",
    padding: "10px 14px",
    borderRadius: 8,
    border: "1px solid #414868",
    background: "#24283b",
    color: "#c0caf5",
    fontSize: 13,
    outline: "none",
    boxSizing: "border-box" as const,
  },
  toolbar: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "0 12px",
    height: 36,
    background: "rgba(22, 22, 30, 0.85)",
    borderBottom: "1px solid #414868",
    flexShrink: 0,
    userSelect: "none" as const,
  },
  brand: { fontSize: 13, fontWeight: 700, color: "#7aa2f7" },
  sep: { width: 1, height: 18, background: "#414868" },
  dot: { width: 8, height: 8, borderRadius: "50%" },
  toolName: { fontSize: 13, fontWeight: 600, color: "#7aa2f7" },
  sessionLabel: {
    fontSize: 11,
    color: "#565f89",
    fontFamily: '"JetBrains Mono", "Fira Code", monospace',
  },
  tb: {
    padding: "3px 10px",
    borderRadius: 4,
    border: "1px solid #414868",
    background: "transparent",
    color: "#565f89",
    fontSize: 11,
    cursor: "pointer",
  },
  terminal: { flex: 1, minHeight: 0, overflow: "hidden" },
};
