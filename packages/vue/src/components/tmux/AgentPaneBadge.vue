<template>
  <div
    v-if="paneRole"
    class="agent-pane-badge"
    :class="statusClass"
    @click.stop="handleClick"
  >
    <span v-if="hasActiveTask" class="pulse-dot"></span>
    <span class="badge-label">[{{ paneRole }}]</span>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useAgentMessagingStore } from '../../stores/agentMessagingStore'
  import { useAgentTaskStore } from '../../stores/agentTaskStore'
  import { useTmuxStore } from '../../stores/tmuxStore'
  import { useUIModeStore } from '../../stores/uiModeStore'

  const props = defineProps<{
    paneId: string
  }>()

  const tmuxStore = useTmuxStore()
  const messagingStore = useAgentMessagingStore()
  const taskStore = useAgentTaskStore()
  const uiModeStore = useUIModeStore()

  const pane = computed(() => {
    const win = tmuxStore.activeWindow
    return win?.panes[props.paneId] || null
  })

  const paneRole = computed(() => pane.value?.role || '')

  const agentStatus = computed(() => {
    if (!paneRole.value) return null
    // Find agent by matching role to agent id
    const agents = messagingStore.agentList
    return agents.find((a) => a.id === paneRole.value) || null
  })

  const hasActiveTask = computed(() => {
    return taskStore.inProgressTasks.some(
      (t) => t.owner === paneRole.value
    )
  })

  const statusClass = computed(() => {
    if (pane.value?.status === 'blocked') return 'status-blocked'
    if (agentStatus.value && !agentStatus.value.isIdle) return 'status-busy'
    return 'status-idle'
  })

  function handleClick() {
    if (uiModeStore.isPilotMode) {
      uiModeStore.setSidebarTab('agents')
    }
  }
</script>

<style scoped>
  .agent-pane-badge {
    position: absolute;
    top: 4px;
    left: 4px;
    z-index: 15;
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 10px;
    font-weight: 700;
    cursor: pointer;
    user-select: none;
    backdrop-filter: blur(4px);
    transition: opacity 0.15s;
  }

  .agent-pane-badge:hover {
    opacity: 1 !important;
  }

  .status-idle {
    background: rgba(76, 175, 80, 0.2);
    color: #4caf50;
    border: 1px solid rgba(76, 175, 80, 0.3);
  }

  .status-busy {
    background: rgba(255, 152, 0, 0.2);
    color: #ff9800;
    border: 1px solid rgba(255, 152, 0, 0.3);
  }

  .status-blocked {
    background: rgba(244, 67, 54, 0.2);
    color: #f44336;
    border: 1px solid rgba(244, 67, 54, 0.3);
  }

  .pulse-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    animation: pulse 1.5s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  .badge-label {
    line-height: 1;
  }
</style>
