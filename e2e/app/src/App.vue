<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { AgiApiClient, THEME_PRESETS } from "@working-with-agi/sdk";
import type { TerminalTheme, ToolInfo } from "@working-with-agi/sdk";
import { AgiTerminal } from "@working-with-agi/vue";

const endpoint = window.location.origin;
const apiKey = "test-key-123";
const api = new AgiApiClient(endpoint, apiKey);

const tools = ref<Record<string, ToolInfo>>({});
const error = ref("");
const themeName = ref("light");
const theme = computed<TerminalTheme>(() => {
  const entry = THEME_PRESETS.find((t) => t.name === themeName.value);
  return entry?.theme ?? THEME_PRESETS[0].theme;
});
const sessionId = ref("");
const selectedTool = ref("");
const prompt = ref("");
const launching = ref(false);
const connected = ref(false);

// Agents that render their own dark UI (ANSI bg colors)
const DARK_UI_AGENTS = new Set(["claude", "codex", "gemini", "opencode"]);

onMounted(async () => {
  try {
    tools.value = await api.listTools();
    const first = Object.entries(tools.value).find(([name, info]) => info.available && name !== "bash");
    if (first) selectedTool.value = first[0];
  } catch (err: any) {
    error.value = err.message;
  }
});

// Auto-switch terminal theme when agent changes
watch(selectedTool, (tool) => {
  if (DARK_UI_AGENTS.has(tool)) {
    themeName.value = "dark";
  } else if (themeName.value === "dark") {
    themeName.value = "light";
  }
});

const availableTools = computed(() =>
  Object.entries(tools.value)
    .filter(([name, info]) => info.available && name !== "bash")
    .map(([name, info]) => ({ name, label: info.label })),
);

async function submit() {
  if (launching.value || !selectedTool.value) return;
  launching.value = true;
  error.value = "";
  try {
    const session = await api.createSession({
      user_id: "demo-user",
      tool: selectedTool.value,
      sandbox: true,
      label: tools.value[selectedTool.value]?.label ?? selectedTool.value,
      prompt: prompt.value || undefined,
    });
    sessionId.value = session.session_id;
  } catch (err: any) {
    error.value = err.message;
  } finally {
    launching.value = false;
  }
}

async function endSession() {
  if (sessionId.value) {
    try { await api.destroySession(sessionId.value); } catch { /* ignore */ }
  }
  sessionId.value = "";
  connected.value = false;
}

const darkThemes = THEME_PRESETS.filter((t) => t.dark);
const lightThemes = THEME_PRESETS.filter((t) => !t.dark);
</script>

<template>
  <div class="shell">
    <!-- Header -->
    <header class="header">
      <div class="header-left">
        <span class="logo">Work With AI</span>
        <span class="badge">Vue</span>
      </div>
      <div class="header-right">
        <select v-if="availableTools.length > 0" v-model="selectedTool" class="agent-select">
          <option v-for="t in availableTools" :key="t.name" :value="t.name">{{ t.label }}</option>
        </select>
        <select v-model="themeName" class="theme-select">
          <optgroup label="Dark">
            <option v-for="t in darkThemes" :key="t.name" :value="t.name">{{ t.label }}</option>
          </optgroup>
          <optgroup label="Light">
            <option v-for="t in lightThemes" :key="t.name" :value="t.name">{{ t.label }}</option>
          </optgroup>
        </select>
        <button v-if="sessionId" class="btn-end" @click="endSession">End Session</button>
      </div>
    </header>

    <!-- Content -->
    <main class="content">
      <!-- Welcome + input -->
      <template v-if="!sessionId">
        <div class="welcome">
          <h1>AI Terminal</h1>
          <p>What would you like to work on?</p>

          <!-- Chat-style input bar -->
          <div class="input-bar">
            <input
              v-model="prompt"
              class="chat-input"
              placeholder="Describe your task..."
              :disabled="launching || availableTools.length === 0"
              @keydown.enter="submit"
            />
            <button
              class="send-btn"
              :disabled="launching || availableTools.length === 0"
              @click="submit"
            >
              {{ launching ? '...' : 'Start' }}
            </button>
          </div>
          <p v-if="error" class="error-text">{{ error }}</p>
          <p v-if="availableTools.length === 0 && !error" class="hint">Connecting to server...</p>
        </div>
      </template>

      <!-- Terminal session -->
      <template v-else>
        <div class="terminal-wrap">
          <div class="terminal-bar">
            <span class="dot" :class="connected ? 'green' : 'yellow'" />
            <span class="bar-label">{{ tools[selectedTool]?.label ?? selectedTool }}</span>
            <span class="bar-session">{{ sessionId.slice(0, 12) }}</span>
          </div>
          <div class="terminal-body">
            <AgiTerminal
              :endpoint="endpoint"
              :api-key="apiKey"
              :session-id="sessionId"
              :theme="theme"
              :font-size="14"
              @connect="connected = true"
              @disconnect="connected = false"
            />
          </div>
        </div>
      </template>
    </main>
  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --font-sans: "Inter", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", Menlo, monospace;
}

