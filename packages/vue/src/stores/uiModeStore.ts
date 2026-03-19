import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export type InteractionMode = 'tmux' | 'pilot'

const STORAGE_KEYS = {
  interactionMode: 'aetherterm-interaction-mode',
  sidebarWidth: 'aetherterm-sidebar-width',
  sidebarCollapsed: 'aetherterm-sidebar-collapsed',
} as const

export const useUIModeStore = defineStore('uiMode', () => {
  const interactionMode = ref<InteractionMode>('tmux')
  const isTransitioning = ref(false)
  const sidebarWidth = ref(320)
  const isSidebarCollapsed = ref(false)
  const activeSidebarTab = ref<'chat' | 'agents' | 'tasks' | 'timeline'>('chat')

  // Getters
  const isTmuxMode = computed(() => interactionMode.value === 'tmux')
  const isPilotMode = computed(() => interactionMode.value === 'pilot')
  const showSidebar = computed(() => isPilotMode.value && !isSidebarCollapsed.value)
  const effectiveSidebarWidth = computed(() =>
    showSidebar.value ? sidebarWidth.value : 0
  )

  // Actions
  function setInteractionMode(mode: InteractionMode) {
    if (interactionMode.value === mode) return
    isTransitioning.value = true
    interactionMode.value = mode
    localStorage.setItem(STORAGE_KEYS.interactionMode, mode)
    setTimeout(() => {
      isTransitioning.value = false
    }, 250)
  }

  function toggleInteractionMode() {
    setInteractionMode(interactionMode.value === 'tmux' ? 'pilot' : 'tmux')
  }

  function setSidebarTab(tab: 'chat' | 'agents' | 'tasks' | 'timeline') {
    activeSidebarTab.value = tab
    // Auto-expand sidebar when selecting a tab
    if (isSidebarCollapsed.value) {
      isSidebarCollapsed.value = false
      localStorage.setItem(STORAGE_KEYS.sidebarCollapsed, 'false')
    }
  }

  function toggleSidebar() {
    isSidebarCollapsed.value = !isSidebarCollapsed.value
    localStorage.setItem(STORAGE_KEYS.sidebarCollapsed, String(isSidebarCollapsed.value))
  }

  function setSidebarWidth(width: number) {
    sidebarWidth.value = Math.max(240, Math.min(width, 480))
    localStorage.setItem(STORAGE_KEYS.sidebarWidth, String(sidebarWidth.value))
  }

  function loadFromStorage() {
    const savedMode = localStorage.getItem(STORAGE_KEYS.interactionMode)
    if (savedMode === 'tmux' || savedMode === 'pilot') {
      interactionMode.value = savedMode
    }

    const savedWidth = localStorage.getItem(STORAGE_KEYS.sidebarWidth)
    if (savedWidth) {
      sidebarWidth.value = Math.max(240, Math.min(Number(savedWidth) || 320, 480))
    }

    const savedCollapsed = localStorage.getItem(STORAGE_KEYS.sidebarCollapsed)
    if (savedCollapsed === 'true') {
      isSidebarCollapsed.value = true
    }
  }

  return {
    // State
    interactionMode,
    isTransitioning,
    sidebarWidth,
    isSidebarCollapsed,
    activeSidebarTab,

    // Getters
    isTmuxMode,
    isPilotMode,
    showSidebar,
    effectiveSidebarWidth,

    // Actions
    setInteractionMode,
    toggleInteractionMode,
    setSidebarTab,
    toggleSidebar,
    setSidebarWidth,
    loadFromStorage,
  }
})
