<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="context-menu-backdrop"
      @mousedown.self="close"
      @contextmenu.prevent
    >
      <div
        ref="menuEl"
        class="context-menu"
        :style="menuPosition"
        @contextmenu.prevent
      >
        <div class="menu-header">
          <span class="menu-title">Pane {{ paneLabel }}</span>
        </div>

        <div class="menu-separator"></div>

        <!-- Split operations -->
        <div class="menu-item" @click="action('split_h')">
          <span class="menu-icon">&#9472;</span>
          <span class="menu-label">Split Horizontal</span>
          <span class="menu-shortcut">Ctrl+B "</span>
        </div>
        <div class="menu-item" @click="action('split_v')">
          <span class="menu-icon">&#9474;</span>
          <span class="menu-label">Split Vertical</span>
          <span class="menu-shortcut">Ctrl+B %</span>
        </div>

        <div class="menu-separator"></div>

        <!-- Zoom -->
        <div class="menu-item" @click="action('zoom')">
          <span class="menu-icon">{{ isZoomed ? '&#9724;' : '&#9723;' }}</span>
          <span class="menu-label">{{ isZoomed ? 'Unzoom' : 'Zoom Pane' }}</span>
          <span class="menu-shortcut">Ctrl+B z</span>
        </div>

        <!-- Copy mode -->
        <div class="menu-item" @click="action('copy_mode')">
          <span class="menu-icon">&#128203;</span>
          <span class="menu-label">Copy Mode</span>
          <span class="menu-shortcut">Ctrl+B [</span>
        </div>

        <div class="menu-separator"></div>

        <!-- Agent view options (only if pane has a role) -->
        <template v-if="paneHasRole">
          <div class="menu-group-label">Agent</div>
          <div class="menu-item" @click="viewAgentMessages">
            <span class="menu-icon">&#9993;</span>
            <span class="menu-label">View Agent Messages</span>
          </div>
          <div class="menu-item" @click="viewAgentTasks">
            <span class="menu-icon">&#9745;</span>
            <span class="menu-label">View Agent Tasks</span>
          </div>
        </template>

        <div class="menu-separator"></div>

        <!-- Window operations -->
        <div class="menu-item" @click="action('rename_window')">
          <span class="menu-icon">&#9998;</span>
          <span class="menu-label">Rename Window</span>
          <span class="menu-shortcut">Ctrl+B ,</span>
        </div>
        <div class="menu-item" @click="action('new_window')">
          <span class="menu-icon">+</span>
          <span class="menu-label">New Window</span>
          <span class="menu-shortcut">Ctrl+B c</span>
        </div>

        <div class="menu-separator"></div>

        <!-- Close -->
        <div class="menu-item danger" @click="action('close_pane')">
          <span class="menu-icon">&#10005;</span>
          <span class="menu-label">Close Pane</span>
          <span class="menu-shortcut">Ctrl+B x</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
  import { computed, nextTick, ref, watch } from 'vue'
  import { useTmuxStore } from '../../stores/tmuxStore'
  import { useUIModeStore } from '../../stores/uiModeStore'

  const props = defineProps<{
    visible: boolean
    x: number
    y: number
    paneId: string
  }>()

  const emit = defineEmits<{
    close: []
    action: [type: string]
  }>()

  const tmuxStore = useTmuxStore()
  const uiModeStore = useUIModeStore()
  const menuEl = ref<HTMLElement | null>(null)

  const isZoomed = computed(() => tmuxStore.zoomedPaneId === props.paneId)

  const paneHasRole = computed(() => {
    const win = tmuxStore.activeWindow
    const pane = win?.panes[props.paneId]
    return !!pane?.role
  })

  const paneLabel = computed(() => {
    const win = tmuxStore.activeWindow
    if (!win) return ''
    const paneIds = Object.keys(win.panes)
    const idx = paneIds.indexOf(props.paneId)
    return idx >= 0 ? `#${idx}` : ''
  })

  const menuPosition = computed(() => {
    return {
      left: `${props.x}px`,
      top: `${props.y}px`,
    }
  })

  // Adjust position if menu overflows viewport
  watch(() => props.visible, async (vis) => {
    if (!vis) return
    await nextTick()
    if (!menuEl.value) return
    const rect = menuEl.value.getBoundingClientRect()
    const vw = window.innerWidth
    const vh = window.innerHeight
    if (rect.right > vw) {
      menuEl.value.style.left = `${props.x - rect.width}px`
    }
    if (rect.bottom > vh) {
      menuEl.value.style.top = `${props.y - rect.height}px`
    }
  })

  function close() {
    emit('close')
  }

  function action(type: string) {
    emit('action', type)
    close()
  }

  function viewAgentMessages() {
    uiModeStore.setInteractionMode('pilot')
    uiModeStore.setSidebarTab('agents')
    close()
  }

  function viewAgentTasks() {
    uiModeStore.setInteractionMode('pilot')
    uiModeStore.setSidebarTab('tasks')
    close()
  }
</script>

<style scoped>
  .context-menu-backdrop {
    position: fixed;
    inset: 0;
    z-index: 9999;
  }

  .context-menu {
    position: fixed;
    min-width: 220px;
    max-width: 280px;
    background: #1c1e24;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 4px 0;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(16px);
    animation: menuFadeIn 0.1s ease-out;
    z-index: 10000;
  }

  @keyframes menuFadeIn {
    from {
      opacity: 0;
      transform: scale(0.95);
    }
    to {
      opacity: 1;
      transform: scale(1);
    }
  }

  .menu-header {
    padding: 6px 12px 4px;
  }

  .menu-title {
    font-size: 10px;
    font-weight: 700;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .menu-separator {
    height: 1px;
    background: rgba(255, 255, 255, 0.08);
    margin: 4px 8px;
  }

  .menu-group-label {
    font-size: 10px;
    font-weight: 600;
    color: #666;
    padding: 4px 12px 2px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }

  .menu-item {
    display: flex;
    align-items: center;
    padding: 6px 12px;
    cursor: pointer;
    transition: background 0.1s;
    gap: 10px;
  }

  .menu-item:hover {
    background: rgba(99, 102, 241, 0.15);
  }

  .menu-item.selected {
    background: rgba(76, 175, 80, 0.1);
  }

  .menu-item.selected .menu-label {
    color: #4caf50;
    font-weight: 600;
  }

  .menu-item.danger:hover {
    background: rgba(244, 67, 54, 0.15);
  }

  .menu-item.danger .menu-label {
    color: #f44336;
  }

  .menu-item.danger .menu-icon {
    color: #f44336;
  }

  .menu-icon {
    width: 16px;
    text-align: center;
    font-size: 12px;
    color: #888;
    flex-shrink: 0;
  }

  .menu-label {
    flex: 1;
    font-size: 12px;
    color: #ddd;
  }

  .menu-shortcut {
    font-size: 10px;
    color: #555;
    font-family: 'JetBrains Mono', monospace;
    flex-shrink: 0;
  }
</style>
