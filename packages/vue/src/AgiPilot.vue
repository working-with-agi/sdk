<script setup lang="ts">
/**
 * AgiPilot — Standard WorkWithAGI terminal component.
 *
 * Layout:
 *   - Background: Sub-agent panes rendered via PaneLayout (server-driven)
 *   - Foreground: Main user terminal as a floating, draggable window
 *
 * The embedding application controls agents via REST API.
 * This component passively renders the result.
 */
import {
  ref,
  reactive,
  computed,
  watch,
  onMounted,
  onBeforeUnmount,
  type PropType,
} from "vue";
import { resolveTheme } from "@working-with-agi/sdk";
import type { TerminalTheme } from "@working-with-agi/sdk";
import { AgiTerminal } from "./AgiTerminal";
import PaneLayout from "./PaneLayout.vue";
import type { PaneNode, PaneTerminalHandle } from "./PaneLayout.vue";

const props = defineProps({
  /** agiterm-server base URL */
  endpoint: { type: String, required: true },
  /** API key */
  apiKey: { type: String, default: undefined },
  /** Main session ID (user-interactive terminal) */
  sessionId: { type: String, default: undefined },
  /** Theme preset or custom theme */
  theme: {
    type: [String, Object] as PropType<"dark" | "light" | TerminalTheme>,
    default: "dark",
  },
  /** Terminal font size */
  fontSize: { type: Number, default: 14 },
  /** Initial float window position */
  floatX: { type: Number, default: 80 },
  floatY: { type: Number, default: 60 },
  /** Initial float window size */
  floatWidth: { type: Number, default: 720 },
  floatHeight: { type: Number, default: 480 },
});

const emit = defineEmits<{
  (e: "connect"): void;
  (e: "disconnect"): void;
  (e: "pane-added", paneId: string, role?: string): void;
  (e: "pane-removed", paneId: string): void;
}>();

// ---------------------------------------------------------------------------
// Main terminal state
// ---------------------------------------------------------------------------

const mainConnected = ref(false);

// Float window state
const floatPos = ref({ x: props.floatX, y: props.floatY });
const floatSize = ref({ w: props.floatWidth, h: props.floatHeight });
const floatMinimized = ref(false);
const dragOffset = ref({ x: 0, y: 0 });
let dragging = false;

function onDragStart(e: MouseEvent) {
  dragging = true;
  dragOffset.value = {
    x: e.clientX - floatPos.value.x,
    y: e.clientY - floatPos.value.y,
  };
  const onMove = (ev: MouseEvent) => {
    if (dragging) {
      floatPos.value = {
        x: ev.clientX - dragOffset.value.x,
        y: ev.clientY - dragOffset.value.y,
      };
    }
  };
  const onUp = () => {
    dragging = false;
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  };
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}

// ---------------------------------------------------------------------------
// Background panes (sub-agents) — workspace WebSocket
// ---------------------------------------------------------------------------

const resolvedTheme = computed(() => resolveTheme(props.theme));
const layoutTree = ref<PaneNode | null>(null);
const connectionState = ref<"disconnected" | "connecting" | "connected">("disconnected");
const paneTerminals = reactive(new Map<string, PaneTerminalHandle>());
const activePaneId = ref<string | null>(null);
const zoomedPaneId = ref<string | null>(null);

let ws: WebSocket | null = null;
let pingInterval: ReturnType<typeof setInterval> | null = null;
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
let reconnectAttempts = 0;

function buildWsUrl(): string {
  const ep = props.endpoint.replace(/\/$/, "");
  const protocol = ep.startsWith("https") ? "wss:" : "ws:";
  const host = ep.replace(/^https?:\/\//, "");
  const params = new URLSearchParams();
  if (props.apiKey) params.set("api_key", props.apiKey);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return `${protocol}//${host}/ws/workspace/${props.sessionId}${qs}`;
}

function connectWorkspace() {
  if (!props.sessionId) return;
  if (ws) disconnectWorkspace();

  connectionState.value = "connecting";
  ws = new WebSocket(buildWsUrl());
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    connectionState.value = "connected";
    reconnectAttempts = 0;
    startPing();
  };

  ws.onclose = () => {
    connectionState.value = "disconnected";
    stopPing();
    scheduleReconnect();
  };

  ws.onerror = () => {};

  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      handleBinaryFrame(event.data);
    } else {
      handleControlMessage(event.data);
    }
  };
}

