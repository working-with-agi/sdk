/**
 * @work-with-ai/angular
 *
 * Angular component that connects to AgentServer (AetherTerm) and provides
 * an xterm.js terminal running an AI agent session.
 *
 * Usage:
 *   <work-with-ai
 *     agentServerUrl="ws://localhost:57575"
 *     [context]="{ projects: [...] }"
 *     [skills]="['secretary']"
 *     locale="ja"
 *   ></work-with-ai>
 */
import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnInit,
  OnDestroy,
  ViewChild,
  ElementRef,
  AfterViewInit,
} from '@angular/core'
import { Terminal, type ITheme } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import ReconnectingWebSocket from 'reconnecting-websocket'

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

@Component({
  selector: 'work-with-ai',
  template: `
    <div [class]="'wai-container wai-theme-' + theme">
      <!-- Header -->
      <div class="wai-header">
        <div class="wai-header-icon">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M8 2v4M8 10v4M2 8h4M10 8h4M4 4l2.5 2.5M9.5 9.5L12 12M12 4l-2.5 2.5M6.5 9.5L4 12" />
          </svg>
        </div>
        <div>
          <div class="wai-header-title">Work with AI</div>
          <div class="wai-header-status" [class.wai-active]="status === 'session'">
            <span class="wai-status-dot"></span>
            {{ statusText }}
          </div>
        </div>
      </div>
      <!-- Terminal -->
      <div #terminalEl class="wai-terminal"></div>
    </div>
  `,
  styles: [`
    .wai-container { border: 1px solid #e2e0db; border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; height: 500px; }
    .wai-theme-dark { border-color: #3a3a4e; }
    .wai-header { display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 1px solid #e2e0db; background: #f5f3ff; flex-shrink: 0; }
    .wai-theme-dark .wai-header { background: #2a2a3e; border-color: #3a3a4e; }
    .wai-header-icon { width: 32px; height: 32px; border-radius: 8px; background: #7c3aed; color: white; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
    .wai-header-icon svg { width: 16px; height: 16px; }
    .wai-header-title { font-size: 13px; font-weight: 600; color: #1a1a2e; }
    .wai-theme-dark .wai-header-title { color: #e0e0e8; }
    .wai-header-status { font-size: 11px; color: #8a8a96; display: flex; align-items: center; gap: 4px; }
    .wai-header-status.wai-active { color: #059669; }
    .wai-status-dot { width: 6px; height: 6px; border-radius: 50%; background: #8a8a96; }
    .wai-active .wai-status-dot { background: #059669; }
    .wai-terminal { flex: 1; background: #1e1e1e; overflow: hidden; }
    .wai-theme-light .wai-terminal { background: #ffffff; }
    :host ::ng-deep .xterm { height: 100%; padding: 4px; }
    :host ::ng-deep .xterm-viewport::-webkit-scrollbar { width: 6px; }
    :host ::ng-deep .xterm-viewport::-webkit-scrollbar-thumb { background: #555; border-radius: 3px; }
  `],
})
export class WorkWithAIComponent implements OnInit, OnDestroy, AfterViewInit {
  @Input() agentServerUrl = 'ws://localhost:57575'
  @Input() apiKey = ''
  @Input() context: Record<string, any> = {}
  @Input() skills: string[] = []
  @Input() locale: 'ja' | 'en' = 'ja'
  @Input() theme: 'light' | 'dark' = 'dark'
  @Input() fontSize = 13

  @Output() onConnected = new EventEmitter<void>()
  @Output() onDisconnected = new EventEmitter<void>()
  @Output() onSessionCreated = new EventEmitter<string>()
  @Output() onError = new EventEmitter<Error>()

  @ViewChild('terminalEl') terminalEl!: ElementRef<HTMLDivElement>

  status: 'connecting' | 'connected' | 'session' | 'error' = 'connecting'

  private terminal: Terminal | null = null
  private fitAddon: FitAddon | null = null
  private ws: ReconnectingWebSocket | null = null
  private paneId = ''
  private resizeObserver: ResizeObserver | null = null

