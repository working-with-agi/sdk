/**
 * Copy mode store for vi-style navigation and text selection.
 *
 * Activated by Ctrl+B [ in the keybinding store.
 * Provides scrollback navigation, search, and selection.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useTmuxCopyModeStore = defineStore('tmuxCopyMode', () => {
  const isActive = ref(false)
  const paneId = ref('')
  const scrollOffset = ref(0)
  const cursorLine = ref(0)
  const cursorCol = ref(0)

  // Selection
  const isSelecting = ref(false)
  const selectionStart = ref({ line: 0, col: 0 })
  const selectionEnd = ref({ line: 0, col: 0 })

  // Search
  const searchQuery = ref('')
  const searchActive = ref(false)
  const searchDirection = ref<'forward' | 'backward'>('forward')

  function enter(targetPaneId: string) {
    isActive.value = true
    paneId.value = targetPaneId
    scrollOffset.value = 0
    cursorLine.value = 0
    cursorCol.value = 0
    isSelecting.value = false
    searchActive.value = false
  }

  function exit() {
    isActive.value = false
    isSelecting.value = false
    searchActive.value = false
    paneId.value = ''
  }

  function handleKey(key: string): string | null {
    if (!isActive.value) return null

    // Search mode
    if (searchActive.value) {
      if (key === 'Enter') {
        searchActive.value = false
        return 'search_execute'
      }
      if (key === 'Escape') {
        searchActive.value = false
        searchQuery.value = ''
        return 'search_cancel'
      }
      if (key === 'Backspace') {
        searchQuery.value = searchQuery.value.slice(0, -1)
        return 'search_update'
      }
      if (key.length === 1) {
        searchQuery.value += key
        return 'search_update'
      }
      return null
    }

    // Vi-style navigation
    switch (key) {
      case 'q':
      case 'Escape':
        exit()
        return 'exit'

      // Movement
      case 'h':
      case 'ArrowLeft':
        cursorCol.value = Math.max(0, cursorCol.value - 1)
        return 'move'
      case 'j':
      case 'ArrowDown':
        cursorLine.value++
        return 'move'
      case 'k':
      case 'ArrowUp':
        cursorLine.value = Math.max(0, cursorLine.value - 1)
        return 'move'
      case 'l':
      case 'ArrowRight':
        cursorCol.value++
        return 'move'

      // Page movement
      case 'u': // Ctrl+U half page up
        scrollOffset.value = Math.max(0, scrollOffset.value - 12)
        return 'scroll'
      case 'd': // Ctrl+D half page down
        scrollOffset.value += 12
        return 'scroll'

      // Line movement
      case '0':
        cursorCol.value = 0
        return 'move'
      case '$':
        cursorCol.value = 999 // Will be clamped by renderer
        return 'move'
      case 'g':
        scrollOffset.value = 0
        cursorLine.value = 0
        return 'scroll'
      case 'G':
        scrollOffset.value = 999999 // Jump to bottom
        return 'scroll'

      // Selection
      case 'v':
        if (!isSelecting.value) {
          isSelecting.value = true
          selectionStart.value = { line: cursorLine.value, col: cursorCol.value }
          selectionEnd.value = { ...selectionStart.value }
        } else {
          isSelecting.value = false
        }
        return 'selection_toggle'
      case 'y':
        if (isSelecting.value) {
          selectionEnd.value = { line: cursorLine.value, col: cursorCol.value }
          return 'copy'
        }
        return null

      // Search
      case '/':
        searchActive.value = true
        searchDirection.value = 'forward'
        searchQuery.value = ''
        return 'search_start'
      case '?':
        searchActive.value = true
        searchDirection.value = 'backward'
        searchQuery.value = ''
        return 'search_start'
      case 'n':
        return 'search_next'
      case 'N':
        return 'search_prev'

      default:
        return null
    }
  }

  return {
    isActive,
    paneId,
    scrollOffset,
    cursorLine,
    cursorCol,
    isSelecting,
    selectionStart,
    selectionEnd,
    searchQuery,
    searchActive,
    searchDirection,
    enter,
    exit,
    handleKey,
  }
})
