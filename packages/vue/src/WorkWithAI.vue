<script setup lang="ts">
/**
 * WorkWithAI — Passive display container for multi-pane AI agent terminals.
 *
 * Connects to an agiterm-server via WebSocket and renders whatever pane layout
 * the server dictates. The embedding application controls which agents run via
 * the REST API; this component simply visualizes the result.
 *
 * Layout is a binary tree of hsplit/vsplit nodes with terminal leaves.
 * Each leaf pane renders an xterm.js terminal with a role badge.
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
import PaneLayout from "./PaneLayout.vue";
import type { PaneNode, PaneTerminalHandle } from "./PaneLayout.vue";

// Re-export PaneNode for consumers
export type { PaneNode };

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

const props = defineProps({
  /** agiterm-server base URL (e.g. "https://your-server:8600") */
  endpoint: {
    type: String,
    required: true,
  },
  /** API key for authentication */
  apiKey: {
    type: String,
    default: undefined,
  },
  /** Session ID to connect to. If omitted, workspace waits for it. */
  sessionId: {
    type: String,
    default: undefined,
  },
  /** Theme preset or custom theme object */
  theme: {
    type: [String, Object] as PropType<"dark" | "light" | TerminalTheme>,
    default: "dark",
  },
  /** Show sidebar (Chat panel) */
  sidebar: {
    type: Boolean,
    default: false,
  },
  /** Workspace title displayed in the header */
  title: {
    type: String,
    default: undefined,
  },
  /** Terminal font size */
  fontSize: {
    type: Number,
    default: 14,
  },
  /** Show the status bar at the bottom */
  showStatusBar: {
    type: Boolean,
    default: true,
  },
});

// ---------------------------------------------------------------------------
// Emits
// ---------------------------------------------------------------------------

const emit = defineEmits<{
  (e: "connect"): void;
  (e: "disconnect"): void;
  (e: "pane-added", paneId: string, role?: string): void;
  (e: "pane-removed", paneId: string): void;
  (e: "fullscreen-change", isFullscreen: boolean): void;
}>();

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const resolvedTheme = computed(() => resolveTheme(props.theme));

/** Current pane layout tree — entirely server-driven */
const layoutTree = ref<PaneNode | null>(null);

/** Connection status */
const connectionState = ref<"disconnected" | "connecting" | "connected">(
  "disconnected",
);

/** Pane count for status bar */
const paneCount = ref(0);

/** Active (focused) pane ID */
const activePaneId = ref<string | null>(null);

/** Zoomed pane ID (null = normal view) */
const zoomedPaneId = ref<string | null>(null);

/** Fullscreen state */
const isFullscreen = ref(false);

/** Map of pane ID -> terminal handle for writing data */
const paneTerminals = reactive(new Map<string, PaneTerminalHandle>());

/** WebSocket instance */
let ws: WebSocket | null = null;

/** Ping interval handle */
let pingInterval: ReturnType<typeof setInterval> | null = null;

/** Reconnect timeout handle */
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

/** Reconnect attempt counter */
let reconnectAttempts = 0;

/** Maximum reconnect delay in ms */
const MAX_RECONNECT_DELAY = 30000;

/** Workspace root element ref */
const workspaceRef = ref<HTMLElement | null>(null);

// ---------------------------------------------------------------------------
// WebSocket connection
// ---------------------------------------------------------------------------

function buildWsUrl(): string {
  const endpoint = props.endpoint.replace(/\/$/, "");
  const protocol = endpoint.startsWith("https") ? "wss:" : "ws:";
  const host = endpoint.replace(/^https?:\/\//, "");
  const sessionId = props.sessionId ?? "";

  const params = new URLSearchParams();
  if (props.apiKey) {
    params.set("api_key", props.apiKey);
  }
  const qs = params.toString() ? `?${params.toString()}` : "";

  return `${protocol}//${host}/ws/workspace/${sessionId}${qs}`;
}

function connect() {
  if (!props.sessionId) return;
  if (ws) disconnect();

  connectionState.value = "connecting";

  const url = buildWsUrl();
  ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    connectionState.value = "connected";
    reconnectAttempts = 0;
    emit("connect");
    startPing();
  };

  ws.onclose = () => {
    connectionState.value = "disconnected";
    stopPing();
    emit("disconnect");
    scheduleReconnect();
  };

  ws.onerror = () => {
    // onclose will fire after onerror
  };

  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      handleBinaryFrame(event.data);
    } else {
      handleControlMessage(event.data);
    }
  };
}

