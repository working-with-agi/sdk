import { useState, useEffect, useRef, useCallback } from "react";
import { AgiApiClient, THEME_PRESETS } from "@work-with-ai/sdk";
import type { TerminalTheme, ToolInfo } from "@work-with-ai/sdk";
import { AgiTerminal } from "@work-with-ai/react";
import type { AgiTerminalHandle } from "@work-with-ai/react";

const endpoint = window.location.origin;
const apiKey = "test-key-123";
const api = new AgiApiClient(endpoint, apiKey);

const darkThemes = THEME_PRESETS.filter((t) => t.dark);
const lightThemes = THEME_PRESETS.filter((t) => !t.dark);
const DARK_UI_AGENTS = new Set(["claude", "codex", "gemini", "opencode"]);

export function App() {
  const [tools, setTools] = useState<Record<string, ToolInfo>>({});
  const [sessionId, setSessionId] = useState("");
  const [selectedTool, setSelectedTool] = useState("");
  const [themeName, setThemeName] = useState("light");
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [launching, setLaunching] = useState(false);
  const [prompt, setPrompt] = useState("");
  const termRef = useRef<AgiTerminalHandle>(null);

  const theme: TerminalTheme = (THEME_PRESETS.find((t) => t.name === themeName) ?? THEME_PRESETS[0]).theme;

  useEffect(() => {
    api.listTools().then((t) => {
      setTools(t);
      const first = Object.entries(t).find(([name, info]) => info.available && name !== "bash");
      if (first) {
        setSelectedTool(first[0]);
        if (DARK_UI_AGENTS.has(first[0])) setThemeName("dark");
      }
    }).catch((e) => setError(e.message));
  }, []);

  // Auto-switch terminal theme when agent changes
  useEffect(() => {
    if (DARK_UI_AGENTS.has(selectedTool)) {
      setThemeName("dark");
    } else if (themeName === "dark") {
      setThemeName("light");
    }
  }, [selectedTool]);

  const available = Object.entries(tools).filter(([name, info]) => info.available && name !== "bash");

  const submit = useCallback(async () => {
    if (launching || !selectedTool) return;
    setLaunching(true);
    setError("");
    try {
      const session = await api.createSession({
        user_id: "demo-user",
        tool: selectedTool,
        sandbox: true,
        label: tools[selectedTool]?.label ?? selectedTool,
        prompt: prompt || undefined,
      });
      setSessionId(session.session_id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLaunching(false);
    }
  }, [launching, selectedTool, tools, prompt]);

  const endSession = useCallback(async () => {
    if (sessionId) {
      try { await api.destroySession(sessionId); } catch { /* ignore */ }
    }
    setSessionId("");
    setConnected(false);
  }, [sessionId]);

  return (
    <div className="shell">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <span className="logo">Work With AI</span>
          <span className="badge">React</span>
        </div>
        <div className="header-right">
          {available.length > 0 && (
            <select
              className="agent-select"
              value={selectedTool}
              onChange={(e) => setSelectedTool(e.target.value)}
            >
              {available.map(([name, info]) => (
                <option key={name} value={name}>{info.label}</option>
              ))}
            </select>
          )}
          <select
            className="theme-select"
            value={themeName}
            onChange={(e) => setThemeName(e.target.value)}
          >
            <optgroup label="Dark">
              {darkThemes.map((t) => (
                <option key={t.name} value={t.name}>{t.label}</option>
              ))}
            </optgroup>
            <optgroup label="Light">
              {lightThemes.map((t) => (
                <option key={t.name} value={t.name}>{t.label}</option>
              ))}
            </optgroup>
          </select>
          {sessionId && (
            <button className="btn-end" onClick={endSession}>End Session</button>
          )}
        </div>
      </header>

      {/* Content */}
      <main className="content">
        {!sessionId ? (
          <div className="welcome">
            <h1>AI Terminal</h1>
            <p>What would you like to work on?</p>

            <div className="input-bar">
              <input
                className="chat-input"
                placeholder="Describe your task..."
                disabled={launching || available.length === 0}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
              />
              <button
                className="send-btn"
                disabled={launching || available.length === 0}
                onClick={submit}
              >
                {launching ? "..." : "Start"}
              </button>
            </div>
            {error && <p className="error-text">{error}</p>}
            {available.length === 0 && !error && <p className="hint">Connecting to server...</p>}
          </div>
        ) : (
          <div className="terminal-wrap">
            <div className="terminal-bar">
              <span className={`dot ${connected ? "green" : "yellow"}`} />
              <span className="bar-label">{tools[selectedTool]?.label ?? selectedTool}</span>
              <span className="bar-session">{sessionId.slice(0, 12)}</span>
            </div>
            <div className="terminal-body">
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
        )}
      </main>
    </div>
  );
}
