<script setup lang="ts">
/**
 * @work-with-ai/vue — UsageMeter
 *
 * AIクレジットの使用量をリアルタイム表示するウィジェット。
 * /api/billing/quota エンドポイントからデータを取得し、
 * プログレスバーと残クレジットを表示します。
 *
 * Usage:
 *   <UsageMeter api-url="https://api.example.com" api-key="wai_xxx" />
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'

export interface UsageMeterProps {
  apiUrl?: string
  apiKey?: string
  theme?: 'light' | 'dark'
  locale?: 'ja' | 'en'
  refreshInterval?: number  // ms, 0 = no auto-refresh
  compact?: boolean
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

const props = withDefaults(defineProps<UsageMeterProps>(), {
  apiUrl: '',
  apiKey: '',
  theme: 'light',
  locale: 'ja',
  refreshInterval: 60_000,
  compact: false,
})

const emit = defineEmits<{
  loaded: [data: QuotaData]
  error: [err: Error]
  limitWarning: [remaining: number]
}>()

const data = ref<QuotaData | null>(null)
const loading = ref(true)
const error = ref('')
let timer: ReturnType<typeof setInterval> | null = null

const isJa = computed(() => props.locale === 'ja')

const creditPercent = computed(() => {
  if (!data.value || data.value.ai_credits_limit === -1) return 0
  return Math.min((data.value.ai_credits_used / data.value.ai_credits_limit) * 100, 100)
})

const recordingPercent = computed(() => {
  if (!data.value || data.value.recording_minutes_limit === -1) return 0
  return Math.min((data.value.recording_minutes_used / data.value.recording_minutes_limit) * 100, 100)
})

const creditBarColor = computed(() => {
  if (creditPercent.value >= 90) return 'um-bar-danger'
  if (creditPercent.value >= 70) return 'um-bar-warn'
  return 'um-bar-ok'
})

const recordingBarColor = computed(() => {
  if (recordingPercent.value >= 90) return 'um-bar-danger'
  if (recordingPercent.value >= 70) return 'um-bar-warn'
  return 'um-bar-ok'
})

function formatNum(n: number): string {
  if (n === -1) return '∞'
  return n.toLocaleString()
}

async function fetchUsage() {
  if (!props.apiUrl) return
  try {
    const res = await fetch(`${props.apiUrl}/api/billing/quota`, {
      headers: props.apiKey ? { 'Authorization': `Bearer ${props.apiKey}` } : {},
    })
    if (!res.ok) throw new Error(`${res.status}`)
    const json = await res.json()
    data.value = json.usage as QuotaData
    loading.value = false
    emit('loaded', data.value)

    // Warn if low
    if (data.value.ai_credits_remaining !== -1 && data.value.ai_credits_remaining < 100) {
      emit('limitWarning', data.value.ai_credits_remaining)
    }
  } catch (e: any) {
    error.value = e.message
    loading.value = false
    emit('error', e)
  }
}

onMounted(() => {
  fetchUsage()
  if (props.refreshInterval > 0) {
    timer = setInterval(fetchUsage, props.refreshInterval)
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

defineExpose({ refresh: fetchUsage })
</script>

<template>
  <div :class="['um-container', `um-theme-${theme}`, compact ? 'um-compact' : '']">
    <!-- Loading -->
    <div v-if="loading" class="um-loading">
      {{ isJa ? '読み込み中...' : 'Loading...' }}
    </div>

    <!-- Error -->
    <div v-else-if="error" class="um-error">
      {{ isJa ? 'データ取得に失敗しました' : 'Failed to load usage data' }}
    </div>

    <!-- Data -->
    <template v-else-if="data">
      <!-- AI Credits -->
      <div class="um-section">
        <div class="um-label">
          <span>{{ isJa ? 'AIクレジット' : 'AI Credits' }}</span>
          <span class="um-value">
            {{ formatNum(data.ai_credits_used) }}
            <span class="um-dim">/ {{ formatNum(data.ai_credits_limit) }}</span>
          </span>
        </div>
        <div class="um-bar-bg">
          <div :class="['um-bar', creditBarColor]" :style="{ width: `${creditPercent}%` }" />
        </div>
        <div v-if="!compact && data.ai_credits_remaining !== -1" class="um-remaining">
          {{ isJa ? `残り ${formatNum(data.ai_credits_remaining)} クレジット` : `${formatNum(data.ai_credits_remaining)} credits remaining` }}
          <span v-if="data.ai_credits_topup > 0" class="um-topup">
            ({{ isJa ? `追加: ${formatNum(data.ai_credits_topup)}` : `+${formatNum(data.ai_credits_topup)} top-up` }})
          </span>
        </div>
      </div>

      <!-- Recording (non-compact only) -->
      <div v-if="!compact" class="um-section">
        <div class="um-label">
          <span>{{ isJa ? '録音時間' : 'Recording' }}</span>
          <span class="um-value">
            {{ formatNum(data.recording_minutes_used) }}
            <span class="um-dim">/ {{ formatNum(data.recording_minutes_limit) }} {{ isJa ? '分' : 'min' }}</span>
          </span>
        </div>
        <div class="um-bar-bg">
          <div :class="['um-bar', recordingBarColor]" :style="{ width: `${recordingPercent}%` }" />
        </div>
      </div>

      <!-- Projects (non-compact only) -->
      <div v-if="!compact" class="um-section um-projects">
        <span class="um-label-inline">{{ isJa ? 'プロジェクト' : 'Projects' }}</span>
        <span class="um-value-inline">{{ data.active_projects }} / {{ formatNum(data.projects_limit) }}</span>
      </div>

      <!-- Credit cost guide (non-compact only) -->
      <div v-if="!compact && data.credit_cost_guide" class="um-guide">
        <div class="um-guide-title">{{ isJa ? '消費目安' : 'Cost guide' }}</div>
        <div class="um-guide-items">
          <span v-for="(cost, op) in data.credit_cost_guide" :key="op" class="um-guide-item">
            {{ op === 'meeting_summary' ? (isJa ? '議事録要約' : 'Summary')
             : op === 'ai_chat' ? (isJa ? 'AI対話' : 'AI chat')
             : op === 'action_item_extraction' ? (isJa ? 'アクション抽出' : 'Actions')
             : op === 'cross_project_analysis' ? (isJa ? '横断分析' : 'Analysis')
             : op === 'agenda_generation' ? (isJa ? 'アジェンダ' : 'Agenda')
             : op
            }}: {{ cost }}
          </span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.um-container {
  --um-bg: #ffffff;
  --um-border: #e2e0db;
  --um-text: #1a1a2e;
  --um-text-dim: #8a8a96;
  --um-bar-bg: #f3f1ec;
  --um-ok: #7c3aed;
  --um-warn: #d97706;
  --um-danger: #dc2626;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--um-bg);
  border: 1px solid var(--um-border);
  border-radius: 12px;
  padding: 16px;
  font-size: 13px;
  color: var(--um-text);
}
.um-theme-dark {
  --um-bg: #1e1e2e;
  --um-border: #3a3a4e;
  --um-text: #e0e0e8;
  --um-text-dim: #707080;
  --um-bar-bg: #2a2a3e;
}
.um-compact { padding: 10px; }
.um-compact .um-section { margin-bottom: 0; }

.um-loading, .um-error { text-align: center; color: var(--um-text-dim); padding: 12px 0; font-size: 12px; }
.um-error { color: var(--um-danger); }

.um-section { margin-bottom: 12px; }
.um-section:last-child { margin-bottom: 0; }

.um-label { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 12px; font-weight: 500; }
.um-value { font-weight: 600; }
.um-dim { font-weight: 400; color: var(--um-text-dim); }

.um-bar-bg { height: 6px; background: var(--um-bar-bg); border-radius: 3px; overflow: hidden; }
.um-bar { height: 100%; border-radius: 3px; transition: width 0.5s ease; }
.um-bar-ok { background: var(--um-ok); }
.um-bar-warn { background: var(--um-warn); }
.um-bar-danger { background: var(--um-danger); }

.um-remaining { font-size: 11px; color: var(--um-text-dim); margin-top: 4px; }
.um-topup { color: var(--um-ok); }

.um-projects { display: flex; justify-content: space-between; align-items: center; font-size: 12px; }
.um-label-inline { font-weight: 500; }
.um-value-inline { font-weight: 600; }

.um-guide { border-top: 1px solid var(--um-border); padding-top: 10px; margin-top: 12px; }
.um-guide-title { font-size: 11px; color: var(--um-text-dim); margin-bottom: 6px; }
.um-guide-items { display: flex; flex-wrap: wrap; gap: 6px; }
.um-guide-item {
  font-size: 10px; color: var(--um-text-dim);
  background: var(--um-bar-bg); border-radius: 4px; padding: 2px 6px;
}
</style>