function disconnect() {
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
  const delay = Math.min(
    1000 * Math.pow(2, reconnectAttempts),
    MAX_RECONNECT_DELAY,
  );
  reconnectAttempts++;
  reconnectTimeout = setTimeout(() => {
    reconnectTimeout = null;
    connect();
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

// ---------------------------------------------------------------------------
// Message handling
// ---------------------------------------------------------------------------

/**
 * Binary frame protocol:
 *   First 2 bytes: pane ID length (uint16 big-endian)
 *   Next N bytes: pane ID (UTF-8)
 *   Remaining bytes: PTY output data
 */
function handleBinaryFrame(buffer: ArrayBuffer) {
  const view = new DataView(buffer);
  if (buffer.byteLength < 2) return;

  const paneIdLen = view.getUint16(0, false);
  if (buffer.byteLength < 2 + paneIdLen) return;

  const decoder = new TextDecoder();
  const paneId = decoder.decode(
    new Uint8Array(buffer, 2, paneIdLen),
  );
  const data = new Uint8Array(buffer, 2 + paneIdLen);

  const handle = paneTerminals.get(paneId);
  if (handle) {
    handle.terminal.write(data);
  }
}

function handleControlMessage(raw: string) {
  let msg: Record<string, unknown>;
  try {
    msg = JSON.parse(raw);
  } catch {
    return; // Ignore malformed messages
  }

  switch (msg.type) {
    case "layout":
      handleLayoutUpdate(msg.tree as PaneNode);
      break;
    case "layout_sync":
      handleLayoutUpdate(msg.layout as PaneNode);
      break;

    case "pane_added":
      handlePaneAdded(msg as { type: string; pane_id: string; role?: string });
      break;

    case "pane_removed":
      handlePaneRemoved(msg as { type: string; pane_id: string });
      break;

    case "pane_active":
      activePaneId.value = (msg.pane_id as string) ?? null;
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
      // Informational — no action needed yet
      break;

    case "pong":
      // Keepalive response — no action needed
      break;

    case "error":
      console.warn("[WorkWithAI] Server error:", msg.message);
      break;
  }
}

function handleLayoutUpdate(tree: PaneNode) {
  layoutTree.value = tree;
  paneCount.value = countLeaves(tree);
}

function handlePaneAdded(msg: { pane_id: string; role?: string }) {
  emit("pane-added", msg.pane_id, msg.role);
}

function handlePaneRemoved(msg: { pane_id: string }) {
  // If zoomed pane was removed, exit zoom
  if (zoomedPaneId.value === msg.pane_id) {
    zoomedPaneId.value = null;
  }
  emit("pane-removed", msg.pane_id);
}

function countLeaves(node: PaneNode): number {
  if (node.type === "leaf" || !node.children) return 1;
  return node.children.reduce(
    (sum, child) => sum + countLeaves(child),
    0,
  );
}

// ---------------------------------------------------------------------------
// Send input to a pane's PTY
// ---------------------------------------------------------------------------

function sendInput(paneId: string, data: string) {
  if (ws?.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: "pane_input",
    pane_id: paneId,
    data: btoa(data),
  }));
}

function sendResize(paneId: string, cols: number, rows: number) {
  if (ws?.readyState !== WebSocket.OPEN) return;
  ws.send(
    JSON.stringify({
      type: "pane_resize",
      pane_id: paneId,
      cols,
      rows,
    }),
  );
}

// ---------------------------------------------------------------------------
// Terminal lifecycle callbacks from PaneLayout
// ---------------------------------------------------------------------------

function onTerminalCreated(paneId: string, handle: PaneTerminalHandle) {
  paneTerminals.set(paneId, handle);

  // Forward user keyboard input to server
  handle.terminal.onData((data: string) => {
    sendInput(paneId, data);
  });

  // Forward resize events
  handle.terminal.onResize(({ cols, rows }: { cols: number; rows: number }) => {
    sendResize(paneId, cols, rows);
  });

  // Report initial dimensions
  const dims = handle.fitAddon.proposeDimensions();
  if (dims) {
    sendResize(paneId, dims.cols, dims.rows);
  }
}

function onTerminalDestroyed(paneId: string) {
  paneTerminals.delete(paneId);
}

// ---------------------------------------------------------------------------
// Pane interactions
// ---------------------------------------------------------------------------

function onPaneClick(paneId: string) {
  activePaneId.value = paneId;
  // Notify server of focus change
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "pane_focus", pane_id: paneId }));
  }
}