function disconnectWorkspace() {
  if (reconnectTimeout !== null) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }
  stopPing();
  ws?.close();
  ws = null;
  connectionState.value = "disconnected";
}

function scheduleReconnect() {
  if (!props.sessionId) return;
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
  reconnectAttempts++;
  reconnectTimeout = setTimeout(() => {
    reconnectTimeout = null;
    connectWorkspace();
  }, delay);
}

function startPing() {
  stopPing();
  pingInterval = setInterval(() => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, 25000);
}

function stopPing() {
  if (pingInterval !== null) {
    clearInterval(pingInterval);
    pingInterval = null;
  }
}

// Binary frame: [2 bytes pane ID length][pane ID][data]
function handleBinaryFrame(buffer: ArrayBuffer) {
  const view = new DataView(buffer);
  if (buffer.byteLength < 2) return;
  const paneIdLen = view.getUint16(0, false);
  if (buffer.byteLength < 2 + paneIdLen) return;

  const decoder = new TextDecoder();
  const paneId = decoder.decode(new Uint8Array(buffer, 2, paneIdLen));
  const data = new Uint8Array(buffer, 2 + paneIdLen);

  const handle = paneTerminals.get(paneId);
  if (handle) handle.terminal.write(data);
}

function handleControlMessage(raw: string) {
  let msg: Record<string, unknown>;
  try { msg = JSON.parse(raw); } catch { return; }

  switch (msg.type) {
    case "layout":
      layoutTree.value = msg.tree as PaneNode;
      break;
    case "layout_sync":
      layoutTree.value = msg.layout as PaneNode;
      break;
    case "pane_added":
      emit("pane-added", msg.pane_id as string, msg.role as string | undefined);
      break;
    case "pane_removed":
      if (zoomedPaneId.value === msg.pane_id) zoomedPaneId.value = null;
      emit("pane-removed", msg.pane_id as string);
      break;
    case "pane_output": {
      const paneId = msg.pane_id as string;
      const handle = paneTerminals.get(paneId);
      if (handle && typeof msg.data === "string") {
        const binary = Uint8Array.from(atob(msg.data), (c) => c.charCodeAt(0));
        handle.terminal.write(binary);
      }
      break;
    }
    case "pane_status":
    case "pane_exited":
    case "pong":
      // Informational — no action needed
      break;
    case "pane_active":
      activePaneId.value = (msg.pane_id as string) ?? null;
      break;
  }
}

function sendPaneInput(paneId: string, data: string) {
  if (ws?.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: "pane_input",
    pane_id: paneId,
    data: btoa(data),
  }));
}

function sendPaneResize(paneId: string, cols: number, rows: number) {
  if (ws?.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: "pane_resize", pane_id: paneId, cols, rows }));
}

function onTerminalCreated(paneId: string, handle: PaneTerminalHandle) {
  paneTerminals.set(paneId, handle);
  handle.terminal.onData((data: string) => sendPaneInput(paneId, data));
  handle.terminal.onResize(({ cols, rows }: { cols: number; rows: number }) => sendPaneResize(paneId, cols, rows));
  const dims = handle.fitAddon.proposeDimensions();
  if (dims) sendPaneResize(paneId, dims.cols, dims.rows);
}

function onTerminalDestroyed(paneId: string) {
  paneTerminals.delete(paneId);
}

function onPaneClick(paneId: string) {
  activePaneId.value = paneId;
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "pane_focus", pane_id: paneId }));
  }
}

function onPaneZoom(paneId: string) {
  zoomedPaneId.value = zoomedPaneId.value === paneId ? null : paneId;
}

// Active marking
const layoutTreeWithActive = computed(() => {
  if (!layoutTree.value) return null;
  return markActive(layoutTree.value, activePaneId.value);
});

function markActive(node: PaneNode, activeId: string | null): PaneNode {
  if (node.type === "leaf" || !node.children) return { ...node, active: node.pane_id === activeId };
  return {
    ...node,
    children: [markActive(node.children[0], activeId), markActive(node.children[1], activeId)],
  };
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  if (props.sessionId) connectWorkspace();
});

onBeforeUnmount(() => {
  disconnectWorkspace();
});

