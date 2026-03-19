<script setup lang="ts">
/**
 * @work-with-ai/vue
 *
 * Vue 3 component that connects to AgentServer (AetherTerm) and provides
 * an xterm.js terminal running a Claude Code session.
 *
 * Lifecycle:
 *   1. Connect to AgentServer WebSocket
 *   2. Request session creation (with skills + context)
 *   3. Render xterm.js terminal
 *   4. User interacts with Claude Code via terminal
 *
 * Usage:
 *   <WorkWithAI
 *     agent-server-url="ws://localhost:57575"
 *     :context="{ projects: [...] }"
 *     :skills="['secretary']"
 *     locale="ja"
 *   />
 */
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { Terminal, type ITheme } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import ReconnectingWebSocket from 'reconnecting-websocket'

export interface WorkWithAIProps {
  agentServerUrl?: string
  apiKey?: string
  context?: Record<string, any>
  skills?: string[]
  locale?: 'ja' | 'en'
  theme?: 'light' | 'dark'
  fontSize?: number
}

const props = withDefaults(defineProps<WorkWithAIProps>(), {
  agentServerUrl: 'ws://localhost:57575',
  apiKey: '',
  context: () => ({}),
  skills: () => [],
  locale: 'ja',
  theme: 'dark',
  fontSize: 13,
})

const emit = defineEmits<{
  connected: []
  disconnected: []
  sessionCreated: [sessionId: string]
  error: [err: Error]
}>()

const terminalEl = ref<HTMLElement | null>(null)
const status = ref<'connecting' | 'connected' | 'session' | 'error'>('connecting')
const sessionId = ref('')
const paneId = ref('')

let terminal: Terminal | null = null
let fitAddon: FitAddon | null = null
let ws: ReconnectingWebSocket | null = null
let resizeObserver: ResizeObserver | null = null

const isJa = computed(() => props.locale === 'ja')

const darkTheme: ITheme = {
  background: '#1e1e1e',
  foreground: '#ffffff',
  cursor: '#ffffff',
  cursorAccent: '#000000',
  selectionBackground: 'rgba(255, 255, 255, 0.3)',
  black: '#000000',
  red: '#cd3131',
  green: '#0dbc79',
  yellow: '#e5e510',
  blue: '#3b78ff',
  magenta: '#bc3fbc',
  cyan: '#0dc2c2',
  white: '#e5e5e5',
  brightBlack: '#666666',
  brightRed: '#f14c4c',
  brightGreen: '#23d18b',
  brightYellow: '#f5f543',
  brightBlue: '#3b8eea',
  brightMagenta: '#d670d6',
  brightCyan: '#29b8db',
  brightWhite: '#ffffff',
}

const lightTheme: ITheme = {
  background: '#ffffff',
  foreground: '#1e1e1e',
  cursor: '#1e1e1e',
  cursorAccent: '#ffffff',
  selectionBackground: 'rgba(0, 0, 0, 0.15)',
  black: '#000000',
  red: '#cd3131',
  green: '#008000',
  yellow: '#795e26',
  blue: '#0451a5',
  magenta: '#bc05bc',
  cyan: '#0598bc',
  white: '#e5e5e5',
  brightBlack: '#666666',
  brightRed: '#cd3131',
  brightGreen: '#14ce14',
  brightYellow: '#b5ba00',
  brightBlue: '#0451a5',
  brightMagenta: '#bc05bc',
  brightCyan: '#0598bc',
  brightWhite: '#a5a5a5',
}

function connect() {
  const url = `${props.agentServerUrl}/ws/tmux/work-with-ai`
  ws = new ReconnectingWebSocket(url, [], {
    maxRetries: 10,
    connectionTimeout: 4000,
  })
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => {
    status.value = 'connected'
    emit('connected')

    // Request session creation with skills and context
    ws?.send(JSON.stringify({
      type: 'create_session',
      payload: {
        api_key: props.apiKey,
        skills: props.skills,
        context: props.context,
        locale: props.locale,
      },
    }))
  }

  ws.onmessage = (event: MessageEvent) => {
    if (typeof event.data === 'string') {
      handleTextMessage(event.data)
    } else {
      handleBinaryMessage(event.data as ArrayBuffer)
    }
  }

  ws.onclose = () => {
    status.value = 'connecting'
    emit('disconnected')
  }

  ws.onerror = () => {
    emit('error', new Error('AgentServer connection failed'))
  }
}

function handleTextMessage(text: string) {
  try {
    const msg = JSON.parse(text)

    if (msg.type === 'state_sync' || msg.type === 'session_created') {
      const session = msg.session || msg
      sessionId.value = session.session_id || ''
      if (session.panes && session.panes.length > 0) {
        paneId.value = session.panes[0].pane_id || ''
      }
      status.value = 'session'
      emit('sessionCreated', sessionId.value)
    }

    if (msg.type === 'pane_exited') {
      status.value = 'connected'
    }
  } catch { /* ignore parse errors */ }
}

