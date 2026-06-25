import { defineStore } from 'pinia'
import { ref } from 'vue'
import { WebSocketClient } from '@/utils/websocket'

type WsMessage = Record<string, unknown> & { type?: string }

export const useWsStore = defineStore('websocket', () => {
  const connectionStatus = ref<'connected' | 'disconnected' | 'reconnecting'>('disconnected')
  const messages = ref<WsMessage[]>([])
  const maxMessages = 100
  // 最近一条 Phase 4 task 事件 (供视图 watch)
  const lastTaskEvent = ref<WsMessage | null>(null)

  // 外部订阅者（F2: taskStore.applyWsEvent 通过 subscribe 注册）
  const subscribers = ref<((msg: WsMessage) => void)[]>([])

  let client: WebSocketClient | null = null

  function subscribe(cb: (msg: WsMessage) => void): () => void {
    subscribers.value.push(cb)
    return () => {
      subscribers.value = subscribers.value.filter((fn) => fn !== cb)
    }
  }

  function connect() {
    if (client) {
      client.disconnect()
    }

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${location.host}/ws`

    client = new WebSocketClient(wsUrl)

    client.onStatusChange((status) => {
      connectionStatus.value = status
    })

    client.onMessage((data) => {
      const msg = data as WsMessage
      messages.value.push(msg)
      if (messages.value.length > maxMessages) {
        messages.value.shift()
      }
      // F9: Phase 4 task_* 事件 → 缓存为 lastTaskEvent + dispatch 给订阅者
      const t = msg.type
      if (
        t === 'task_start' ||
        t === 'task_progress' ||
        t === 'task_update' ||
        t === 'task_complete' ||
        t === 'task_error'
      ) {
        lastTaskEvent.value = msg
        subscribers.value.forEach((fn) => {
          try {
            fn(msg)
          } catch (e) {
            console.error('[wsStore] subscriber threw:', e)
          }
        })
      }
    })

    client.connect()
  }

  function disconnect() {
    if (client) {
      client.disconnect()
      client = null
    }
    connectionStatus.value = 'disconnected'
  }

  return { connectionStatus, messages, lastTaskEvent, connect, disconnect, subscribe }
})
