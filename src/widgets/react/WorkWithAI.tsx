/**
 * @work-with-ai/react
 *
 * React component that connects to AgentServer (AetherTerm) and provides
 * an xterm.js terminal running an AI agent session.
 *
 * Lifecycle:
 *   1. Connect to AgentServer WebSocket
 *   2. Request session creation (with skills + context)
 *   3. Render xterm.js terminal
 *   4. User interacts with AI agent via terminal
 *
 * Usage:
 *   <WorkWithAI
 *     agentServerUrl="ws://localhost:57575"
 *     context={{ projects: [...] }}
 *     skills={['secretary']}
 *     locale="ja"
 *   />
 */
import React, { useEffect, useRef, useState, useCallback } from 'react'
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
  onConnected?: () => void
  onDisconnected?: () => void
  onSessionCreated?: (sessionId: string) => void
  onError?: (err: Error) => void
  className?: string
  style?: React.CSSProperties
}

const darkTheme: ITheme = {
  background: '#1e1e1e', foreground: '#ffffff', cursor: '#ffffff', cursorAccent: '#000000',
  selectionBackground: 'rgba(255, 255, 255, 0.3)',
  black: '#000000', red: '#cd3131', green: '#0dbc79', yellow: '#e5e510',
  blue: '#3b78ff', magenta: '#bc3fbc', cyan: '#0dc2c2', white: '#e5e5e5',
  brightBlack: '#666666', brightRed: '#f14c4c', brightGreen: '#23d18b', brightYellow: '#f5f543',
  brightBlue: '#3b8eea', brightMagenta: '#d670d6', brightCyan: '#29b8db', brightWhite: '#ffffff',
}

const lightTheme: ITheme = {
  background: '#ffffff', foreground: '#1e1e1e', cursor: '#1e1e1e', cursorAccent: '#ffffff',
  selectionBackground: 'rgba(0, 0, 0, 0.15)',
  black: '#000000', red: '#cd3131', green: '#008000', yellow: '#795e26',
  blue: '#0451a5', magenta: '#bc05bc', cyan: '#0598bc', white: '#e5e5e5',
  brightBlack: '#666666', brightRed: '#cd3131', brightGreen: '#14ce14', brightYellow: '#b5ba00',
  brightBlue: '#0451a5', brightMagenta: '#bc05bc', brightCyan: '#0598bc', brightWhite: '#a5a5a5',
}

export function WorkWithAI({
  agentServerUrl = 'ws://localhost:57575',
  apiKey = '',
  context = {},
  skills = [],
  locale = 'ja',
  theme = 'dark',
  fontSize = 13,
  onConnected,
  onDisconnected,
  onSessionCreated,
  onError,
  className,
  style,
}: WorkWithAIProps) {
  const terminalElRef = useRef<HTMLDivElement>(null)
  const terminalRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const wsRef = useRef<ReconnectingWebSocket | null>(null)
  const paneIdRef = useRef('')
  const [status, setStatus] = useState<'connecting' | 'connected' | 'session' | 'error'>('connecting')

  const isJa = locale === 'ja'

  const sendInput = useCallback((data: string) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN || !paneIdRef.current) return
    const paneBytes = new TextEncoder().encode(paneIdRef.current)
    const dataBytes = new TextEncoder().encode(data)
    const frame = new Uint8Array(1 + paneBytes.length + dataBytes.length)
    frame[0] = paneBytes.length
    frame.set(paneBytes, 1)
    frame.set(dataBytes, 1 + paneBytes.length)
    ws.send(frame.buffer)
  }, [])

  const sendResize = useCallback((cols: number, rows: number) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN || !paneIdRef.current) return
    ws.send(JSON.stringify({ type: 'pane_resize', pane_id: paneIdRef.current, cols, rows }))
  }, [])

  // Initialize terminal + WebSocket
  useEffect(() => {
    if (!terminalElRef.current) return

    // Terminal
    const terminal = new Terminal({
      convertEol: true, cursorBlink: true, disableStdin: false, scrollback: 10000,
      theme: theme === 'light' ? lightTheme : darkTheme,
      allowProposedApi: true, fontSize,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
    })
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.loadAddon(new WebLinksAddon())
    terminal.open(terminalElRef.current)
    fitAddon.fit()
    terminal.onData(sendInput)
    terminal.onResize(({ cols, rows }) => sendResize(cols, rows))
    terminalRef.current = terminal
    fitAddonRef.current = fitAddon

    const resizeObserver = new ResizeObserver(() => fitAddon.fit())
    resizeObserver.observe(terminalElRef.current)

    // WebSocket
    const url = `${agentServerUrl}/ws/tmux/work-with-ai`
    const ws = new ReconnectingWebSocket(url, [], { maxRetries: 10, connectionTimeout: 4000 })
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => {
      setStatus('connected')
      onConnected?.()
      ws.send(JSON.stringify({
        type: 'create_session',
        payload: { api_key: apiKey, skills, context, locale },
      }))
    }

    ws.onmessage = (event: MessageEvent) => {
      if (typeof event.data === 'string') {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'state_sync' || msg.type === 'session_created') {
            const session = msg.session || msg
            const sid = session.session_id || ''
            if (session.panes?.length > 0) paneIdRef.current = session.panes[0].pane_id || ''
            setStatus('session')
            onSessionCreated?.(sid)
          }
          if (msg.type === 'pane_exited') setStatus('connected')
        } catch { /* ignore */ }
      } else {
        const view = new Uint8Array(event.data as ArrayBuffer)
        if (view.length < 2) return
        const paneIdLen = view[0]
        if (view.length < 1 + paneIdLen) return
        terminal.write(view.slice(1 + paneIdLen))
      }
    }

    ws.onclose = () => { setStatus('connecting'); onDisconnected?.() }
    ws.onerror = () => { onError?.(new Error('AgentServer connection failed')) }

    return () => {
      resizeObserver.disconnect()
      terminal.dispose()
      terminalRef.current = null
      ws.close()
      wsRef.current = null
    }
  }, [agentServerUrl, apiKey, locale, fontSize]) // eslint-disable-line react-hooks/exhaustive-deps

  // Theme change
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.options.theme = theme === 'light' ? lightTheme : darkTheme
    }
  }, [theme])

  const statusText = status === 'session'
    ? (isJa ? 'セッション中' : 'Session active')
    : status === 'connected'
      ? (isJa ? '接続済み' : 'Connected')
      : (isJa ? '接続中...' : 'Connecting...')

  return (
    <div className={`wai-container wai-theme-${theme} ${className || ''}`} style={style}>
      {/* Header */}
      <div className="wai-header">
        <div className="wai-header-icon">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M8 2v4M8 10v4M2 8h4M10 8h4M4 4l2.5 2.5M9.5 9.5L12 12M12 4l-2.5 2.5M6.5 9.5L4 12" />
          </svg>
        </div>
        <div>
          <div className="wai-header-title">Work with AI</div>
          <div className={`wai-header-status ${status === 'session' ? 'wai-active' : ''}`}>
            <span className="wai-status-dot" />
            {statusText}
          </div>
        </div>
      </div>
      {/* Terminal */}
      <div ref={terminalElRef} className="wai-terminal" />
    </div>
  )
}

export default WorkWithAI
