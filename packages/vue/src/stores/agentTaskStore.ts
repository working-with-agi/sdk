/**
 * Pinia store for shared agent tasks.
 *
 * Manages task lifecycle (create, claim, complete, delete) via REST API,
 * and handles real-time task list updates from WebSocket.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface SharedTask {
  task_id: string
  subject: string
  description: string
  status: 'pending' | 'in_progress' | 'completed'
  owner: string | null
  blocked_by: string[]
  metadata: Record<string, any>
  active_form: string
}

export const useAgentTaskStore = defineStore('agentTasks', () => {
  const tasks = ref<Map<string, SharedTask>>(new Map())
  const sessionId = ref('')

  const taskList = computed(() => Array.from(tasks.value.values()))
  const pendingTasks = computed(() => taskList.value.filter((t) => t.status === 'pending'))
  const inProgressTasks = computed(() => taskList.value.filter((t) => t.status === 'in_progress'))
  const completedTasks = computed(() => taskList.value.filter((t) => t.status === 'completed'))

  async function fetchTasks(sid: string) {
    sessionId.value = sid
    try {
      const res = await fetch(`/api/tasks/${sid}`)
      const data = await res.json()
      tasks.value.clear()
      for (const t of data) {
        tasks.value.set(t.task_id, t)
      }
    } catch (e) {
      console.error('Failed to fetch tasks:', e)
    }
  }

  async function createTask(subject: string, description: string = '') {
    if (!sessionId.value) return
    try {
      const res = await fetch(`/api/tasks/${sessionId.value}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject, description }),
      })
      const task = await res.json()
      tasks.value.set(task.task_id, task)
      return task
    } catch (e) {
      console.error('Failed to create task:', e)
    }
  }

  async function updateTask(taskId: string, updates: Partial<SharedTask>) {
    if (!sessionId.value) return
    try {
      const res = await fetch(`/api/tasks/${sessionId.value}/${taskId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      })
      const task = await res.json()
      tasks.value.set(task.task_id, task)
      return task
    } catch (e) {
      console.error('Failed to update task:', e)
    }
  }

  async function deleteTask(taskId: string) {
    if (!sessionId.value) return
    try {
      await fetch(`/api/tasks/${sessionId.value}/${taskId}`, { method: 'DELETE' })
      tasks.value.delete(taskId)
    } catch (e) {
      console.error('Failed to delete task:', e)
    }
  }

  async function claimTask(taskId: string, agentId: string) {
    return updateTask(taskId, { owner: agentId, status: 'in_progress' })
  }

  function handleTaskListUpdate(taskData: SharedTask[]) {
    tasks.value.clear()
    for (const t of taskData) {
      tasks.value.set(t.task_id, t)
    }
  }

  return {
    tasks,
    sessionId,
    taskList,
    pendingTasks,
    inProgressTasks,
    completedTasks,
    fetchTasks,
    createTask,
    updateTask,
    deleteTask,
    claimTask,
    handleTaskListUpdate,
  }
})
