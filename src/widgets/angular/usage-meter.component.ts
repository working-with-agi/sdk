/**
 * @work-with-ai/angular — UsageMeter
 *
 * Displays AI credit usage in real-time.
 *
 * Usage:
 *   <usage-meter apiUrl="https://api.example.com" apiKey="wai_xxx"></usage-meter>
 */
import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnInit,
  OnDestroy,
} from '@angular/core'

interface QuotaData {
  ai_credits_used: number
  ai_credits_limit: number
  ai_credits_base: number
  ai_credits_topup: number
  ai_credits_remaining: number
  recording_minutes_used: number
  recording_minutes_limit: number
  recording_minutes_remaining: number
  active_projects: number
  projects_limit: number
  credit_cost_guide?: Record<string, number>
}

@Component({
  selector: 'usage-meter',
  template: `
    <div [class]="'um-container um-theme-' + theme + (compact ? ' um-compact' : '')">
      <div *ngIf="loading" class="um-center um-dim">{{ isJa ? '読み込み中...' : 'Loading...' }}</div>
      <div *ngIf="!loading && errorMsg" class="um-center um-danger">{{ isJa ? 'データ取得に失敗しました' : 'Failed to load' }}</div>

      <ng-container *ngIf="!loading && !errorMsg && data">
        <!-- AI Credits -->
        <div class="um-section">
          <div class="um-label">
            <span>{{ isJa ? 'AIクレジット' : 'AI Credits' }}</span>
            <span class="um-bold">{{ fmt(data.ai_credits_used) }} <span class="um-dim">/ {{ fmt(data.ai_credits_limit) }}</span></span>
          </div>
          <div class="um-bar-bg"><div class="um-bar" [style.width.%]="creditPct" [style.background]="barColor(creditPct)"></div></div>
          <div *ngIf="!compact && data.ai_credits_remaining !== -1" class="um-remaining">
            {{ isJa ? '残り ' + fmt(data.ai_credits_remaining) + ' クレジット' : fmt(data.ai_credits_remaining) + ' credits remaining' }}
            <span *ngIf="data.ai_credits_topup > 0" class="um-topup">
              ({{ isJa ? '追加: ' + fmt(data.ai_credits_topup) : '+' + fmt(data.ai_credits_topup) + ' top-up' }})
            </span>
          </div>
        </div>

        <!-- Recording -->
        <div *ngIf="!compact" class="um-section">
          <div class="um-label">
            <span>{{ isJa ? '録音時間' : 'Recording' }}</span>
            <span class="um-bold">{{ fmt(data.recording_minutes_used) }} <span class="um-dim">/ {{ fmt(data.recording_minutes_limit) }} {{ isJa ? '分' : 'min' }}</span></span>
          </div>
          <div class="um-bar-bg"><div class="um-bar" [style.width.%]="recPct" [style.background]="barColor(recPct)"></div></div>
        </div>

        <!-- Projects -->
        <div *ngIf="!compact" class="um-projects">
          <span>{{ isJa ? 'プロジェクト' : 'Projects' }}</span>
          <span class="um-bold">{{ data.active_projects }} / {{ fmt(data.projects_limit) }}</span>
        </div>
      </ng-container>
    </div>
  `,
  styles: [`
    .um-container { background: #fff; border: 1px solid #e2e0db; border-radius: 12px; padding: 16px; font-size: 13px; color: #1a1a2e; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    .um-theme-dark { background: #1e1e2e; border-color: #3a3a4e; color: #e0e0e8; }
    .um-compact { padding: 10px; }
    .um-center { text-align: center; padding: 12px 0; font-size: 12px; }
    .um-dim { color: #8a8a96; }
    .um-theme-dark .um-dim { color: #707080; }
    .um-danger { color: #dc2626; }
    .um-section { margin-bottom: 12px; }
    .um-section:last-child { margin-bottom: 0; }
    .um-label { display: flex; justify-content: space-between; font-size: 12px; font-weight: 500; margin-bottom: 6px; }
    .um-bold { font-weight: 600; }
    .um-bar-bg { height: 6px; background: #f3f1ec; border-radius: 3px; overflow: hidden; }
    .um-theme-dark .um-bar-bg { background: #2a2a3e; }
    .um-bar { height: 100%; border-radius: 3px; transition: width 0.5s ease; }
    .um-remaining { font-size: 11px; color: #8a8a96; margin-top: 4px; }
    .um-topup { color: #7c3aed; }
    .um-projects { display: flex; justify-content: space-between; font-size: 12px; }
  `],
})
export class UsageMeterComponent implements OnInit, OnDestroy {
  @Input() apiUrl = ''
  @Input() apiKey = ''
  @Input() theme: 'light' | 'dark' = 'light'
  @Input() locale: 'ja' | 'en' = 'ja'
  @Input() refreshInterval = 60_000
  @Input() compact = false

  @Output() onLoaded = new EventEmitter<QuotaData>()
  @Output() onError = new EventEmitter<Error>()
  @Output() onLimitWarning = new EventEmitter<number>()

  data: QuotaData | null = null
  loading = true
  errorMsg = ''
  private timer: any = null

  get isJa(): boolean { return this.locale === 'ja' }

  get creditPct(): number {
    if (!this.data || this.data.ai_credits_limit === -1) return 0
    return Math.min((this.data.ai_credits_used / this.data.ai_credits_limit) * 100, 100)
  }

  get recPct(): number {
    if (!this.data || this.data.recording_minutes_limit === -1) return 0
    return Math.min((this.data.recording_minutes_used / this.data.recording_minutes_limit) * 100, 100)
  }

  fmt(n: number): string { return n === -1 ? '∞' : n.toLocaleString() }

  barColor(pct: number): string {
    if (pct >= 90) return '#dc2626'
    if (pct >= 70) return '#d97706'
    return '#7c3aed'
  }

  ngOnInit(): void {
    this.fetchUsage()
    if (this.refreshInterval > 0) {
      this.timer = setInterval(() => this.fetchUsage(), this.refreshInterval)
    }
  }

  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer)
  }

  async fetchUsage(): Promise<void> {
    if (!this.apiUrl) return
    try {
      const res = await fetch(`${this.apiUrl}/api/billing/quota`, {
        headers: this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {},
      })
      if (!res.ok) throw new Error(`${res.status}`)
      const json = await res.json()
      this.data = json.usage as QuotaData
      this.loading = false
      this.onLoaded.emit(this.data)
      if (this.data.ai_credits_remaining !== -1 && this.data.ai_credits_remaining < 100) {
        this.onLimitWarning.emit(this.data.ai_credits_remaining)
      }
    } catch (e: any) {
      this.errorMsg = e.message
      this.loading = false
      this.onError.emit(e)
    }
  }
}
