/**
 * WebSocket service for tmux multiplexer.
 *
 * Single WebSocket connection per session.
 * Binary frames: [1 byte pane_id_len][pane_id bytes][pty data]
 * Text frames: JSON control messages.
 */

import ReconnectingWebSocket from 'reconnecting-websocket'
import type { AgentMessage } from '../stores/agentMessagingStore'
import type { SharedTask } from '../stores/agentTaskStore'
import type { TmuxSessionState } from '../stores/tmuxStore'

export interface StatusBarData {
  type: string
  session_name?: string
  window_info?: string
  pane_info?: string
  hostname?: string
  time?: string
  [key: string]: any
}

export interface TmuxWsCallbacks {
  onStateSync: (session: TmuxSessionState) => void
  onStateUpdate: (data: any) => void
  onPaneOutput: (paneId: string, data: Uint8Array) => void
  onPaneExited: (paneId: string, exitCode: number) => void
  onStatusUpdate: (data: StatusBarData) => void
  onSessionList: (sessions: TmuxSessionState[]) => void
  onAgentMessage?: (msg: AgentMessage) => void
  onAgentStatus?: (agentId: string, isIdle: boolean) => void
  onTaskListUpdate?: (tasks: SharedTask[]) => void
  onOpen: () => void
  onClose: () => void
}

export class TmuxWebSocketService {
  private ws: ReconnectingWebSocket | null = null
  private callbacks: TmuxWsCallbacks
  private sessionId: string = ''
  private intentionalClose = false

  constructor(callbacks: TmuxWsCallbacks) {
    this.callbacks = callbacks
  }

  connect(sessionId: string): void {
    this.sessionId = sessionId
    this.intentionalClose = false

    if (this.ws) {
      this.ws.close()
      this.ws = null
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws/tmux/${this.sessionId}`

    this.ws = new ReconnectingWebSocket(url, [], {
      maxRetries: 10,
      connectionTimeout: 4000,
      maxReconnectionDelay: 30000,
    })
    this.ws.binaryType = 'arraybuffer'

    this.ws.onopen = () => {
      this.callbacks.onOpen()
    }

    this.ws.onclose = () => {
      this.callbacks.onClose()
    }

    this.ws.onerror = () => {
      // onclose will fire after this
    }

    this.ws.onmessage = (event: MessageEvent) => {
      if (typeof event.data === 'string') {
        this._handleTextMessage(event.data)
      } else {
        this._handleBinaryMessage(event.data as ArrayBuffer)
      }
    }
  }

  private _handleTextMessage(text: string): void {
    try {
      const msg = JSON.parse(text)
      switch (msg.type) {
        case 'state_sync':
          this.callbacks.onStateSync(msg.session)
          break
        case 'state_update':
          this.callbacks.onStateUpdate(msg)
          break
        case 'pane_exited':
          this.callbacks.onPaneExited(msg.pane_id, msg.exit_code)
          break
        case 'status_update':
          this.callbacks.onStatusUpdate(msg)
          break
        case 'session_list':
          this.callbacks.onSessionList(msg.sessions)
          break
        case 'agent_message':
          this.callbacks.onAgentMessage?.(msg)
          break
        case 'agent_status':
          this.callbacks.onAgentStatus?.(msg.agent_id, msg.is_idle)
          break
        case 'task_list_update':
          this.callbacks.onTaskListUpdate?.(msg.tasks)
          break
        default:
          // Forward as state_update for unrecognized types
          this.callbacks.onStateUpdate(msg)
      }
    } catch {
      // Ignore parse errors
    }
  }

  private _handleBinaryMessage(buffer: ArrayBuffer): void {
    const view = new Uint8Array(buffer)
    if (view.length < 2) return

    const paneIdLen = view[0]
    if (view.length < 1 + paneIdLen) return

    const paneIdBytes = view.slice(1, 1 + paneIdLen)
    const paneId = new TextDecoder().decode(paneIdBytes)
    const data = view.slice(1 + paneIdLen)

    this.callbacks.onPaneOutput(paneId, data)
  }

  // --- Send methods ---

  sendPaneInput(paneId: string, data: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return

    const paneBytes = new TextEncoder().encode(paneId)
    const dataBytes = new TextEncoder().encode(data)
    const frame = new Uint8Array(1 + paneBytes.length + dataBytes.length)
    frame[0] = paneBytes.length
    frame.set(paneBytes, 1)
    frame.set(dataBytes, 1 + paneBytes.length)
    this.ws.send(frame.buffer)
  }

  sendPaneInputBytes(paneId: string, data: Uint8Array): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return

    const paneBytes = new TextEncoder().encode(paneId)
    const frame = new Uint8Array(1 + paneBytes.length + data.length)
    frame[0] = paneBytes.length
    frame.set(paneBytes, 1)
    frame.set(data, 1 + paneBytes.length)
    this.ws.send(frame.buffer)
  }

  sendControl(msg: Record<string, any>): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return
    this.ws.send(JSON.stringify(msg))
  }

  splitPane(direction: 'v' | 'h', paneId?: string): void {
    this.sendControl({ type: 'pane_split', direction, pane_id: paneId })
  }

  closePane(paneId: string): void {
    this.sendControl({ type: 'pane_close', pane_id: paneId })
  }

  focusPane(paneId: string): void {
    this.sendControl({ type: 'pane_focus', pane_id: paneId })
  }

  resizePanePty(paneId: string, cols: number, rows: number): void {
    this.sendControl({ type: 'pane_resize_pty', pane_id: paneId, cols, rows })
  }

  resizeLayout(paneId: string, delta: number): void {
    this.sendControl({ type: 'layout_resize', pane_id: paneId, delta })
  }

  createWindow(name?: string): void {
    this.sendControl({ type: 'window_create', name })
  }

  closeWindow(windowId: string): void {
    this.sendControl({ type: 'window_close', window_id: windowId })
  }

  selectWindow(windowId: string): void {
    this.sendControl({ type: 'window_select', window_id: windowId })
  }

  renameWindow(windowId: string, name: string): void {
    this.sendControl({ type: 'window_rename', window_id: windowId, name })
  }

  renameSession(name: string): void {
    this.sendControl({ type: 'session_rename', name })
  }

  requestSessionList(): void {
    this.sendControl({ type: 'session_list' })
  }

  requestStatus(): void {
    this.sendControl({ type: 'status_request' })
  }

  applyPresetLayout(preset: string): void {
    this.sendControl({ type: 'layout_preset', preset })
  }

  sendAgentDM(toAgent: string, content: string, summary: string = ''): void {
    this.sendControl({
      type: 'agent_dm',
      to_agent: toAgent,
      from_agent: '',
      message_type: 'agent_dm',
      payload: { content, summary },
    })
  }

  sendAgentBroadcast(content: string, summary: string = ''): void {
    this.sendControl({
      type: 'agent_broadcast',
      to_agent: '',
      from_agent: '',
      message_type: 'agent_broadcast',
      payload: { content, summary },
    })
  }

  sendShutdownRequest(toAgent: string): void {
    this.sendControl({
      type: 'shutdown_request',
      to_agent: toAgent,
      from_agent: '',
      message_type: 'shutdown_request',
      payload: {},
    })
  }

  detach(): void {
    this.intentionalClose = true
    this.sendControl({ type: 'session_detach' })
  }

  disconnect(): void {
    this.intentionalClose = true
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}