body { background: #f8f9fa; }

.shell {
  width: 100vw; height: 100vh;
  display: flex; flex-direction: column;
  font-family: var(--font-sans);
  color: #24292e;
  background: #f8f9fa;
}

/* Header */
.header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px; height: 48px;
  background: #ffffff;
  border-bottom: 1px solid #e1e4e8;
  flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 10px; }
.header-right { display: flex; align-items: center; gap: 10px; }
.logo { font-size: 16px; font-weight: 700; letter-spacing: -0.02em; color: #24292e; }
.badge {
  font-size: 10px; font-weight: 600; text-transform: uppercase;
  padding: 2px 6px; border-radius: 4px;
  background: #eef2ff; color: #4f46e5;
}

/* Selects */
.theme-select, .agent-select {
  padding: 5px 10px; border-radius: 6px;
  border: 1px solid #d1d5db;
  background: #ffffff; color: #374151;
  font-size: 12px; font-family: var(--font-sans);
  cursor: pointer; outline: none;
}
.theme-select:focus, .agent-select:focus { border-color: #4f46e5; }

.btn-end {
  padding: 5px 12px; border-radius: 6px;
  border: 1px solid #fecaca;
  background: transparent; color: #dc2626;
  font-size: 12px; cursor: pointer; transition: all 0.15s;
}
.btn-end:hover { background: #dc2626; color: #ffffff; }

/* Content */
.content { flex: 1; min-height: 0; display: flex; flex-direction: column; }

/* Welcome */
.welcome {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 40px 20px; gap: 16px;
}
.welcome h1 { font-size: 32px; font-weight: 700; color: #111827; }
.welcome p { font-size: 14px; color: #6b7280; }

/* Chat-style input bar */
.input-bar {
  display: flex; align-items: center; gap: 0;
  width: 100%; max-width: 640px;
  border-radius: 12px; overflow: hidden;
  border: 1px solid #d1d5db;
  background: #ffffff;
  transition: border-color 0.15s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.input-bar:focus-within { border-color: #4f46e5; box-shadow: 0 0 0 3px rgba(79,70,229,0.1); }

.chat-input {
  flex: 1; padding: 12px 16px; border: none;
  background: transparent; color: #24292e;
  font-size: 14px; font-family: var(--font-sans);
  outline: none;
}
.chat-input::placeholder { color: #9ca3af; }
.chat-input:disabled { opacity: 0.5; }

.send-btn {
  padding: 12px 20px; border: none;
  background: #4f46e5; color: #ffffff;
  font-weight: 600; font-size: 13px;
  cursor: pointer; transition: all 0.15s;
}
.send-btn:hover { background: #4338ca; }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.error-text { color: #dc2626; font-size: 13px; }
.hint { color: #9ca3af; font-size: 14px; }

/* Terminal */
.terminal-wrap {
  flex: 1; min-height: 0; display: flex; flex-direction: column;
  margin: 8px; border-radius: 10px; overflow: hidden;
  border: 1px solid #e1e4e8;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.terminal-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 14px; height: 32px;
  background: #f6f8fa;
  border-bottom: 1px solid #e1e4e8;
  font-size: 12px; color: #57606a;
}
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot.green { background: #2da44e; }
.dot.yellow { background: #d4a72c; }
.bar-label { font-weight: 600; color: #24292e; }
.bar-session { opacity: 0.5; font-family: var(--font-mono); font-size: 11px; }
.terminal-body { flex: 1; min-height: 0; }
</style>
