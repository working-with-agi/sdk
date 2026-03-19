/**
 * Pinia store for inter-agent messaging.
 *
 * Tracks agent messages, agent status (idle/busy), unread counts, and toast notifications.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface AgentMessage {
  message_id: string
  from_agent: string
  to_agent: string
  message_type: string
  timestamp: string
  payload: {
    content?: string
    summary?: string
    agent_id?: string
    request_id?: string
    approve?: boolean
    [key: string]: any
  }
  correlation_id?: string
  reply_to?: string
}

export interface AgentState {
  id: string
  isIdle: boolean
  lastActivity: number
}

export const useAgentMessagingStore = defineStore('agentMessaging', () => {
  const messages = ref<Record<string, AgentMessage[]>>({})
  const agents = ref<Record<string, AgentState>>({})
  const unreadCounts = ref<Record<string, number>>({})
  const toasts = ref<Array<{ id: string; from: string; summary: string; timestamp: number }>>([])

  const totalUnread = computed(() => {
    return Object.values(unreadCounts.value).reduce((sum, c) => sum + c, 0)
  })

  const agentList = computed(() => Object.values(agents.value))

  function messagesForPane(paneId: string): AgentMessage[] {
    return messages.value[paneId] || []
  }

  function handleIncomingMessage(msg: AgentMessage) {
    const key = msg.from_agent
    if (!messages.value[key]) {
      messages.value[key] = []
    }
    messages.value[key].push(msg)

    // Update unread
    const current = unreadCounts.value[key] || 0
    unreadCounts.value[key] = current + 1

    // Add toast
    addToast(msg.from_agent, msg.payload.summary || msg.payload.content?.slice(0, 50) || '')
  }

  function updateAgentStatus(agentId: string, isIdle: boolean) {
    const existing = agents.value[agentId] || { id: agentId, isIdle: true, lastActivity: 0 }
    agents.value[agentId] = { ...existing, isIdle, lastActivity: Date.now() }
  }

  function clearUnread(agentId: string) {
    unreadCounts.value[agentId] = 0
  }

  function addToast(from: string, summary: string) {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`
    toasts.value.push({ id, from, summary, timestamp: Date.now() })
    // Keep max 3 toasts
    if (toasts.value.length > 3) {
      toasts.value.shift()
    }
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, 5000)
  }

  function removeToast(id: string) {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  return {
    messages,
    agents,
    unreadCounts,
    toasts,
    totalUnread,
    agentList,
    messagesForPane,
    handleIncomingMessage,
    updateAgentStatus,
    clearUnread,
    addToast,
    removeToast,
  }
})