function onPaneZoom(paneId: string) {
  zoomedPaneId.value =
    zoomedPaneId.value === paneId ? null : paneId;
}

// ---------------------------------------------------------------------------
// Fullscreen
// ---------------------------------------------------------------------------

function toggleFullscreen() {
  if (!workspaceRef.value) return;

  if (!document.fullscreenElement) {
    workspaceRef.value.requestFullscreen().then(() => {
      isFullscreen.value = true;
      emit("fullscreen-change", true);
    }).catch(() => {
      // Fullscreen denied by browser
    });
  } else {
    document.exitFullscreen().then(() => {
      isFullscreen.value = false;
      emit("fullscreen-change", false);
    }).catch(() => {
      // Ignore
    });
  }
}

function onFullscreenChange() {
  const fs = !!document.fullscreenElement;
  if (isFullscreen.value !== fs) {
    isFullscreen.value = fs;
    emit("fullscreen-change", fs);
  }
}

// ---------------------------------------------------------------------------
// Active pane marking on layout tree
// ---------------------------------------------------------------------------

const layoutTreeWithActive = computed(() => {
  if (!layoutTree.value) return null;
  return markActive(layoutTree.value, activePaneId.value);
});

function markActive(node: PaneNode, activeId: string | null): PaneNode {
  if (node.type === "leaf" || !node.children) {
    return { ...node, active: node.pane_id === activeId };
  }
  return {
    ...node,
    children: [
      markActive(node.children[0], activeId),
      markActive(node.children[1], activeId),
    ],
  };
}

// ---------------------------------------------------------------------------
// Connection status indicator color
// ---------------------------------------------------------------------------

const statusColor = computed(() => {
  switch (connectionState.value) {
    case "connected":
      return "#9ece6a";
    case "connecting":
      return "#e0af68";
    case "disconnected":
      return "#f7768e";
  }
});

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  document.addEventListener("fullscreenchange", onFullscreenChange);
  if (props.sessionId) {
    connect();
  }
});

onBeforeUnmount(() => {
  document.removeEventListener("fullscreenchange", onFullscreenChange);
  disconnect();
});

// Reconnect when sessionId changes
watch(
  () => props.sessionId,
  (newId, oldId) => {
    if (newId !== oldId) {
      disconnect();
      layoutTree.value = null;
      paneCount.value = 0;
      zoomedPaneId.value = null;
      reconnectAttempts = 0;
      if (newId) {
        connect();
      }
    }
  },
);

// Update theme on all active terminals
watch(resolvedTheme, (newTheme) => {
  for (const handle of paneTerminals.values()) {
    handle.terminal.options.theme = newTheme;
  }
});

// Update font size on all active terminals
watch(
  () => props.fontSize,
  (newSize) => {
    for (const handle of paneTerminals.values()) {
      handle.terminal.options.fontSize = newSize;
      handle.fitAddon.fit();
    }
  },
);

// ---------------------------------------------------------------------------
// Expose public API
// ---------------------------------------------------------------------------

defineExpose({
  /** Manually trigger reconnection */
  reconnect: () => {
    disconnect();
    reconnectAttempts = 0;
    connect();
  },
  /** Get current connection state */
  connectionState,
  /** Get the current layout tree */
  layoutTree,
  /** Fit all terminal panes to their containers */
  fitAll: () => {
    for (const handle of paneTerminals.values()) {
      handle.fitAddon.fit();
    }
  },
});
</script>

