<template>
  <div class="tmux-status-bar">
    <div class="status-left">
      <span
        class="mode-indicator"
        :class="uiModeStore.isTmuxMode ? 'mode-tmux' : 'mode-pilot'"
        @click="uiModeStore.toggleInteractionMode()"
        :title="`Switch to ${uiModeStore.isTmuxMode ? 'pilot' : 'tmux'} mode`"
      >
        [{{ uiModeStore.interactionMode }}]
      </span>
      <span class="session-name">[{{ sessionName }}]</span>
    </div>
    <div class="status-center">
      <span
        v-for="win in windowList"
        :key="win.window_id"
        class="window-item"
        :class="{ active: win.active }"
        @click="selectWindow(win.window_id)"
      >
        {{ win.index }}:{{ win.name }}
        <span v-if="win.pane_count > 1" class="pane-count">({{ win.pane_count }})</span>
      </span>
    </div>
    <div class="status-right">
      <!-- Role labels from current window panes -->
      <span v-if="paneRoles.length > 0" class="role-labels">
        <span
          v-for="role in paneRoles"
          :key="role"
          class="role-label"
          @click="openAgentSidebar"
          title="View agent details"
        >
          [{{ role }}]
        </span>
      </span>
      <span v-if="paneRole" class="pane-role">[{{ paneRole }}]</span>
      <span class="pane-info">{{ paneInfo }}</span>
      <!-- Unread message badge -->
      <span v-if="totalUnread > 0" class="unread-badge" :title="`${totalUnread} unread messages`">
        {{ totalUnread > 99 ? '99+' : totalUnread }}
      </span>
      <span class="clock">{{ clock }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, onUnmounted, ref } from 'vue'
  import { useAgentMessagingStore } from '../../stores/agentMessagingStore'
  import { useTmuxStore } from '../../stores/tmuxStore'
  import { useUIModeStore } from '../../stores/uiModeStore'

  const tmuxStore = useTmuxStore()
  const messagingStore = useAgentMessagingStore()
  const uiModeStore = useUIModeStore()
  const clock = ref('')
  let clockTimer: ReturnType<typeof setInterval> | null = null

  const sessionName = computed(() => tmuxStore.session?.name || 'tmux')
  const totalUnread = computed(() => messagingStore.totalUnread)

  const windowList = computed(() => {
    return tmuxStore.windowList.map((w) => ({
      window_id: w.window_id,
      index: w.window_index,
      name: w.name,
      pane_count: Object.keys(w.panes).length,
      active: w.window_id === tmuxStore.session?.active_window_id,
    }))
  })

  const paneRoles = computed(() => {
    const win = tmuxStore.activeWindow
    if (!win) return []
    const roles: string[] = []
    for (const pane of Object.values(win.panes)) {
      if (pane.role) {
        roles.push(pane.role)
      }
    }
    return roles
  })

  const paneInfo = computed(() => {
    const win = tmuxStore.activeWindow
    if (!win) return ''
    const pane = win.panes[win.active_pane_id]
    if (!pane) return ''
    return `${pane.cols}x${pane.rows}`
  })

  const paneRole = computed(() => {
    const win = tmuxStore.activeWindow
    if (!win) return ''
    const pane = win.panes[win.active_pane_id]
    return pane?.role || ''
  })

  function selectWindow(windowId: string) {
    tmuxStore.selectWindow(windowId)
  }

  function openAgentSidebar() {
    uiModeStore.setInteractionMode('pilot')
    uiModeStore.setSidebarTab('agents')
  }

  function updateClock() {
    const now = new Date()
    clock.value = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  onMounted(() => {
    updateClock()
    clockTimer = setInterval(updateClock, 30000)
  })

  onUnmounted(() => {
    if (clockTimer) clearInterval(clockTimer)
  })
</script>

<style scoped>
  .tmux-status-bar {
    height: 22px;
    background: #005f00;
    color: #ffffff;
    display: flex;
    align-items: center;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
    flex-shrink: 0;
    padding: 0 6px;
    user-select: none;
  }

  .status-left {
    flex-shrink: 0;
    margin-right: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .mode-indicator {
    font-weight: 700;
    cursor: pointer;
    transition: opacity 0.15s;
  }

  .mode-indicator:hover {
    opacity: 0.8;
  }

  .mode-tmux {
    color: #4caf50;
  }

  .mode-pilot {
    color: #a855f7;
  }

  .session-name {
    color: #00ff00;
    font-weight: 700;
  }

  .status-center {
    flex: 1;
    display: flex;
    gap: 4px;
    overflow-x: auto;
  }

  .status-center::-webkit-scrollbar {
    display: none;
  }

  .window-item {
    padding: 0 6px;
    cursor: pointer;
    white-space: nowrap;
    color: #aaffaa;
  }

  .window-item:hover {
    background: rgba(255, 255, 255, 0.1);
  }

  .window-item.active {
    background: #008800;
    color: #ffffff;
    font-weight: 700;
  }

  .pane-count {
    font-size: 10px;
    opacity: 0.7;
  }

  .status-right {
    flex-shrink: 0;
    display: flex;
    gap: 12px;
    margin-left: 8px;
  }

  .role-labels {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .role-label {
    color: #a855f7;
    font-weight: 600;
    font-size: 11px;
    cursor: pointer;
    transition: opacity 0.15s;
  }

  .role-label:hover {
    opacity: 0.7;
  }

  .pane-role {
    color: #ffff00;
    font-weight: 700;
  }

  .pane-info {
    opacity: 0.7;
  }

  .clock {
    opacity: 0.8;
  }

  .unread-badge {
    background: #f44336;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    min-width: 16px;
    height: 16px;
    border-radius: 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0 4px;
    line-height: 1;
  }
</style>
