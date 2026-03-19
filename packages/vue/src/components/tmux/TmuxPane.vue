<template>
  <div
    class="tmux-pane"
    :class="{
      active: isActive,
      exited: pane?.status === 'exited',
      blocked: pane?.status === 'blocked',
    }"
    @mousedown="handleFocus"
    @contextmenu.prevent="openContextMenu"
  >
    <TmuxTerminal :pane-id="paneId" :is-focused="isActive" @focus="handleFocus" />
    <AgentPaneBadge :pane-id="paneId" />
    <div v-if="pane?.status === 'exited'" class="pane-exit-overlay">
      <span>Pane exited ({{ pane.exit_code }})</span>
    </div>
    <div v-if="pane?.status === 'blocked'" class="pane-blocked-indicator">
      BLOCKED
    </div>

    <!-- Context menu -->
    <TmuxContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :pane-id="paneId"
      @close="contextMenu.visible = false"
      @action="handleContextAction"
    />
  </div>
</template>

<script setup lang="ts">
  import { computed, reactive } from 'vue'
  import { useTmuxCopyModeStore } from '../../stores/tmuxCopyModeStore'
  import { useTmuxStore } from '../../stores/tmuxStore'
  import AgentPaneBadge from './AgentPaneBadge.vue'
  import TmuxContextMenu from './TmuxContextMenu.vue'
  import TmuxTerminal from './TmuxTerminal.vue'

  const props = defineProps<{
    paneId: string
  }>()

  const tmuxStore = useTmuxStore()
  const copyModeStore = useTmuxCopyModeStore()

  const contextMenu = reactive({ visible: false, x: 0, y: 0 })

  const isActive = computed(() => tmuxStore.activePaneId === props.paneId)

  const pane = computed(() => {
    const win = tmuxStore.activeWindow
    return win?.panes[props.paneId] || null
  })

  function handleFocus() {
    tmuxStore.focusPane(props.paneId)
  }

  function openContextMenu(e: MouseEvent) {
    contextMenu.x = e.clientX
    contextMenu.y = e.clientY
    contextMenu.visible = true
  }

  function handleContextAction(type: string) {
    switch (type) {
      case 'split_h':
        tmuxStore.splitPane('h')
        break
      case 'split_v':
        tmuxStore.splitPane('v')
        break
      case 'close_pane':
        tmuxStore.closePane(props.paneId)
        break
      case 'zoom':
        tmuxStore.toggleZoom(props.paneId)
        break
      case 'copy_mode':
        copyModeStore.enter(props.paneId)
        break
      case 'rename_window': {
        const event = new CustomEvent('tmux-rename-window', { bubbles: true })
        document.dispatchEvent(event)
        break
      }
      case 'new_window':
        tmuxStore.createWindow()
        break
    }
  }
</script>

<style scoped>
  .tmux-pane {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
    border: 1px solid #333;
    transition: border-color 0.15s;
  }

  .tmux-pane.active {
    border-color: #4caf50;
  }

  .tmux-pane.exited {
    opacity: 0.6;
  }

  .tmux-pane.blocked {
    border-color: #f44336;
  }

  .pane-exit-overlay {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: rgba(0, 0, 0, 0.8);
    color: #888;
    padding: 4px 8px;
    font-size: 11px;
    text-align: center;
  }

  .pane-blocked-indicator {
    position: absolute;
    top: 4px;
    right: 4px;
    background: #f44336;
    color: white;
    font-size: 9px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 2px;
    letter-spacing: 0.5px;
  }
</style>
