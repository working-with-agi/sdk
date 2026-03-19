<script setup lang="ts">
import {
  ref,
  onMounted,
  onBeforeUnmount,
  watch,
  nextTick,
  type PropType,
} from "vue";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import type { TerminalTheme } from "@working-with-agi/sdk";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PaneNode {
  /** Node type: "leaf" for terminal panes, "hsplit"/"vsplit" for splits */
  type: "leaf" | "hsplit" | "vsplit";
  /** Pane identifier (leaf nodes only) */
  pane_id?: string;
  /** Children for branch nodes (always 2 for binary tree) */
  children?: [PaneNode, PaneNode];
  /** Split ratio 0-1 for the first child (default 0.5) */
  ratio?: number;
  /** Agent role label shown as a badge on leaf panes */
  role?: string;
  /** Whether this is the currently active/focused pane */
  active?: boolean;
}

export interface PaneTerminalHandle {
  terminal: Terminal;
  fitAddon: FitAddon;
  container: HTMLElement;
}

const props = defineProps({
  /** The layout tree node to render */
  node: {
    type: Object as PropType<PaneNode>,
    required: true,
  },
  /** Resolved terminal theme */
  theme: {
    type: Object as PropType<TerminalTheme>,
    required: true,
  },
  /** Font size for terminals */
  fontSize: {
    type: Number,
    default: 14,
  },
  /** Whether to use WebGL renderer */
  webgl: {
    type: Boolean,
    default: true,
  },
  /** The pane ID currently in zoom mode (null = no zoom) */
  zoomedPaneId: {
    type: String as PropType<string | null>,
    default: null,
  },
});

const emit = defineEmits<{
  (e: "terminal-created", paneId: string, handle: PaneTerminalHandle): void;
  (e: "terminal-destroyed", paneId: string): void;
  (e: "pane-click", paneId: string): void;
  (e: "pane-zoom", paneId: string): void;
}>();

// ---------------------------------------------------------------------------
// Leaf terminal management
// ---------------------------------------------------------------------------

const terminalRef = ref<HTMLElement | null>(null);
let xterm: Terminal | null = null;
let fitAddon: FitAddon | null = null;
let resizeObserver: ResizeObserver | null = null;

const isLeaf = () => props.node.type === "leaf";

function mountTerminal() {
  if (!isLeaf() || !terminalRef.value) return;

  xterm = new Terminal({
    fontSize: props.fontSize,
    fontFamily:
      "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Menlo, monospace",
    cursorStyle: "block",
    cursorBlink: true,
    theme: props.theme,
    allowProposedApi: true,
    scrollback: 10000,
  });

  fitAddon = new FitAddon();
  xterm.loadAddon(fitAddon);
  xterm.open(terminalRef.value);

  if (props.webgl) {
    try {
      xterm.loadAddon(new WebglAddon());
    } catch {
      // Fall back to canvas renderer
    }
  }

  fitAddon.fit();

  resizeObserver = new ResizeObserver(() => {
    try {
      fitAddon?.fit();
    } catch {
      // Ignore fit errors during transitions
    }
  });
  resizeObserver.observe(terminalRef.value);

  emit("terminal-created", props.node.pane_id!, {
    terminal: xterm,
    fitAddon,
    container: terminalRef.value,
  });
}

function unmountTerminal() {
  if (!xterm) return;
  resizeObserver?.disconnect();
  resizeObserver = null;
  xterm.dispose();
  xterm = null;
  fitAddon = null;
  emit("terminal-destroyed", props.node.pane_id!);
}

onMounted(() => {
  nextTick(() => mountTerminal());
});

onBeforeUnmount(() => {
  unmountTerminal();
});

// Re-mount terminal if the node id changes (server replaced the pane)
watch(
  () => props.node.pane_id!,
  () => {
    unmountTerminal();
    nextTick(() => mountTerminal());
  },
);

// Update theme on existing terminal
watch(
  () => props.theme,
  (newTheme) => {
    if (xterm) {
      xterm.options.theme = newTheme;
    }
  },
);

// Update font size on existing terminal
watch(
  () => props.fontSize,
  (newSize) => {
    if (xterm) {
      xterm.options.fontSize = newSize;
      fitAddon?.fit();
    }
  },
);

// ---------------------------------------------------------------------------
// Role badge color mapping
// ---------------------------------------------------------------------------

const ROLE_COLORS: Record<string, string> = {
  developer: "#9ece6a",
  reviewer: "#7aa2f7",
  tester: "#e0af68",
  architect: "#bb9af7",
  orchestrator: "#f7768e",
  main: "#7dcfff",
  shell: "#a9b1d6",
};

