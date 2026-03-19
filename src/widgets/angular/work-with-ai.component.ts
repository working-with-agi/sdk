/**
 * @secretary-io/workwithai-angular
 *
 * Angular component for embedding the Work with AI chat widget.
 * Connects to Secretary.io AgentServer via WebSocket and provides
 * an interactive AI assistant powered by project data.
 *
 * Usage:
 *   <secretary-work-with-ai
 *     apiKey="your-api-key"
 *     projectId="proj_abc123"
 *     theme="light"
 *     [skills]="['risk_analysis', 'progress_summary']"
 *     locale="ja"
 *     (onMessage)="onMessage($event)"
 *   ></secretary-work-with-ai>
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
} from '@angular/core'

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

@Component({
  selector: 'secretary-work-with-ai',
  template: `
    <div [class]="'wai-widget wai-theme-' + theme" [attr.data-locale]="locale">
      <div class="wai-widget-inner">
        <!-- Header -->
        <div class="wai-header">
          <div class="wai-header-icon">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M8 2v4M8 10v4M2 8h4M10 8h4M4 4l2.5 2.5M9.5 9.5L12 12M12 4l-2.5 2.5M6.5 9.5L4 12" />
            </svg>
          </div>
          <div>
            <div class="wai-header-title">Work with AI</div>
            <div class="wai-header-status" [class.wai-connected]="connected">
              <span class="wai-status-dot"></span>
              {{ connected ? (isJa ? 'オンライン' : 'Online') : (isJa ? '接続中...' : 'Connecting...') }}
            </div>
          </div>
        </div>

        <!-- Messages -->
        <div #chatContainer class="wai-messages">
          <!-- Empty state -->
          <div *ngIf="messages.length === 0 && !sending" class="wai-empty">
            <div class="wai-empty-icon">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <path d="M8 2v4M8 10v4M2 8h4M10 8h4M4 4l2.5 2.5M9.5 9.5L12 12M12 4l-2.5 2.5M6.5 9.5L4 12" />
              </svg>
            </div>
            <h3>Work with AI</h3>
            <p>{{ isJa ? 'プロジェクトについて何でも質問してください' : 'Ask anything about your project' }}</p>
            <div class="wai-suggestions">
              <button
                *ngFor="let s of suggestions"
                class="wai-suggestion"
                (click)="sendMessage(s)"
              >
                {{ s }}
              </button>
            </div>
          </div>

          <!-- Message list -->
          <ng-container *ngFor="let msg of messages">
            <div *ngIf="msg.role === 'user'" class="wai-msg-user">
              <div class="wai-bubble-user">
                {{ msg.text }}
                <span class="wai-time">{{ formatTime(msg.timestamp) }}</span>
              </div>
            </div>
            <div *ngIf="msg.role === 'agent'" class="wai-msg-agent">
              <div class="wai-agent-avatar">AI</div>
              <div class="wai-agent-content">
                <div *ngIf="msg.text" class="wai-bubble-agent">
                  <pre>{{ msg.text }}</pre>
                  <span class="wai-time">{{ formatTime(msg.timestamp) }}</span>
                </div>
                <div
                  *ngFor="let w of msg.widgets"
                  class="wai-widget-card"
                  [attr.data-type]="w.type"
                >
                  <div class="wai-widget-card-title">{{ w.title }}</div>
                  <ul>
                    <li *ngFor="let item of w.items">{{ item }}</li>
                  </ul>
                </div>
              </div>
            </div>
          </ng-container>

          <!-- Typing indicator -->
          <div *ngIf="sending" class="wai-msg-agent">
            <div class="wai-agent-avatar">AI</div>
            <div class="wai-typing">
              <div class="wai-typing-dots"><span></span><span></span><span></span></div>
              <span>{{ isJa ? '分析中...' : 'Analyzing...' }}</span>
            </div>
          </div>
        </div>

        <!-- Watermark (free plan) -->
        <a *ngIf="showWatermark" href="https://workwithai.secretary.io" target="_blank" rel="noopener"
           style="display:block;text-align:center;padding:4px 0;font-size:10px;color:#8A8A96;text-decoration:none;border-top:1px solid #E2E0DB;background:#F3F1EC">
          Powered by <strong>Secretary.io</strong>
        </a>

        <!-- Input -->
        <div class="wai-input-bar">
          <input
            [(ngModel)]="input"
            type="text"
            [placeholder]="placeholder || (isJa ? 'メッセージを入力...' : 'Type a message...')"
            [disabled]="sending"
            (keyup.enter)="sendMessage()"
          />
          <button [disabled]="sending || !input.trim()" (click)="sendMessage()">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <path d="M2 8h12M10 4l4 4-4 4" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  `,
})
export class WorkWithAIComponent implements OnInit, OnDestroy {
  @Input() apiKey = ''
  @Input() projectId = ''
  @Input() theme: 'light' | 'dark' = 'light'
  @Input() skills: string[] = [
    'risk_analysis',
    'progress_summary',
    'comparative_analysis',
    'action_items',
    'timeline_forecast',
  ]
  @Input() locale: 'ja' | 'en' = 'ja'
  @Input() scale: 'le' | 'org' = 'le'
  @Input() baseUrl = 'https://api.secretary.io'
  @Input() placeholder = ''

  @Output() onMessage = new EventEmitter<Message>()
  @Output() onError = new EventEmitter<Error>()
  @Output() onConnected = new EventEmitter<void>()
  @Output() onDisconnected = new EventEmitter<void>()

  @ViewChild('chatContainer') chatContainer!: ElementRef<HTMLDivElement>

  messages: Message[] = []
  input = ''
  sending = false
  connected = false
  showWatermark = true

  private ws: WebSocket | null = null
  private msgCounter = 0

  get isJa(): boolean {
    return this.locale === 'ja'
  }

  get suggestions(): string[] {
    return this.isJa
      ? ['プロジェクトの進捗をまとめて', 'リスクを洗い出して', '次のアクションを提案して', 'タイムライン予測を見せて']
      : ['Summarize project progress', 'Identify risks', 'Suggest next actions', 'Show timeline forecast']
  }

  ngOnInit(): void {
    this.validateApiKey()
    this.connectWebSocket()
  }

  private validateApiKey(): void {
    fetch(`${this.baseUrl}/api/widget/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: this.apiKey, project_id: this.projectId }),
    })
      .then(r => r.ok ? r.json() : Promise.reject(new Error('Invalid API key')))
      .then(data => { this.showWatermark = data.watermark !== false })
      .catch(e => this.onError.emit(e))
  }

  ngOnDestroy(): void {
    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }
  }

  private connectWebSocket(): void {
    const wsUrl = this.baseUrl.replace(/^http/, 'ws') + '/ws'
    this.ws = new WebSocket(wsUrl)

    this.ws.onopen = () => {
      this.connected = true
      this.onConnected.emit()
      this.ws?.send(
        JSON.stringify({
          type: 'auth',
          payload: { apiKey: this.apiKey, projectId: this.projectId },
        })
      )
    }

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'agent_result') {
          this.addMessage('agent', msg.payload.markdown || '', msg.payload.widgets || [])
          this.sending = false
        }
      } catch {}
    }

    this.ws.onclose = () => {
      this.connected = false
      this.onDisconnected.emit()
      setTimeout(() => this.connectWebSocket(), 5000)
    }

    this.ws.onerror = () => {
      this.onError.emit(new Error('WebSocket connection failed'))
    }
  }

  private scrollToBottom(): void {
    requestAnimationFrame(() => {
      const el = this.chatContainer?.nativeElement
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    })
  }

  private addMessage(role: 'user' | 'agent', text: string, widgets?: Widget[]): Message {
    const msg: Message = {
      id: `msg-${++this.msgCounter}`,
      role,
      text,
      widgets,
      timestamp: new Date(),
    }
    this.messages.push(msg)
    this.scrollToBottom()
    this.onMessage.emit(msg)
    return msg
  }

  sendMessage(text?: string): void {
    const content = (text || this.input).trim()
    if (!content || this.sending) return
    this.input = ''
    this.addMessage('user', content)
    this.sending = true

    try {
      this.ws?.send(
        JSON.stringify({
          type: 'spawn',
          payload: {
            topic: content,
            projectId: this.projectId,
            scale: this.scale,
            skills: this.skills,
          },
        })
      )
    } catch (e: any) {
      this.addMessage('agent', this.isJa ? `エラー: ${e.message}` : `Error: ${e.message}`)
      this.sending = false
      this.onError.emit(e)
    }
  }

  formatTime(d: Date): string {
    return d.toLocaleTimeString(this.isJa ? 'ja-JP' : 'en-US', {
      hour: '2-digit',
      minute: '2-digit',
    })
  }
}
