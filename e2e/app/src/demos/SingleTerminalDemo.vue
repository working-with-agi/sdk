<script setup lang="ts">
import { ref, computed } from "vue";
import { AgiTerminal } from "@work-with-ai/vue";
import type { AgiApiClient, TerminalTheme, ToolInfo } from "@work-with-ai/sdk";

const props = defineProps<{
  api: AgiApiClient;
  endpoint: string;
  apiKey: string;
  tools: Record<string, ToolInfo>;
  theme: "dark" | "light" | TerminalTheme;
}>();

const sessionId = ref("");
const connected = ref(false);
const selectedTool = ref("");
const promptText = ref("");
const error = ref("");
const launching = ref(false);

// Sidebar state
const sidebarOpen = ref(true);
const sidebarTab = ref<"chat" | "agents" | "tasks">("chat");
const chatMessages = ref<{ id: number; role: "user" | "system"; text: string; time: string }[]>([]);
const chatInput = ref("");
let msgId = 0;

// Agent status
const agents = ref<{ id: string; role: string; tool: string; status: "running" | "idle" | "done" }[]>([]);

const availableTools = computed(() =>
  Object.entries(props.tools)
    .filter(([, info]) => info.available)
    .map(([name, info]) => ({ name, label: info.label }))
);

async function launchSession(tool: string) {
  if (launching.value) return;
  launching.value = true;
  error.value = "";
  selectedTool.value = tool;

  try {
    const session = await props.api.createSession({
      user_id: "demo-user",
      tool,
      sandbox: true,
      label: props.tools[tool]?.label ?? tool,
      prompt: promptText.value || undefined,
    });
    sessionId.value = session.session_id;
    addSystemMessage(`Session started: ${session.session_id}`);
  } catch (err: any) {
    error.value = err.message;
    selectedTool.value = "";
  } finally {
    launching.value = false;
  }
}

async function destroySession() {
  if (sessionId.value) {
    try { await props.api.destroySession(sessionId.value); } catch { /* ignore */ }
  }
  addSystemMessage("Session ended");
  sessionId.value = "";
  connected.value = false;
  selectedTool.value = "";
  agents.value = [];
}

function onConnected() {
  connected.value = true;
  addSystemMessage("Terminal connected");
}

function addSystemMessage(text: string) {
  chatMessages.value.push({
    id: ++msgId, role: "system", text,
    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  });
}

function sendChat() {
  const text = chatInput.value.trim();
  if (!text) return;
  chatMessages.value.push({
    id: ++msgId, role: "user", text,
    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  });
  chatInput.value = "";
  setTimeout(() => addSystemMessage(`Received: "${text}" (chat is a placeholder)`), 500);
}

async function addAgent(role: string) {
  if (!sessionId.value) return;
  try {
    const pane = await props.api.addPane(sessionId.value, { tool: "bash", role });
    agents.value.push({ id: pane.pane_id, role: pane.role || role, tool: pane.tool, status: "running" });
    addSystemMessage(`Agent "${role}" started (${pane.pane_id.slice(0, 12)})`);
  } catch (err: any) {
    addSystemMessage(`Failed to add agent: ${err.message}`);
  }
}

async function removeAgent(id: string) {
  if (!sessionId.value) return;
  try {
    await props.api.removePane(sessionId.value, id);
    agents.value = agents.value.filter((a) => a.id !== id);
    addSystemMessage(`Agent removed: ${id.slice(0, 12)}`);
  } catch (err: any) {
    addSystemMessage(`Failed: ${err.message}`);
  }
}

const ROLE_COLORS: Record<string, string> = {
  developer: "#9ece6a", reviewer: "#7aa2f7", tester: "#e0af68", architect: "#bb9af7",
};
</script>

