/**
 * Pinia store for tmux session state management.
 *
 * Manages session/window/pane hierarchy from server state_sync/state_update messages.
 */

import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import { TmuxWebSocketService } from '../services/TmuxWebSocketService'
import type { StatusBarData } from '../services/TmuxWebSocketService'
import { useAgentMessagingStore } from './agentMessagingStore'
import { useAgentTaskStore } from './agentTaskStore'

// --- TypeScript interfaces mirroring backend models ---

export interface LayoutNode {
  type: 'leaf' | 'hsplit' | 'vsplit'
  pane_id?: string
  children?: LayoutNode[]
  ratio: number
}

export interface TmuxPaneState {
  pane_id: string
  status: 'running' | 'exited' | 'blocked'
  cols: number
  rows: number
  title: string
  exit_code: number | null
  created_at: number
  history_size: number
  role: string
  mode?: 'terminal' | 'agent-inbox' | 'agent-tasks'
}

export interface TmuxWindowState {
  window_id: string
  window_index: number
  name: string
  layout: LayoutNode
  panes: Record<string, TmuxPaneState>
  active_pane_id: string
}

export interface TmuxSessionState {
  session_id: string
  name: string
  created_at: number
  windows: Record<string, TmuxWindowState>
  active_window_id: string
  active_clients: number
}

