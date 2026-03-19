<template>
  <div v-if="layout" class="tmux-pane-layout" :class="layoutClass">
    <!-- Leaf node: render a pane -->
    <template v-if="layout.type === 'leaf' && layout.pane_id">
      <TmuxPane :pane-id="layout.pane_id" />
    </template>

    <!-- Split node: render children with divider -->
    <template v-else-if="layout.children && layout.children.length === 2">
      <div
        class="split-child first"
        :style="firstChildStyle"
      >
        <TmuxPaneLayout :layout="layout.children[0]" />
      </div>

      <TmuxPaneDivider
        :direction="layout.type === 'hsplit' ? 'horizontal' : 'vertical'"
        :pane-id="getFirstLeafId(layout.children[1])"
        @resize="handleResize"
      />

      <div
        class="split-child second"
        :style="secondChildStyle"
      >
        <TmuxPaneLayout :layout="layout.children[1]" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import type { LayoutNode } from '../../stores/tmuxStore'
  import { useTmuxStore } from '../../stores/tmuxStore'
  import TmuxPane from './TmuxPane.vue'
  import TmuxPaneDivider from './TmuxPaneDivider.vue'

  const props = defineProps<{
    layout: LayoutNode
  }>()

  const tmuxStore = useTmuxStore()

  const layoutClass = computed(() => {
    if (props.layout.type === 'hsplit') return 'split-h'
    if (props.layout.type === 'vsplit') return 'split-v'
    return 'leaf'
  })

  const firstChildStyle = computed(() => {
    const ratio = props.layout.ratio || 0.5
    if (props.layout.type === 'vsplit') {
      return { width: `calc(${ratio * 100}% - 2px)`, height: '100%' }
    }
    if (props.layout.type === 'hsplit') {
      return { height: `calc(${ratio * 100}% - 2px)`, width: '100%' }
    }
    return {}
  })

  const secondChildStyle = computed(() => {
    const ratio = 1 - (props.layout.ratio || 0.5)
    if (props.layout.type === 'vsplit') {
      return { width: `calc(${ratio * 100}% - 2px)`, height: '100%' }
    }
    if (props.layout.type === 'hsplit') {
      return { height: `calc(${ratio * 100}% - 2px)`, width: '100%' }
    }
    return {}
  })

  function getFirstLeafId(node: LayoutNode): string {
    if (node.type === 'leaf' && node.pane_id) return node.pane_id
    if (node.children && node.children.length > 0) return getFirstLeafId(node.children[0])
    return ''
  }

  function handleResize(delta: number) {
    const paneId = getFirstLeafId(
      props.layout.children ? props.layout.children[1] : props.layout
    )
    tmuxStore.resizeLayout(paneId, delta)
  }
</script>

<style scoped>
  .tmux-pane-layout {
    width: 100%;
    height: 100%;
    overflow: hidden;
  }

  .tmux-pane-layout.leaf {
    display: flex;
  }

  .tmux-pane-layout.split-v {
    display: flex;
    flex-direction: row;
  }

  .tmux-pane-layout.split-h {
    display: flex;
    flex-direction: column;
  }

  .split-child {
    overflow: hidden;
    min-width: 40px;
    min-height: 40px;
  }
</style>
