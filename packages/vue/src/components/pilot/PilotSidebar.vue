<template>
  <aside class="pilot-sidebar" :style="{ width: uiMode.sidebarWidth + 'px' }">
    <!-- Resize handle -->
    <div class="pilot-sidebar__resize" @mousedown="startResize" />

    <!-- Header with tabs and collapse -->
    <div class="pilot-sidebar__header">
      <div class="pilot-sidebar__tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="pilot-sidebar__tab"
          :class="{ 'pilot-sidebar__tab--active': uiMode.activeSidebarTab === tab.id }"
          @click="uiMode.setSidebarTab(tab.id)"
        >
          {{ tab.label }}
        </button>
      </div>
      <button class="pilot-sidebar__collapse" @click="uiMode.toggleSidebar" title="Collapse sidebar">
        <span class="collapse-icon">&#x276F;</span>
      </button>
    </div>

    <!-- Content area -->
    <div class="pilot-sidebar__content">
      <slot :active-tab="uiMode.activeSidebarTab">
        <!-- Default: render nothing; consumers provide tab content via slot -->
      </slot>
    </div>
  </aside>
</template>

<script setup lang="ts">
  import { useUIModeStore } from '../../stores/uiModeStore'

  const uiMode = useUIModeStore()

  const tabs = [
    { id: 'chat' as const, label: 'Chat' },
    { id: 'agents' as const, label: 'Agents' },
    { id: 'tasks' as const, label: 'Tasks' },
    { id: 'timeline' as const, label: 'Timeline' },
  ]

  function startResize(e: MouseEvent) {
    e.preventDefault()
    const startX = e.clientX
    const startWidth = uiMode.sidebarWidth

    function onMove(ev: MouseEvent) {
      const delta = startX - ev.clientX
      uiMode.setSidebarWidth(startWidth + delta)
    }

    function onUp() {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }
</script>

<style scoped>
  .pilot-sidebar {
    display: flex;
    flex-direction: column;
    background: #1a1d23;
    border-left: 1px solid #2d3139;
    position: relative;
    flex-shrink: 0;
    height: 100%;
  }

  .pilot-sidebar__resize {
    position: absolute;
    left: -3px;
    top: 0;
    bottom: 0;
    width: 6px;
    cursor: col-resize;
    z-index: 10;
  }

  .pilot-sidebar__resize:hover {
    background: rgba(88, 166, 255, 0.3);
  }

  .pilot-sidebar__header {
    display: flex;
    align-items: center;
    border-bottom: 1px solid #2d3139;
    padding: 0 4px;
    height: 36px;
    flex-shrink: 0;
  }

  .pilot-sidebar__tabs {
    display: flex;
    flex: 1;
    gap: 2px;
  }

  .pilot-sidebar__tab {
    background: none;
    border: none;
    color: #8b949e;
    font-size: 12px;
    padding: 6px 10px;
    cursor: pointer;
    border-radius: 4px;
    transition: color 0.15s, background 0.15s;
  }

  .pilot-sidebar__tab:hover {
    color: #c9d1d9;
    background: rgba(255, 255, 255, 0.05);
  }

  .pilot-sidebar__tab--active {
    color: #58a6ff;
    background: rgba(88, 166, 255, 0.1);
  }

  .pilot-sidebar__collapse {
    background: none;
    border: none;
    color: #8b949e;
    cursor: pointer;
    padding: 4px 6px;
    font-size: 12px;
    border-radius: 4px;
    flex-shrink: 0;
  }

  .pilot-sidebar__collapse:hover {
    color: #c9d1d9;
    background: rgba(255, 255, 255, 0.05);
  }

  .collapse-icon {
    display: inline-block;
  }

  .pilot-sidebar__content {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
</style>