export const useTmuxStore = defineStore('tmuxStore', () => {
  // --- State ---
  const session = ref<TmuxSessionState | null>(null)
  const isConnected = ref(false)
  const sessionList = ref<TmuxSessionState[]>([])
  const zoomedPaneId = ref<string | null>(null)
  const statusBar = ref<StatusBarData | null>(null)

  // Per-pane output listeners: paneId -> callbacks[]
  const paneOutputListeners = ref<Map<string, ((data: Uint8Array) => void)[]>>(new Map())

  // WebSocket service
  const wsService = shallowRef<TmuxWebSocketService | null>(null)

  // --- Computed ---
  const activeWindow = computed(() => {
    if (!session.value) return null
    return session.value.windows[session.value.active_window_id] || null
  })

  const activePane = computed(() => {
    const win = activeWindow.value
    if (!win) return null
    return win.panes[win.active_pane_id] || null
  })

  const windowList = computed(() => {
    if (!session.value) return []
    return Object.values(session.value.windows).sort((a, b) => a.window_index - b.window_index)
  })

  const activePaneId = computed(() => {
    return activeWindow.value?.active_pane_id || ''
  })

  const sessionId = computed(() => session.value?.session_id || '')

  // --- Actions ---

  function connect(targetSessionId: string = '_new') {
    if (wsService.value) {
      wsService.value.disconnect()
    }

    const messagingStore = useAgentMessagingStore()
    const taskStore = useAgentTaskStore()

    const service = new TmuxWebSocketService({
      onStateSync: (sess) => {
        session.value = sess
      },
      onStateUpdate: (data) => {
        // Re-sync full state on updates for simplicity
        if (data.session) {
          session.value = data.session
        } else if (data.layout && data.window_id && session.value) {
          const win = session.value.windows[data.window_id]
          if (win) win.layout = data.layout
        }
      },
      onPaneOutput: (paneId, data) => {
        const listeners = paneOutputListeners.value.get(paneId)
        if (listeners) {
          listeners.forEach((cb) => cb(data))
        }
      },
      onPaneExited: (paneId, exitCode) => {
        if (!session.value) return
        for (const win of Object.values(session.value.windows)) {
          const pane = win.panes[paneId]
          if (pane) {
            pane.status = 'exited'
            pane.exit_code = exitCode
          }
        }
      },
      onStatusUpdate: (data) => {
        statusBar.value = data
      },
      onSessionList: (sessions) => {
        sessionList.value = sessions
      },
      onAgentMessage: (msg) => messagingStore.handleIncomingMessage(msg),
      onAgentStatus: (agentId, isIdle) => messagingStore.updateAgentStatus(agentId, isIdle),
      onTaskListUpdate: (tasks) => taskStore.handleTaskListUpdate(tasks),
      onOpen: () => {
        isConnected.value = true
      },
      onClose: () => {
        isConnected.value = false
      },
    })

    wsService.value = service
    service.connect(targetSessionId)
  }

  function disconnect() {
    wsService.value?.disconnect()
    wsService.value = null
    session.value = null
    isConnected.value = false
  }

  // Pane output listener management
  function onPaneOutput(paneId: string, callback: (data: Uint8Array) => void) {
    if (!paneOutputListeners.value.has(paneId)) {
      paneOutputListeners.value.set(paneId, [])
    }
    paneOutputListeners.value.get(paneId)!.push(callback)
  }

  function offPaneOutput(paneId: string, callback: (data: Uint8Array) => void) {
    const listeners = paneOutputListeners.value.get(paneId)
    if (listeners) {
      const idx = listeners.indexOf(callback)
      if (idx !== -1) listeners.splice(idx, 1)
    }
  }

  // Proxy methods to WebSocket service
  function sendPaneInput(paneId: string, data: string) {
    wsService.value?.sendPaneInput(paneId, data)
  }

  function splitPane(direction: 'v' | 'h', paneId?: string) {
    wsService.value?.splitPane(direction, paneId)
  }

  function closePane(paneId: string) {
    wsService.value?.closePane(paneId)
  }

  function focusPane(paneId: string) {
    if (!session.value) return
    // Local focus update
    const win = activeWindow.value
    if (win && win.panes[paneId]) {
      win.active_pane_id = paneId
    }
    wsService.value?.focusPane(paneId)
  }

  function resizePanePty(paneId: string, cols: number, rows: number) {
    wsService.value?.resizePanePty(paneId, cols, rows)
  }

  function resizeLayout(paneId: string, delta: number) {
    wsService.value?.resizeLayout(paneId, delta)
  }

  function createWindow(name?: string) {
    wsService.value?.createWindow(name)
  }

  function closeWindow(windowId: string) {
    wsService.value?.closeWindow(windowId)
  }

  function selectWindow(windowId: string) {
    if (session.value) {
      session.value.active_window_id = windowId
    }
    wsService.value?.selectWindow(windowId)
  }

  function renameWindow(windowId: string, name: string) {
    wsService.value?.renameWindow(windowId, name)
  }

  function renameSession(name: string) {
    wsService.value?.renameSession(name)
  }

  function requestSessionList() {
    wsService.value?.requestSessionList()
  }

  function applyPresetLayout(preset: string) {
    wsService.value?.applyPresetLayout(preset)
  }

  function toggleZoom(paneId: string) {
    zoomedPaneId.value = zoomedPaneId.value === paneId ? null : paneId
  }

  function setPaneMode(paneId: string, mode: string) {
    if (!session.value) return
    for (const win of Object.values(session.value.windows)) {
      const pane = win.panes[paneId]
      if (pane) {
        pane.mode = mode as TmuxPaneState['mode']
        break
      }
    }
  }

  function detach() {
    wsService.value?.detach()
  }

  function sendAgentDM(toAgent: string, content: string, summary?: string) {
    wsService.value?.sendAgentDM(toAgent, content, summary || content.slice(0, 50))
  }

  function sendAgentBroadcast(content: string, summary?: string) {
    wsService.value?.sendAgentBroadcast(content, summary || content.slice(0, 50))
  }

  function sendShutdownRequest(toAgent: string) {
    wsService.value?.sendShutdownRequest(toAgent)
  }

  return {
    // State
    session,
    isConnected,
    sessionList,
    zoomedPaneId,
    statusBar,

    // Computed
    activeWindow,
    activePane,
    windowList,
    activePaneId,
    sessionId,

    // Actions
    connect,
    disconnect,
    onPaneOutput,
    offPaneOutput,
    sendPaneInput,
    splitPane,
    closePane,
    focusPane,
    resizePanePty,
    resizeLayout,
    createWindow,
    closeWindow,
    selectWindow,
    renameWindow,
    renameSession,
    requestSessionList,
    applyPresetLayout,
    toggleZoom,
    detach,
    setPaneMode,
    sendAgentDM,
    sendAgentBroadcast,
    sendShutdownRequest,
  }
})
