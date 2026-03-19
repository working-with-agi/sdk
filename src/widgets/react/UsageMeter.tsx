/**
 * @work-with-ai/react — UsageMeter
 *
 * Displays AI credit usage in real-time.
 * Fetches from /api/billing/quota and shows progress bars + remaining credits.
 *
 * Usage:
 *   <UsageMeter apiUrl="https://api.example.com" apiKey="wai_xxx" />
 */
import React, { useEffect, useState, useCallback } from 'react'

export interface UsageMeterProps {
  apiUrl?: string
  apiKey?: string
  theme?: 'light' | 'dark'
  locale?: 'ja' | 'en'
  refreshInterval?: number
  compact?: boolean
  onLoaded?: (data: QuotaData) => void
  onError?: (err: Error) => void
  onLimitWarning?: (remaining: number) => void
  className?: string
  style?: React.CSSProperties
}

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

const GUIDE_LABELS: Record<string, { ja: string; en: string }> = {
  meeting_summary: { ja: '議事録要約', en: 'Summary' },
  ai_chat: { ja: 'AI対話', en: 'AI chat' },
  action_item_extraction: { ja: 'アクション抽出', en: 'Actions' },
  cross_project_analysis: { ja: '横断分析', en: 'Analysis' },
  agenda_generation: { ja: 'アジェンダ', en: 'Agenda' },
}

function formatNum(n: number): string {
  if (n === -1) return '∞'
  return n.toLocaleString()
}

function barColor(percent: number): string {
  if (percent >= 90) return '#dc2626'
  if (percent >= 70) return '#d97706'
  return '#7c3aed'
}

export function UsageMeter({
  apiUrl = '',
  apiKey = '',
  theme = 'light',
  locale = 'ja',
  refreshInterval = 60_000,
  compact = false,
  onLoaded,
  onError,
  onLimitWarning,
  className,
  style,
}: UsageMeterProps) {
  const [data, setData] = useState<QuotaData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const isJa = locale === 'ja'

  const isDark = theme === 'dark'
  const bg = isDark ? '#1e1e2e' : '#ffffff'
  const border = isDark ? '#3a3a4e' : '#e2e0db'
  const text = isDark ? '#e0e0e8' : '#1a1a2e'
  const dim = isDark ? '#707080' : '#8a8a96'
  const barBg = isDark ? '#2a2a3e' : '#f3f1ec'

  const fetchUsage = useCallback(async () => {
    if (!apiUrl) return
    try {
      const res = await fetch(`${apiUrl}/api/billing/quota`, {
        headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
      })
      if (!res.ok) throw new Error(`${res.status}`)
      const json = await res.json()
      const usage = json.usage as QuotaData
      setData(usage)
      setLoading(false)
      onLoaded?.(usage)
      if (usage.ai_credits_remaining !== -1 && usage.ai_credits_remaining < 100) {
        onLimitWarning?.(usage.ai_credits_remaining)
      }
    } catch (e: any) {
      setError(e.message)
      setLoading(false)
      onError?.(e)
    }
  }, [apiUrl, apiKey, onLoaded, onError, onLimitWarning])

  useEffect(() => {
    fetchUsage()
    if (refreshInterval > 0) {
      const t = setInterval(fetchUsage, refreshInterval)
      return () => clearInterval(t)
    }
  }, [fetchUsage, refreshInterval])

  const creditPct = data && data.ai_credits_limit !== -1
    ? Math.min((data.ai_credits_used / data.ai_credits_limit) * 100, 100) : 0
  const recPct = data && data.recording_minutes_limit !== -1
    ? Math.min((data.recording_minutes_used / data.recording_minutes_limit) * 100, 100) : 0

  const containerStyle: React.CSSProperties = {
    background: bg, border: `1px solid ${border}`, borderRadius: 12,
    padding: compact ? 10 : 16, fontSize: 13, color: text,
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    ...style,
  }

  if (loading) return <div className={className} style={containerStyle}><div style={{ textAlign: 'center', color: dim, fontSize: 12, padding: '12px 0' }}>{isJa ? '読み込み中...' : 'Loading...'}</div></div>
  if (error) return <div className={className} style={containerStyle}><div style={{ textAlign: 'center', color: '#dc2626', fontSize: 12, padding: '12px 0' }}>{isJa ? 'データ取得に失敗しました' : 'Failed to load'}</div></div>
  if (!data) return null

  return (
    <div className={className} style={containerStyle}>
      {/* AI Credits */}
      <div style={{ marginBottom: compact ? 0 : 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 500, marginBottom: 6 }}>
          <span>{isJa ? 'AIクレジット' : 'AI Credits'}</span>
          <span style={{ fontWeight: 600 }}>{formatNum(data.ai_credits_used)} <span style={{ fontWeight: 400, color: dim }}>/ {formatNum(data.ai_credits_limit)}</span></span>
        </div>
        <div style={{ height: 6, background: barBg, borderRadius: 3, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${creditPct}%`, background: barColor(creditPct), borderRadius: 3, transition: 'width 0.5s ease' }} />
        </div>
        {!compact && data.ai_credits_remaining !== -1 && (
          <div style={{ fontSize: 11, color: dim, marginTop: 4 }}>
            {isJa ? `残り ${formatNum(data.ai_credits_remaining)} クレジット` : `${formatNum(data.ai_credits_remaining)} credits remaining`}
            {data.ai_credits_topup > 0 && <span style={{ color: '#7c3aed' }}> ({isJa ? `追加: ${formatNum(data.ai_credits_topup)}` : `+${formatNum(data.ai_credits_topup)} top-up`})</span>}
          </div>
        )}
      </div>

      {/* Recording */}
      {!compact && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, fontWeight: 500, marginBottom: 6 }}>
            <span>{isJa ? '録音時間' : 'Recording'}</span>
            <span style={{ fontWeight: 600 }}>{formatNum(data.recording_minutes_used)} <span style={{ fontWeight: 400, color: dim }}>/ {formatNum(data.recording_minutes_limit)} {isJa ? '分' : 'min'}</span></span>
          </div>
          <div style={{ height: 6, background: barBg, borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${recPct}%`, background: barColor(recPct), borderRadius: 3, transition: 'width 0.5s ease' }} />
          </div>
        </div>
      )}

      {/* Projects */}
      {!compact && (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 12 }}>
          <span style={{ fontWeight: 500 }}>{isJa ? 'プロジェクト' : 'Projects'}</span>
          <span style={{ fontWeight: 600 }}>{data.active_projects} / {formatNum(data.projects_limit)}</span>
        </div>
      )}

      {/* Cost guide */}
      {!compact && data.credit_cost_guide && (
        <div style={{ borderTop: `1px solid ${border}`, paddingTop: 10, marginTop: 12 }}>
          <div style={{ fontSize: 11, color: dim, marginBottom: 6 }}>{isJa ? '消費目安' : 'Cost guide'}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {Object.entries(data.credit_cost_guide).map(([op, cost]) => (
              <span key={op} style={{ fontSize: 10, color: dim, background: barBg, borderRadius: 4, padding: '2px 6px' }}>
                {GUIDE_LABELS[op]?.[locale] || op}: {cost}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default UsageMeter