<template>
  <div class="pilot-demo">
    <!-- Launcher -->
    <div v-if="!sessionId" class="launcher">
      <div class="launcher-hero">
        <h2>Pilot Mode</h2>
        <p>Main terminal front &amp; center, agents in the background, sidebar for chat &amp; status</p>
      </div>
      <div class="prompt-row">
        <input v-model="promptText" placeholder="Initial prompt (optional)" class="prompt-input"
          @keydown.enter="availableTools.length > 0 && launchSession(availableTools[0].name)" />
      </div>
      <div class="tool-grid">
        <button v-for="t in availableTools" :key="t.name" @click="launchSession(t.name)"
          :disabled="launching" class="tool-btn">{{ t.label }}</button>
      </div>
      <p v-if="error" class="error-text">{{ error }}</p>
    </div>

    <!-- Pilot layout -->
    <div v-else class="pilot-layout">
      <!-- Main terminal area -->
      <div class="pilot-main">
        <div class="pilot-header">
          <div class="header-left">
            <span class="status-dot" :class="connected ? 'green' : 'yellow'" />
            <span class="tool-name">{{ tools[selectedTool]?.label ?? selectedTool }}</span>
            <span class="session-label">{{ sessionId }}</span>
          </div>
          <div class="header-right">
            <button class="header-btn" @click="sidebarOpen = !sidebarOpen">
              {{ sidebarOpen ? "\u25C1 Hide" : "\u25B7 Sidebar" }}
            </button>
            <button class="header-btn close" @click="destroySession">End Session</button>
          </div>
        </div>
        <div class="pilot-terminal">
          <AgiTerminal :endpoint="endpoint" :api-key="apiKey" :session-id="sessionId"
            :theme="theme" :font-size="14" @connect="onConnected" @disconnect="connected = false" />
        </div>
        <div class="pilot-statusbar">
          <span class="sb-item"><span class="status-dot small" :class="connected ? 'green' : 'yellow'" /> {{ connected ? "connected" : "connecting..." }}</span>
          <span class="sb-item">{{ agents.length }} agent{{ agents.length !== 1 ? "s" : "" }}</span>
          <span class="sb-item right">{{ sessionId.slice(0, 16) }}</span>
        </div>
      </div>

      <!-- Sidebar -->
      <Transition name="slide">
        <aside v-if="sidebarOpen" class="pilot-sidebar">
          <div class="sidebar-header">
            <div class="sidebar-tabs">
              <button v-for="tab in (['chat', 'agents', 'tasks'] as const)" :key="tab"
                :class="['stab', { active: sidebarTab === tab }]" @click="sidebarTab = tab">
                {{ tab.charAt(0).toUpperCase() + tab.slice(1) }}
              </button>
            </div>
            <button class="sidebar-close" @click="sidebarOpen = false">&times;</button>
          </div>

          <!-- Chat -->
          <div v-if="sidebarTab === 'chat'" class="sidebar-body">
            <div class="chat-messages">
              <div v-if="chatMessages.length === 0" class="chat-empty">
                <p>Pilot Chat</p><span>Type a message to interact.</span>
              </div>
              <div v-for="msg in chatMessages" :key="msg.id" :class="['chat-msg', msg.role]">
                <span class="chat-text">{{ msg.text }}</span>
                <span class="chat-time">{{ msg.time }}</span>
              </div>
            </div>
            <div class="chat-input-area">
              <input v-model="chatInput" class="chat-input" placeholder="Message or /command..."
                @keydown.enter="sendChat" />
            </div>
          </div>

          <!-- Agents -->
          <div v-else-if="sidebarTab === 'agents'" class="sidebar-body">
            <div class="agents-actions">
              <button v-for="role in ['developer', 'reviewer', 'tester', 'architect']" :key="role"
                class="agent-add" @click="addAgent(role)">
                <span class="adot" :style="{ background: ROLE_COLORS[role] }" /> + {{ role }}
              </button>
            </div>
            <div class="agents-list">
              <div v-for="a in agents" :key="a.id" class="agent-item">
                <span class="adot" :style="{ background: ROLE_COLORS[a.role] || '#565f89' }" />
                <span class="agent-role">{{ a.role }}</span>
                <span class="agent-id">{{ a.id.slice(0, 8) }}</span>
                <span class="agent-status running">{{ a.status }}</span>
                <button class="agent-rm" @click="removeAgent(a.id)">&times;</button>
              </div>
              <div v-if="agents.length === 0" class="empty-state">No background agents.</div>
            </div>
          </div>

          <!-- Tasks -->
          <div v-else class="sidebar-body">
            <div class="empty-state">Task tracking coming soon.</div>
          </div>
        </aside>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.pilot-demo { height: 100%; display: flex; flex-direction: column; }

.launcher { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 24px; height: 100%; padding: 32px; }
.launcher-hero { text-align: center; }
.launcher-hero h2 { font-size: 24px; font-weight: 700; color: var(--accent); margin-bottom: 8px; }
.launcher-hero p { font-size: 14px; color: var(--text-muted); }
.prompt-row { width: 100%; max-width: 480px; }
.prompt-input { width: 100%; padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border); background: var(--bg-elevated); color: var(--text); font-size: 13px; outline: none; }
.prompt-input:focus { border-color: var(--accent); }
.tool-grid { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
.tool-btn { padding: 10px 20px; border-radius: 8px; border: none; background: var(--accent); color: var(--bg); font-weight: 600; font-size: 14px; cursor: pointer; transition: all 0.15s; }
.tool-btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
.tool-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.error-text { color: var(--error); font-size: 13px; }

/* Pilot layout */
.pilot-layout { display: flex; height: 100%; overflow: hidden; }
.pilot-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }

