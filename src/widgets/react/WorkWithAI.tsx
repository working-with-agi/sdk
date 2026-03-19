/**
 * @secretary-io/workwithai-react
 *
 * React component for embedding the Work with AI chat widget.
 * Connects to Secretary.io AgentServer via WebSocket and provides
 * an interactive AI assistant powered by project data.
 *
 * Usage:
 *   <WorkWithAI
 *     apiKey="your-api-key"
 *     projectId="proj_abc123"
 *     theme="light"
 *     skills={['risk_analysis', 'progress_summary']}
 *     locale="ja"
 *     onMessage={(msg) => console.log(msg)}
 *   />
 */
import React, { useState, useEffect, useRef, useCallback } from 'react'

export interface Widget {
  type: string
  title: string
  items: string[]
}

export interface Message {
  id: string
  role: 'user' | 'agent'
  text: string
  widgets?: Widget[]
  timestamp: Date
}

export interface WorkWithAIProps {
  apiKey: string
  projectId: string
  theme?: 'light' | 'dark'
  skills?: string[]
  locale?: 'ja' | 'en'
  scale?: 'le' | 'org'
  baseUrl?: string
  placeholder?: string
  onMessage?: (msg: Message) => void
  onError?: (err: Error) => void
  onConnected?: () => void
  onDisconnected?: () => void
  className?: string
  style?: React.CSSProperties
}

let msgCounter = 0