<template>
  <div
    ref="workspaceRef"
    :style="{
      display: 'flex',
      flexDirection: 'column',
      width: '100%',
      height: '100%',
      background: resolvedTheme.background ?? '#1a1b26',
      color: resolvedTheme.foreground ?? '#c0caf5',
      fontFamily:
        '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      overflow: 'hidden',
      position: 'relative',
    }"
  >
    <!-- Header bar -->
    <div
      v-if="title"
      :style="{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '6px 12px',
        background: '#16161e',
        borderBottom: '1px solid #24283b',
        fontSize: '13px',
        fontWeight: 600,
        flexShrink: 0,
        userSelect: 'none',
      }"
    >
      <span :style="{ color: '#c0caf5' }">{{ title }}</span>
      <div :style="{ display: 'flex', alignItems: 'center', gap: '8px' }">
        <span
          :style="{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '11px',
            color: '#565f89',
          }"
        >
          <span
            :style="{
              display: 'inline-block',
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: statusColor,
            }"
          />
          {{ connectionState }}
        </span>
        <button
          :style="{
            background: 'none',
            border: '1px solid #24283b',
            borderRadius: '3px',
            color: '#565f89',
            cursor: 'pointer',
            padding: '2px 6px',
            fontSize: '11px',
            lineHeight: 1,
          }"
          :title="isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'"
          @click="toggleFullscreen"
        >
          {{ isFullscreen ? "\u2716" : "\u26f6" }}
        </button>
      </div>
    </div>

    <!-- Main content area -->
    <div
      :style="{
        display: 'flex',
        flex: '1 1 0%',
        minHeight: 0,
        overflow: 'hidden',
      }"
    >
      <!-- Pane layout area -->
      <div
        :style="{
          flex: '1 1 0%',
          minWidth: 0,
          minHeight: 0,
          padding: '2px',
          overflow: 'hidden',
        }"
      >
        <!-- Waiting state: no layout from server yet -->
        <div
          v-if="!layoutTreeWithActive"
          :style="{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '100%',
            height: '100%',
            color: '#565f89',
            fontSize: '14px',
          }"
        >
          <div :style="{ textAlign: 'center' }">
            <div
              v-if="!sessionId"
              :style="{ marginBottom: '4px' }"
            >
              Waiting for session...
            </div>
            <div
              v-else-if="connectionState === 'connecting'"
              :style="{ marginBottom: '4px' }"
            >
              Connecting...
            </div>
            <div
              v-else-if="connectionState === 'disconnected'"
              :style="{ marginBottom: '4px' }"
            >
              Disconnected. Reconnecting...
            </div>
            <div v-else :style="{ marginBottom: '4px' }">
              Waiting for agent layout...
            </div>
          </div>
        </div>

        <!-- Render the pane tree -->
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

      <!-- Sidebar (Chat) -->
      <div
        v-if="sidebar"
        :style="{
          width: '320px',
          flexShrink: 0,
          borderLeft: '1px solid #24283b',
          background: '#16161e',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }"
      >
        <div
          :style="{
            padding: '8px 12px',
            borderBottom: '1px solid #24283b',
            fontSize: '12px',
            fontWeight: 600,
            color: '#565f89',
            userSelect: 'none',
          }"
        >
          Chat
        </div>
        <div
          :style="{
            flex: '1 1 0%',
            overflow: 'auto',
            padding: '8px 12px',
            fontSize: '13px',
            color: '#565f89',
          }"
        >
          <!-- Chat slot for embedding apps to inject content -->
          <slot name="sidebar">
            <div
              :style="{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                color: '#414868',
              }"
            >
              Chat not connected
            </div>
          </slot>
        </div>
      </div>
    </div>

    <!-- Status bar -->
    <div
      v-if="showStatusBar"
      :style="{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '3px 12px',
        background: '#16161e',
        borderTop: '1px solid #24283b',
        fontSize: '11px',
        color: '#565f89',
        flexShrink: 0,
        userSelect: 'none',
      }"
    >
      <div :style="{ display: 'flex', alignItems: 'center', gap: '12px' }">
        <span
          :style="{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
          }"
        >
          <span
            :style="{
              display: 'inline-block',
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: statusColor,
            }"
          />
          {{ connectionState }}
        </span>
        <span v-if="sessionId">
          Session: {{ sessionId.slice(0, 12) }}{{ sessionId.length > 12 ? '...' : '' }}
        </span>
      </div>
      <div :style="{ display: 'flex', alignItems: 'center', gap: '12px' }">
        <span v-if="paneCount > 0">
          {{ paneCount }} pane{{ paneCount !== 1 ? "s" : "" }}
        </span>
        <span v-if="zoomedPaneId">
          ZOOM
        </span>
      </div>
    </div>
  </div>
</template>