function handleBinaryMessage(buffer: ArrayBuffer) {
  // AetherTerm binary frame: [1 byte pane_id_len][pane_id bytes][pty data]
  const view = new Uint8Array(buffer)
  if (view.length < 2) return

  const paneIdLen = view[0]
  if (view.length < 1 + paneIdLen) return

  const data = view.slice(1 + paneIdLen)
  terminal?.write(data)
}

function sendInput(data: string) {
  if (!ws || ws.readyState !== WebSocket.OPEN || !paneId.value) return

  const paneBytes = new TextEncoder().encode(paneId.value)
  const dataBytes = new TextEncoder().encode(data)
  const frame = new Uint8Array(1 + paneBytes.length + dataBytes.length)
  frame[0] = paneBytes.length
  frame.set(paneBytes, 1)
  frame.set(dataBytes, 1 + paneBytes.length)
  ws.send(frame.buffer)
}

function sendResize(cols: number, rows: number) {
  if (!ws || ws.readyState !== WebSocket.OPEN || !paneId.value) return
  ws.send(JSON.stringify({
    type: 'pane_resize',
    pane_id: paneId.value,
    cols,
    rows,
  }))
}

function initTerminal() {
  if (!terminalEl.value) return

  terminal = new Terminal({
    convertEol: true,
    cursorBlink: true,
    disableStdin: false,
    scrollback: 10000,
    theme: props.theme === 'light' ? lightTheme : darkTheme,
    allowProposedApi: true,
    fontSize: props.fontSize,
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
  })

  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.loadAddon(new WebLinksAddon())

  terminal.open(terminalEl.value)
  fitAddon.fit()

  terminal.onData((data: string) => sendInput(data))
  terminal.onResize((dims: { cols: number; rows: number }) => sendResize(dims.cols, dims.rows))

  resizeObserver = new ResizeObserver(() => fitAddon?.fit())
  resizeObserver.observe(terminalEl.value)
}

onMounted(() => {
  initTerminal()
  connect()
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  terminal?.dispose()
  terminal = null
  if (ws) { ws.close(); ws = null }
})

watch(() => props.theme, (newTheme: string) => {
  if (terminal) {
    terminal.options.theme = newTheme === 'light' ? lightTheme : darkTheme
  }
})

defineExpose({
  focus: () => terminal?.focus(),
  fit: () => fitAddon?.fit(),
  sessionId,
})
</script>

<template>
  <div class="wai-container" :class="`wai-theme-${theme}`">
    <!-- Header -->
    <div class="wai-header">
      <div class="wai-header-icon">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M8 2v4M8 10v4M2 8h4M10 8h4M4 4l2.5 2.5M9.5 9.5L12 12M12 4l-2.5 2.5M6.5 9.5L4 12" />
        </svg>
      </div>
      <div class="wai-header-text">
        <div class="wai-header-title">Work with AI</div>
        <div class="wai-header-status" :class="{ 'wai-active': status === 'session' }">
          <span class="wai-status-dot" />
          <template v-if="status === 'session'">{{ isJa ? 'セッション中' : 'Session active' }}</template>
          <template v-else-if="status === 'connected'">{{ isJa ? '接続済み' : 'Connected' }}</template>
          <template v-else>{{ isJa ? '接続中...' : 'Connecting...' }}</template>
        </div>
      </div>
    </div>

    <!-- Terminal -->
    <div ref="terminalEl" class="wai-terminal" />
  </div>
</template>

<style scoped>
.wai-container {
  border: 1px solid #e2e0db;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 500px;
}

.wai-theme-dark .wai-container,
.wai-theme-dark {
  border-color: #3a3a4e;
}

.wai-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid #e2e0db;
  background: #f5f3ff;
  flex-shrink: 0;
}

.wai-theme-dark .wai-header {
  background: #2a2a3e;
  border-color: #3a3a4e;
}

.wai-header-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #7c3aed;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.wai-header-icon svg {
  width: 16px;
  height: 16px;
}

.wai-header-title {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
}

.wai-theme-dark .wai-header-title {
  color: #e0e0e8;
}

.wai-header-status {
  font-size: 11px;
  color: #8a8a96;
  display: flex;
  align-items: center;
  gap: 4px;
}

.wai-header-status.wai-active {
  color: #059669;
}

.wai-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #8a8a96;
}

.wai-active .wai-status-dot {
  background: #059669;
}

.wai-terminal {
  flex: 1;
  background: #1e1e1e;
  overflow: hidden;
}

.wai-theme-light .wai-terminal {
  background: #ffffff;
}

:deep(.xterm) {
  height: 100%;
  padding: 4px;
}

:deep(.xterm-viewport::-webkit-scrollbar) {
  width: 6px;
}

:deep(.xterm-viewport::-webkit-scrollbar-thumb) {
  background: #555;
  border-radius: 3px;
}
</style>