export function WorkWithAI({
  apiKey,
  projectId,
  theme = 'light',
  skills = ['risk_analysis', 'progress_summary', 'comparative_analysis', 'action_items', 'timeline_forecast'],
  locale = 'ja',
  scale = 'le',
  baseUrl = 'https://api.secretary.io',
  placeholder,
  onMessage,
  onError,
  onConnected,
  onDisconnected,
  className,
  style,
}: WorkWithAIProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [connected, setConnected] = useState(false)
  const [showWatermark, setShowWatermark] = useState(true)
  const chatRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const isJa = locale === 'ja'

  // Validate API key and determine watermark visibility
  useEffect(() => {
    fetch(`${baseUrl}/api/widget/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey, project_id: projectId }),
    })
      .then(r => r.ok ? r.json() : Promise.reject(new Error('Invalid API key')))
      .then(data => setShowWatermark(data.watermark !== false))
      .catch(e => onError?.(e))
  }, [apiKey, projectId, baseUrl, onError])

  const suggestions = isJa
    ? ['プロジェクトの進捗をまとめて', 'リスクを洗い出して', '次のアクションを提案して', 'タイムライン予測を見せて']
    : ['Summarize project progress', 'Identify risks', 'Suggest next actions', 'Show timeline forecast']

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: 'smooth' })
    })
  }, [])

  const addMessage = useCallback((role: 'user' | 'agent', text: string, widgets?: Widget[]): Message => {
    const msg: Message = {
      id: `msg-${++msgCounter}`,
      role,
      text,
      widgets,
      timestamp: new Date(),
    }
    setMessages(prev => [...prev, msg])
    scrollToBottom()
    onMessage?.(msg)
    return msg
  }, [onMessage, scrollToBottom])

  useEffect(() => {
    function connect() {
      const wsUrl = baseUrl.replace(/^http/, 'ws') + '/ws'
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        onConnected?.()
        ws.send(JSON.stringify({
          type: 'auth',
          payload: { apiKey, projectId },
        }))
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'agent_result') {
            addMessage('agent', msg.payload.markdown || '', msg.payload.widgets || [])
            setSending(false)
          }
        } catch { /* ignore */ }
      }

      ws.onclose = () => {
        setConnected(false)
        onDisconnected?.()
        setTimeout(connect, 5000)
      }

      ws.onerror = () => {
        onError?.(new Error('WebSocket connection failed'))
      }
    }

    connect()

    return () => {
      const ws = wsRef.current
      if (ws) { ws.onclose = null; ws.close() }
    }
  }, [apiKey, projectId, baseUrl, addMessage, onConnected, onDisconnected, onError])

  const sendMessage = useCallback((text?: string) => {
    const content = (text || input).trim()
    if (!content || sending) return
    setInput('')
    addMessage('user', content)
    setSending(true)

    try {
      wsRef.current?.send(JSON.stringify({
        type: 'spawn',
        payload: { topic: content, projectId, scale, skills },
      }))
    } catch (e: any) {
      addMessage('agent', isJa ? `エラー: ${e.message}` : `Error: ${e.message}`)
      setSending(false)
      onError?.(e)
    }
  }, [input, sending, addMessage, projectId, scale, skills, isJa, onError])

  const formatTime = (d: Date) =>
    d.toLocaleTimeString(isJa ? 'ja-JP' : 'en-US', { hour: '2-digit', minute: '2-digit' })

  return (
    <div className={`wai-widget wai-theme-${theme} ${className || ''}`} style={style} data-locale={locale}>
      <div className="wai-widget-inner">
        {/* Header */}
        <div className="wai-header">
          <div className="wai-header-icon">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M8 2v4M8 10v4M2 8h4M10 8h4M4 4l2.5 2.5M9.5 9.5L12 12M12 4l-2.5 2.5M6.5 9.5L4 12" />
            </svg>
          </div>
          <div>
            <div className="wai-header-title">Work with AI</div>
            <div className={`wai-header-status ${connected ? 'wai-connected' : ''}`}>
              <span className="wai-status-dot" />
              {connected ? (isJa ? 'オンライン' : 'Online') : (isJa ? '接続中...' : 'Connecting...')}
            </div>
          </div>
        </div>

        {/* Messages */}
        <div ref={chatRef} className="wai-messages">
          {messages.length === 0 && !sending ? (
            <div className="wai-empty">
              <div className="wai-empty-icon">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M8 2v4M8 10v4M2 8h4M10 8h4M4 4l2.5 2.5M9.5 9.5L12 12M12 4l-2.5 2.5M6.5 9.5L4 12" />
                </svg>
              </div>
              <h3>Work with AI</h3>
              <p>{isJa ? 'プロジェクトについて何でも質問してください' : 'Ask anything about your project'}</p>
              <div className="wai-suggestions">
                {suggestions.map(s => (
                  <button key={s} className="wai-suggestion" onClick={() => sendMessage(s)}>{s}</button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {messages.map(msg => msg.role === 'user' ? (
                <div key={msg.id} className="wai-msg-user">
                  <div className="wai-bubble-user">
                    {msg.text}
                    <span className="wai-time">{formatTime(msg.timestamp)}</span>
                  </div>
                </div>
              ) : (
                <div key={msg.id} className="wai-msg-agent">
                  <div className="wai-agent-avatar">AI</div>
                  <div className="wai-agent-content">
                    {msg.text && (
                      <div className="wai-bubble-agent">
                        <pre>{msg.text}</pre>
                        <span className="wai-time">{formatTime(msg.timestamp)}</span>
                      </div>
                    )}
                    {msg.widgets?.map((w, idx) => (
                      <div key={idx} className="wai-widget-card" data-type={w.type}>
                        <div className="wai-widget-card-title">{w.title}</div>
                        <ul>
                          {w.items.map((item, i) => <li key={i}>{item}</li>)}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {sending && (
                <div className="wai-msg-agent">
                  <div className="wai-agent-avatar">AI</div>
                  <div className="wai-typing">
                    <div className="wai-typing-dots"><span /><span /><span /></div>
                    <span>{isJa ? '分析中...' : 'Analyzing...'}</span>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Watermark (free plan) */}
        {showWatermark && (
          <a href="https://workwithai.secretary.io" target="_blank" rel="noopener"
            style={{ display: 'block', textAlign: 'center', padding: '4px 0', fontSize: '10px', color: '#8A8A96', textDecoration: 'none', borderTop: '1px solid #E2E0DB', background: '#F3F1EC' }}>
            Powered by <strong>Secretary.io</strong>
          </a>
        )}

        {/* Input */}
        <div className="wai-input-bar">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            type="text"
            placeholder={placeholder || (isJa ? 'メッセージを入力...' : 'Type a message...')}
            disabled={sending}
            onKeyUp={e => e.key === 'Enter' && sendMessage()}
          />
          <button disabled={sending || !input.trim()} onClick={() => sendMessage()}>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M2 8h12M10 4l4 4-4 4" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}

export default WorkWithAI