  get isJa(): boolean { return this.locale === 'ja' }

  get statusText(): string {
    if (this.status === 'session') return this.isJa ? 'セッション中' : 'Session active'
    if (this.status === 'connected') return this.isJa ? '接続済み' : 'Connected'
    return this.isJa ? '接続中...' : 'Connecting...'
  }

  ngOnInit(): void {}

  ngAfterViewInit(): void {
    this.initTerminal()
    this.connect()
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect()
    this.terminal?.dispose()
    this.terminal = null
    if (this.ws) { this.ws.close(); this.ws = null }
  }

  private initTerminal(): void {
    if (!this.terminalEl?.nativeElement) return

    this.terminal = new Terminal({
      convertEol: true, cursorBlink: true, disableStdin: false, scrollback: 10000,
      theme: this.theme === 'light' ? lightTheme : darkTheme,
      allowProposedApi: true, fontSize: this.fontSize,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
    })

    this.fitAddon = new FitAddon()
    this.terminal.loadAddon(this.fitAddon)
    this.terminal.loadAddon(new WebLinksAddon())

    this.terminal.open(this.terminalEl.nativeElement)
    this.fitAddon.fit()

    this.terminal.onData((data: string) => this.sendInput(data))
    this.terminal.onResize(({ cols, rows }) => this.sendResize(cols, rows))

    this.resizeObserver = new ResizeObserver(() => this.fitAddon?.fit())
    this.resizeObserver.observe(this.terminalEl.nativeElement)
  }

  private connect(): void {
    const url = `${this.agentServerUrl}/ws/tmux/work-with-ai`
    this.ws = new ReconnectingWebSocket(url, [], { maxRetries: 10, connectionTimeout: 4000 })
    this.ws.binaryType = 'arraybuffer'

    this.ws.onopen = () => {
      this.status = 'connected'
      this.onConnected.emit()
      this.ws?.send(JSON.stringify({
        type: 'create_session',
        payload: { api_key: this.apiKey, skills: this.skills, context: this.context, locale: this.locale },
      }))
    }

    this.ws.onmessage = (event: MessageEvent) => {
      if (typeof event.data === 'string') {
        this.handleTextMessage(event.data)
      } else {
        this.handleBinaryMessage(event.data as ArrayBuffer)
      }
    }

    this.ws.onclose = () => { this.status = 'connecting'; this.onDisconnected.emit() }
    this.ws.onerror = () => { this.onError.emit(new Error('AgentServer connection failed')) }
  }

  private handleTextMessage(text: string): void {
    try {
      const msg = JSON.parse(text)
      if (msg.type === 'state_sync' || msg.type === 'session_created') {
        const session = msg.session || msg
        if (session.panes?.length > 0) this.paneId = session.panes[0].pane_id || ''
        this.status = 'session'
        this.onSessionCreated.emit(session.session_id || '')
      }
      if (msg.type === 'pane_exited') this.status = 'connected'
    } catch { /* ignore */ }
  }

  private handleBinaryMessage(buffer: ArrayBuffer): void {
    const view = new Uint8Array(buffer)
    if (view.length < 2) return
    const paneIdLen = view[0]
    if (view.length < 1 + paneIdLen) return
    this.terminal?.write(view.slice(1 + paneIdLen))
  }

  private sendInput(data: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN || !this.paneId) return
    const paneBytes = new TextEncoder().encode(this.paneId)
    const dataBytes = new TextEncoder().encode(data)
    const frame = new Uint8Array(1 + paneBytes.length + dataBytes.length)
    frame[0] = paneBytes.length
    frame.set(paneBytes, 1)
    frame.set(dataBytes, 1 + paneBytes.length)
    this.ws.send(frame.buffer)
  }

  private sendResize(cols: number, rows: number): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN || !this.paneId) return
    this.ws.send(JSON.stringify({ type: 'pane_resize', pane_id: this.paneId, cols, rows }))
  }
}
