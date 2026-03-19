<script setup lang="ts">
import { ref, onMounted } from "vue";
import { AgiApiClient } from "@working-with-agi/sdk";
import type { TerminalTheme, ToolInfo } from "@working-with-agi/sdk";
import { AgiPilot } from "@working-with-agi/vue";

const endpoint = window.location.origin;
const apiKey = "test-key-123";
const api = new AgiApiClient(endpoint, apiKey);

const tools = ref<Record<string, ToolInfo>>({});
const error = ref("");
const theme = ref<"dark" | "light" | TerminalTheme>("dark");
const sessionId = ref("");
const selectedTool = ref("");
const launching = ref(false);

onMounted(async () => {
  try {
    tools.value = await api.listTools();
  } catch (err: any) {
    error.value = err.message;
  }
});

async function launchSession(tool: string) {
  if (launching.value) return;
  launching.value = true;
  error.value = "";
  selectedTool.value = tool;
  try {
    const session = await api.createSession({
      user_id: "demo-user",
      tool,
      sandbox: true,
      label: tools.value[tool]?.label ?? tool,
    });
    sessionId.value = session.session_id;
  } catch (err: any) {
    error.value = err.message;
    selectedTool.value = "";
  } finally {
    launching.value = false;
  }
}

async function addAgent(role: string) {
  if (!sessionId.value) return;
  try {
    await api.addPane(sessionId.value, { tool: "bash", role });
  } catch (err: any) {
    error.value = err.message;
  }
}

async function endSession() {
  if (sessionId.value) {
    try { await api.destroySession(sessionId.value); } catch { /* ignore */ }
  }
  sessionId.value = "";
  selectedTool.value = "";
}

function toggleTheme() {
  theme.value = theme.value === "dark" ? "light" : "dark";
}

const availableTools = Object.entries;
</script>

<template>
  <div class="app">
    <!-- Pilot mode (with session) -->
    <template v-if="sessionId">
      <!-- Toolbar overlaid at top -->
      <div class="toolbar">
        <span class="toolbar-brand">WorkWithAGI</span>
        <span class="toolbar-sep" />
        <button class="tb" @click="addAgent('developer')">+ Developer</button>
        <button class="tb" @click="addAgent('reviewer')">+ Reviewer</button>
        <button class="tb" @click="addAgent('tester')">+ Tester</button>
        <span class="toolbar-sep" />
        <button class="tb" @click="toggleTheme">{{ theme === "dark" ? "\u263E" : "\u2600" }}</button>
        <button class="tb end" @click="endSession">End</button>
      </div>

      <div class="pilot-area">
        <AgiPilot
          :endpoint="endpoint"
          :api-key="apiKey"
          :session-id="sessionId"
          :theme="theme"
          :font-size="14"
          :float-x="120"
          :float-y="60"
          :float-width="780"
          :float-height="460"
        />
      </div>
    </template>

    <!-- Launcher (no session) -->
    <template v-else>
      <div class="launcher">
        <div class="hero">
          <h1>WorkWithAGI</h1>
          <p>Pilot Mode — main terminal floats over background agent panes</p>
        </div>
        <div class="tool-grid">
          <button
            v-for="(info, name) in tools" :key="name"
            :disabled="!info.available || launching"
            @click="launchSession(name as string)"
            :class="['tool-btn', { available: info.available }]"
          >
            {{ info.label }}
          </button>
        </div>
        <p v-if="error" class="error-text">{{ error }}</p>
      </div>
    </template>
  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --bg: #1a1b26; --bg-surface: #16161e; --bg-elevated: #24283b;
  --border: #414868; --text: #c0caf5; --text-muted: #565f89;
  --accent: #7aa2f7; --success: #9ece6a; --warn: #e0af68; --error: #f7768e;
  --font-sans: "Inter", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", Menlo, monospace;
}

body { background: var(--bg); color: var(--text); font-family: var(--font-sans); }

.app { width: 100vw; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

/* Toolbar */
.toolbar {
  display: flex; align-items: center; gap: 6px;
  padding: 0 12px; height: 36px;
  background: rgba(22, 22, 30, 0.85); backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
  z-index: 200; flex-shrink: 0; user-select: none;
}
.toolbar-brand { font-size: 13px; font-weight: 700; color: var(--accent); }
.toolbar-sep { width: 1px; height: 18px; background: var(--border); }
.tb {
  padding: 3px 10px; border-radius: 4px; border: 1px solid var(--border);
  background: transparent; color: var(--text-muted); font-size: 11px;
  cursor: pointer; transition: all 0.15s;
}
.tb:hover { color: var(--text); border-color: var(--text-muted); }
.tb.end { margin-left: auto; }
.tb.end:hover { background: var(--error); color: var(--bg); border-color: var(--error); }

.pilot-area { flex: 1; min-height: 0; position: relative; }

/* Launcher */
.launcher {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 24px; height: 100%; padding: 32px;
}
.hero { text-align: center; }
.hero h1 { font-size: 28px; font-weight: 700; color: var(--accent); margin-bottom: 8px; }
.hero p { font-size: 14px; color: var(--text-muted); }
.tool-grid { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
.tool-btn {
  padding: 10px 20px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--bg-elevated); color: var(--text-muted); font-weight: 600;
  font-size: 14px; cursor: not-allowed; transition: all 0.15s;
}
.tool-btn.available {
  background: var(--accent); color: var(--bg); border-color: var(--accent); cursor: pointer;
}
.tool-btn.available:hover { filter: brightness(1.1); transform: translateY(-1px); }
.error-text { color: var(--error); font-size: 13px; }
</style>
