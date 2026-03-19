<template>
  <div
    class="tmux-divider"
    :class="direction"
    @mousedown.prevent="startDrag"
  >
    <div class="divider-handle"></div>
  </div>
</template>

<script setup lang="ts">
  import { onUnmounted, ref } from 'vue'

  const props = defineProps<{
    direction: 'horizontal' | 'vertical'
    paneId: string
  }>()

  const emit = defineEmits<{
    resize: [delta: number]
  }>()

  const isDragging = ref(false)
  let startPos = 0
  let containerSize = 0

  function startDrag(e: MouseEvent) {
    isDragging.value = true
    const isHorizontal = props.direction === 'horizontal'
    startPos = isHorizontal ? e.clientY : e.clientX

    // Get the split container (grandparent: .tmux-pane-layout) for delta calculation
    const el = (e.target as HTMLElement).closest('.tmux-pane-layout')
    if (el) {
      containerSize = isHorizontal ? el.clientHeight : el.clientWidth
    }

    document.addEventListener('mousemove', onDrag)
    document.addEventListener('mouseup', stopDrag)
    document.body.style.cursor = isHorizontal ? 'row-resize' : 'col-resize'
    document.body.style.userSelect = 'none'
  }

  function onDrag(e: MouseEvent) {
    if (!isDragging.value || containerSize === 0) return
    const isHorizontal = props.direction === 'horizontal'
    const currentPos = isHorizontal ? e.clientY : e.clientX
    const delta = (currentPos - startPos) / containerSize
    startPos = currentPos
    emit('resize', delta)
  }

  function stopDrag() {
    isDragging.value = false
    document.removeEventListener('mousemove', onDrag)
    document.removeEventListener('mouseup', stopDrag)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  onUnmounted(() => {
    stopDrag()
  })
</script>

<style scoped>
  .tmux-divider {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
  }

  .tmux-divider.vertical {
    width: 4px;
    cursor: col-resize;
  }

  .tmux-divider.horizontal {
    height: 4px;
    cursor: row-resize;
  }

  .divider-handle {
    background: #444;
    border-radius: 2px;
    transition: background 0.15s;
  }

  .vertical .divider-handle {
    width: 2px;
    height: 100%;
  }

  .horizontal .divider-handle {
    height: 2px;
    width: 100%;
  }

  .tmux-divider:hover .divider-handle {
    background: #6366f1;
  }
</style>
