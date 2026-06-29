import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  DUB_TASK_TYPES,
  TASK_STEP_LABELS,
  STATUS_META,
} from '@/constants'
import { taskApi } from '@/api'
import type { Task } from '@/api'

export { DUB_TASK_TYPES, TASK_STEP_LABELS, STATUS_META }

export const useTaskStore = defineStore('task', () => {
  const tasks = ref<Task[]>([])
  const loading = ref(false)
  const total = ref(0)
  const currentPage = ref(1)
  const pageSize = ref(20)

  // F2: dubTasks getter — 过滤 Phase 4 dubbing 任务链
  // 一条 task 被认为是 dub 任务当 type 在 DUB_TASK_TYPES 中
  const dubTasks = computed(() =>
    tasks.value.filter((t) => (DUB_TASK_TYPES as readonly string[]).includes(t.type)),
  )

  // F2: runningDubTasks — 当前在运行/排队的 dub 任务
  const runningDubTasks = computed(() =>
    dubTasks.value.filter((t) => t.status === 'running' || t.status === 'pending'),
  )

  // F2: failedDubTasks — failed 的 dub 任务
  const failedDubTasks = computed(() =>
    dubTasks.value.filter((t) => t.status === 'failed'),
  )

  async function fetchTasks(params?: {
    page?: number
    page_size?: number
    status?: string
    type?: string
  }) {
    loading.value = true
    try {
      const res = await taskApi.list(params)
      tasks.value = res.data.items
      total.value = res.data.total
      if (params?.page) currentPage.value = params.page
    } catch (e) {
      console.error('Failed to fetch tasks:', e)
    } finally {
      loading.value = false
    }
  }

  async function retryTask(id: number) {
    try {
      await taskApi.retry(id)
      await fetchTasks()
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  async function cancelTask(id: number) {
    try {
      await taskApi.cancel(id)
      await fetchTasks()
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  // F2: 根据 WebSocket 消息局部更新 task（避免每次都重新拉全表）
  function applyWsEvent(msg: Record<string, unknown>) {
    const type = msg.type as string | undefined
    const taskId = Number(msg.task_id ?? msg.id)
    const videoId = Number(msg.video_id)
    if (!type || !taskId) return false

    if (
      type !== 'task_start' &&
      type !== 'task_progress' &&
      type !== 'task_update' &&
      type !== 'task_complete' &&
      type !== 'task_error'
    ) {
      return false
    }

    const idx = tasks.value.findIndex((t) => t.id === taskId)
    if (idx === -1) return false

    const t = { ...tasks.value[idx] }
    if (type === 'task_start') {
      t.status = 'running'
      if (msg.message) t.message = String(msg.message)
    } else if (type === 'task_progress' || type === 'task_update') {
      t.status = 'running'
      if (typeof msg.progress === 'number') t.progress = msg.progress
      if (msg.message) t.message = String(msg.message)
    } else if (type === 'task_complete') {
      t.status = 'completed'
      t.progress = 100
      if (msg.message) t.message = String(msg.message)
    } else if (type === 'task_error') {
      t.status = 'failed'
      if (msg.error_msg || msg.message) {
        t.error_msg = String(msg.error_msg || msg.message)
      }
    }
    // 触发响应式更新
    tasks.value[idx] = t
    // video_id 保留供后续 video-side 推断（不影响该 store）
    void videoId
    return true
  }

  return {
    tasks,
    loading,
    total,
    currentPage,
    pageSize,
    dubTasks,
    runningDubTasks,
    failedDubTasks,
    fetchTasks,
    retryTask,
    cancelTask,
    applyWsEvent,
  }
})