.pilot-header { display: flex; align-items: center; justify-content: space-between; padding: 0 12px; height: 36px; background: var(--bg-surface); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.header-left { display: flex; align-items: center; gap: 8px; }
.header-right { display: flex; gap: 6px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.small { width: 6px; height: 6px; }
.status-dot.green { background: var(--success); }
.status-dot.yellow { background: var(--warn); }
.tool-name { font-size: 13px; font-weight: 600; color: var(--accent); }
.session-label { font-size: 11px; color: var(--text-muted); font-family: var(--font-mono); }
.header-btn { padding: 4px 10px; border-radius: 4px; border: 1px solid var(--border); background: transparent; color: var(--text-muted); font-size: 11px; cursor: pointer; transition: all 0.15s; }
.header-btn:hover { color: var(--text); border-color: var(--text-muted); }
.header-btn.close:hover { background: var(--error); color: var(--bg); border-color: var(--error); }

.pilot-terminal { flex: 1; min-height: 0; overflow: hidden; }

.pilot-statusbar { display: flex; align-items: center; gap: 16px; padding: 3px 12px; height: 24px; background: var(--bg-surface); border-top: 1px solid var(--border); flex-shrink: 0; font-size: 11px; color: var(--text-muted); }
.sb-item { display: flex; align-items: center; gap: 4px; }
.sb-item.right { margin-left: auto; font-family: var(--font-mono); }

/* Sidebar */
.pilot-sidebar { width: 320px; flex-shrink: 0; display: flex; flex-direction: column; background: var(--bg-surface); border-left: 1px solid var(--border); height: 100%; }
.slide-enter-active, .slide-leave-active { transition: transform 0.2s ease, opacity 0.2s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); opacity: 0; }

.sidebar-header { display: flex; align-items: center; padding: 0 4px; height: 36px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.sidebar-tabs { display: flex; flex: 1; gap: 2px; }
.stab { background: none; border: none; color: var(--text-muted); font-size: 12px; padding: 6px 10px; cursor: pointer; border-radius: 4px; transition: all 0.15s; }
.stab:hover { color: var(--text); background: var(--bg-elevated); }
.stab.active { color: var(--accent); background: rgba(122, 162, 247, 0.1); }
.sidebar-close { background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 4px 8px; font-size: 16px; border-radius: 4px; }
.sidebar-close:hover { color: var(--text); }
.sidebar-body { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* Chat */
.chat-messages { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 6px; }
.chat-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); text-align: center; }
.chat-empty p { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.chat-empty span { font-size: 12px; }
.chat-msg { padding: 6px 10px; border-radius: 6px; font-size: 12px; line-height: 1.4; max-width: 90%; }
.chat-msg.user { align-self: flex-end; background: rgba(122, 162, 247, 0.15); color: var(--text); }
.chat-msg.system { align-self: flex-start; background: var(--bg-elevated); color: var(--text-muted); }
.chat-time { display: block; font-size: 10px; color: var(--text-muted); margin-top: 2px; opacity: 0.7; }
.chat-input-area { padding: 8px; border-top: 1px solid var(--border); }
.chat-input { width: 100%; padding: 8px 10px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg-elevated); color: var(--text); font-size: 12px; outline: none; }
.chat-input:focus { border-color: var(--accent); }

/* Agents */
.agents-actions { display: flex; flex-wrap: wrap; gap: 4px; padding: 8px; border-bottom: 1px solid var(--border); }
.agent-add { display: flex; align-items: center; gap: 4px; padding: 4px 10px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg-elevated); color: var(--text); font-size: 11px; cursor: pointer; transition: all 0.15s; }
.agent-add:hover { border-color: var(--accent); }
.adot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.agents-list { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 4px; }
.agent-item { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 4px; background: var(--bg-elevated); font-size: 12px; }
.agent-role { font-weight: 600; color: var(--text); }
.agent-id { font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); }
.agent-status { margin-left: auto; font-size: 10px; padding: 1px 6px; border-radius: 3px; }
.agent-status.running { background: rgba(158, 206, 106, 0.15); color: var(--success); }
.agent-rm { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 14px; padding: 0 4px; }
.agent-rm:hover { color: var(--error); }
.empty-state { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); font-size: 12px; }
</style>