function roleBadgeColor(role?: string): string {
  if (!role) return "#565f89";
  return ROLE_COLORS[role.toLowerCase()] ?? "#565f89";
}

// ---------------------------------------------------------------------------
// Zoom visibility
// ---------------------------------------------------------------------------

function isHiddenByZoom(): boolean {
  if (!props.zoomedPaneId) return false;
  // If zoomed, only the zoomed leaf is visible
  if (isLeaf()) return props.node.pane_id! !== props.zoomedPaneId;
  // For branch nodes, check if the zoomed pane is a descendant
  return !containsPane(props.node, props.zoomedPaneId);
}

function containsPane(node: PaneNode, paneId: string): boolean {
  if (node.pane_id === paneId) return true;
  if (node.children) {
    return node.children.some((child) => containsPane(child, paneId));
  }
  return false;
}
</script>

<template>
  <!-- Branch node: flex container with two children -->
  <div
    v-if="node.type !== 'leaf' && node.children"
    :style="{
      display: isHiddenByZoom() ? 'none' : 'flex',
      flexDirection: node.type === 'hsplit' ? 'row' : 'column',
      width: '100%',
      height: '100%',
      minWidth: 0,
      minHeight: 0,
    }"
  >
    <div
      :style="{
        flex: `${(node.ratio ?? 0.5) * 100} 1 0%`,
        minWidth: 0,
        minHeight: 0,
        overflow: 'hidden',
      }"
    >
      <PaneLayout
        :node="node.children[0]"
        :theme="theme"
        :font-size="fontSize"
        :webgl="webgl"
        :zoomed-pane-id="zoomedPaneId"
        @terminal-created="(id, h) => emit('terminal-created', id, h)"
        @terminal-destroyed="(id) => emit('terminal-destroyed', id)"
        @pane-click="(id) => emit('pane-click', id)"
        @pane-zoom="(id) => emit('pane-zoom', id)"
      />
    </div>

    <!-- Separator line -->
    <div
      :style="{
        flexShrink: 0,
        background: '#1a1b26',
        [node.type === 'hsplit' ? 'width' : 'height']: '2px',
      }"
    />

    <div
      :style="{
        flex: `${(1 - (node.ratio ?? 0.5)) * 100} 1 0%`,
        minWidth: 0,
        minHeight: 0,
        overflow: 'hidden',
      }"
    >
      <PaneLayout
        :node="node.children[1]"
        :theme="theme"
        :font-size="fontSize"
        :webgl="webgl"
        :zoomed-pane-id="zoomedPaneId"
        @terminal-created="(id, h) => emit('terminal-created', id, h)"
        @terminal-destroyed="(id) => emit('terminal-destroyed', id)"
        @pane-click="(id) => emit('pane-click', id)"
        @pane-zoom="(id) => emit('pane-zoom', id)"
      />
    </div>
  </div>

  <!-- Leaf node: terminal pane with role badge -->
  <div
    v-else
    :style="{
      display: isHiddenByZoom() ? 'none' : 'flex',
      flexDirection: 'column',
      width: '100%',
      height: '100%',
      minWidth: 0,
      minHeight: 0,
      position: 'relative',
      border: node.active ? '1px solid #7aa2f7' : '1px solid #24283b',
      borderRadius: '2px',
      overflow: 'hidden',
    }"
    @click="emit('pane-click', node.pane_id!)"
  >
    <!-- Role badge header -->
    <div
      v-if="node.role"
      :style="{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '2px 8px',
        background: '#16161e',
        borderBottom: '1px solid #24283b',
        fontSize: '11px',
        fontFamily:
          '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
        color: '#565f89',
        userSelect: 'none',
        flexShrink: 0,
      }"
    >
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
            background: roleBadgeColor(node.role),
          }"
        />
        <span :style="{ color: roleBadgeColor(node.role), fontWeight: 600 }">
          {{ node.role }}
        </span>
      </span>

      <!-- Zoom toggle button -->
      <button
        :style="{
          background: 'none',
          border: 'none',
          color: '#565f89',
          cursor: 'pointer',
          padding: '0 2px',
          fontSize: '11px',
          lineHeight: 1,
        }"
        :title="zoomedPaneId === node.pane_id ? 'Exit zoom' : 'Zoom pane'"
        @click.stop="emit('pane-zoom', node.pane_id!)"
      >
        {{ zoomedPaneId === node.pane_id ? "\u25a3" : "\u25a1" }}
      </button>
    </div>

    <!-- Terminal container -->
    <div
      ref="terminalRef"
      :style="{
        flex: '1 1 0%',
        minHeight: 0,
        overflow: 'hidden',
      }"
    />
  </div>
</template>