watch(() => props.sessionId, (newId, oldId) => {
  if (newId !== oldId) {
    disconnectWorkspace();
    layoutTree.value = null;
    reconnectAttempts = 0;
    if (newId) connectWorkspace();
  }
});

watch(resolvedTheme, (t) => {
  for (const h of paneTerminals.values()) {
    h.terminal.options.theme = t;
    h.terminal.refresh(0, h.terminal.rows - 1);
  }
});

// ---------------------------------------------------------------------------
// Expose
// ---------------------------------------------------------------------------

defineExpose({
  connectionState,
  layoutTree,
  mainConnected,
  reconnect: () => { disconnectWorkspace(); reconnectAttempts = 0; connectWorkspace(); },
  fitAll: () => { for (const h of paneTerminals.values()) h.fitAddon.fit(); },
});
</script>

<template>
  <div class="agi-pilot" :style="{ background: resolvedTheme.background ?? '#1a1b26' }">
    <!-- Background: sub-agent panes -->
    <div class="pilot-bg">
      <div v-if="!layoutTreeWithActive" class="pilot-bg-empty"
        :style="{ color: resolvedTheme.foreground ?? '#565f89' }">
        <span v-if="!sessionId">Waiting for session...</span>
        <span v-else>No agents running</span>
      </div>
      <PaneLayout
        v-else
        :node="layoutTreeWithActive"
        :theme="resolvedTheme"
        :font-size="fontSize"
        :zoomed-pane-id="zoomedPaneId"
        @terminal-created="onTerminalCreated"
        @terminal-destroyed="onTerminalDestroyed"
        @pane-click="onPaneClick"
        @pane-zoom="onPaneZoom"
      />
    </div>

    <!-- Foreground: floating main terminal -->
    <div
      v-if="sessionId"
      class="pilot-float"
      :style="{
        left: floatPos.x + 'px',
        top: floatPos.y + 'px',
        width: floatSize.w + 'px',
        height: floatMinimized ? '36px' : floatSize.h + 'px',
        background: resolvedTheme.background ?? '#1a1b26',
      }"
    >
      <!-- Title bar -->
      <div class="float-titlebar" @mousedown="onDragStart">
        <div class="float-dots">
          <div class="fdot close" @click.stop="floatMinimized = !floatMinimized" />
          <div class="fdot minimize" @click.stop="floatMinimized = !floatMinimized" />
          <div class="fdot zoom" />
        </div>
        <span class="float-label">Main Terminal</span>
        <span class="float-status" :class="mainConnected ? 'on' : 'off'">
          {{ mainConnected ? "connected" : "connecting..." }}
        </span>
      </div>

      <!-- Terminal body -->
      <div v-show="!floatMinimized" class="float-body">
        <AgiTerminal
          :endpoint="endpoint"
          :api-key="apiKey"
          :session-id="sessionId"
          :theme="theme"
          :font-size="fontSize"
          @connect="() => { mainConnected = true; emit('connect'); }"
          @disconnect="() => { mainConnected = false; emit('disconnect'); }"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.agi-pilot {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* Background panes */
.pilot-bg {
  position: absolute;
  inset: 0;
}

.pilot-bg-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  font-size: 14px;
  opacity: 0.5;
}

/* Floating main terminal */
.pilot-float {
  position: absolute;
  background: #1a1b26;
  border: 1px solid #414868;
  border-radius: 10px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.6);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 100;
  transition: height 0.2s ease;
}

.float-titlebar {
  display: flex;
  align-items: center;
  padding: 0 10px;
  height: 36px;
  background: #24283b;
  cursor: move;
  flex-shrink: 0;
  user-select: none;
  border-bottom: 1px solid #414868;
  gap: 8px;
}

.float-dots {
  display: flex;
  gap: 7px;
  margin-right: 4px;
}

.fdot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  cursor: pointer;
}

.fdot.close { background: #f7768e; }
.fdot.minimize { background: #e0af68; }
.fdot.zoom { background: #9ece6a; cursor: default; }

.float-label {
  font-size: 12px;
  font-weight: 600;
  color: #7aa2f7;
}

.float-status {
  font-size: 10px;
}

.float-status::before { content: "\25CF "; }
.float-status.on { color: #9ece6a; }
.float-status.off { color: #e0af68; }

.float-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
