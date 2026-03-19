<template>
  <div ref="terminalEl" class="tmux-terminal" @click="handleClick"></div>
</template>

<script setup lang="ts">
  import { FitAddon } from '@xterm/addon-fit'
  import { Unicode11Addon } from '@xterm/addon-unicode11'
  import { WebLinksAddon } from '@xterm/addon-web-links'
  import { Terminal, type ITheme } from '@xterm/xterm'
  import '@xterm/xterm/css/xterm.css'
  import { onMounted, onUnmounted, ref, watch } from 'vue'
  import { useTmuxStore } from '../../stores/tmuxStore'

  const props = defineProps<{
    paneId: string
    isFocused: boolean
  }>()

  const emit = defineEmits<{
    focus: []
  }>()

  const terminalEl = ref<HTMLElement | null>(null)
  const terminal = ref<Terminal | null>(null)
  const fitAddon = ref<FitAddon | null>(null)
  const tmuxStore = useTmuxStore()

  let resizeObserver: ResizeObserver | null = null

  const theme: ITheme = {
    background: '#1e1e1e',
    foreground: '#ffffff',
    cursor: '#ffffff',
    cursorAccent: '#000000',
    selectionBackground: 'rgba(255, 255, 255, 0.3)',
    black: '#000000',
    red: '#cd3131',
    green: '#0dbc79',
    yellow: '#e5e510',
    blue: '#3b78ff',
    magenta: '#bc3fbc',
    cyan: '#0dc2c2',
    white: '#e5e5e5',
    brightBlack: '#666666',
    brightRed: '#f14c4c',
    brightGreen: '#23d18b',
    brightYellow: '#f5f543',
    brightBlue: '#3b8eea',
    brightMagenta: '#d670d6',
    brightCyan: '#29b8db',
    brightWhite: '#ffffff',
  }

  function handleClick() {
    emit('focus')
  }

  function handlePaneOutput(data: Uint8Array) {
    if (terminal.value) {
      terminal.value.write(data)
    }
  }

  onMounted(() => {
    if (!terminalEl.value) return

    terminal.value = new Terminal({
      convertEol: true,
      cursorBlink: true,
      disableStdin: false,
      scrollback: 5000,
      theme,
      allowProposedApi: true,
      fontSize: 13,
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
    })

    fitAddon.value = new FitAddon()
    terminal.value.loadAddon(fitAddon.value)
    terminal.value.loadAddon(new WebLinksAddon())
    terminal.value.loadAddon(new Unicode11Addon())

    terminal.value.open(terminalEl.value)
    fitAddon.value.fit()

    // Handle all input (keyboard, paste, IME) -> send to backend
    terminal.value.onData((data) => {
      tmuxStore.sendPaneInput(props.paneId, data)
    })

    // Handle terminal resize -> send to backend
    terminal.value.onResize((dims) => {
      tmuxStore.resizePanePty(props.paneId, dims.cols, dims.rows)
    })

    // Listen for output from this pane
    tmuxStore.onPaneOutput(props.paneId, handlePaneOutput)

    // Fit on container resize
    resizeObserver = new ResizeObserver(() => {
      if (fitAddon.value && terminal.value) {
        fitAddon.value.fit()
      }
    })
    resizeObserver.observe(terminalEl.value)

    // Initial resize notification
    if (terminal.value.cols && terminal.value.rows) {
      tmuxStore.resizePanePty(props.paneId, terminal.value.cols, terminal.value.rows)
    }
  })

  onUnmounted(() => {
    tmuxStore.offPaneOutput(props.paneId, handlePaneOutput)
    resizeObserver?.disconnect()
    if (terminal.value) {
      terminal.value.dispose()
      terminal.value = null
    }
  })

  watch(
    () => props.isFocused,
    (focused) => {
      if (focused) {
        terminal.value?.focus()
        setTimeout(() => fitAddon.value?.fit(), 50)
      }
    }
  )

  defineExpose({
    focus: () => terminal.value?.focus(),
    fit: () => fitAddon.value?.fit(),
  })
</script>

<style scoped>
  .tmux-terminal {
    width: 100%;
    height: 100%;
    background: #1e1e1e;
    overflow: hidden;
  }

  :deep(.xterm) {
    height: 100%;
    padding: 2px;
  }

  :deep(.xterm-viewport::-webkit-scrollbar) {
    width: 4px;
  }

  :deep(.xterm-viewport::-webkit-scrollbar-thumb) {
    background: #444;
    border-radius: 10px;
  }
</style>
