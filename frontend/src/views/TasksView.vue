<script setup lang="ts">
/**
 * Phase 12 TasksView — DESIGN.md §5.3.
 *
 * - el-table replaced by card grid
 * - Cards grouped by status accordion: 进行中 / 已完成 / 失败 / 已暂停
 * - Each card: thumbnail + title + horizontal stepper + actions
 * - Multi-select preserved (DESIGN.md R5)
 * - Batch toolbar preserved (暂停 / 恢复 / 重试 / 删除 / 导出)
 * - Channels + PublishHistory merged as tabs (DESIGN.md §3.1)
 * - Keyboard shortcuts: N (new) / R (refresh) / Space (preview) (R6)
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  VideoPlay, Refresh, Plus, Search,
} from '@element-plus/icons-vue'
import { useTaskStore, TASK_STEP_LABELS } from '@/stores/taskStore'
import { useWsStore } from '@/stores/wsStore'
import { dubApi, publishApi, batchApi, exportApi, taskDetailApi } from '@/api'
import api from '@/api'
import AiTitleSelector from '@/components/AiTitleSelector.vue'
import DubCreateDialog from '@/components/DubCreateDialog.vue'
import { defineAsyncComponent } from 'vue'

// DESIGN.md §3.1: channels and publish merged into Tasks as lazy tabs.
const ChannelsViewInline = defineAsyncComponent(() => import('@/views/ChannelsView.vue'))
const PublishHistoryInline = defineAsyncComponent(() => import('@/views/PublishHistoryView.vue'))

const store = useTaskStore()
const wsStore = useWsStore()
const router = useRouter()
const route = useRoute()

// ── Tab routing (channels / publish tabs via ?tab=) ──
const activeTab = ref<'tasks' | 'channels' | 'publish'>(
  (route.query.tab as any) || 'tasks',
)

// ── Filters ──
const statusFilter = ref('')
const typeFilter = ref('')
const sourceFilter = ref('')
const includeDeleted = ref(false)
const dateFilter = ref<[Date, Date] | null>(null)
const searchQuery = ref('')

// ── Selection ──
const selectedIds = ref<number[]>([])

// ── Video title cache (tasks only have video_id) ──
const videoTitles = ref<Record<number, string>>({})

const STEP_ORDER = ['download', 'transcribe', 'translate', 'synthesize', 'compose', 'publish']
const STEP_LABELS: Record<string, string> = {
  download: '下载', transcribe: '转写', translate: '翻译',
  synthesize: '合成', compose: '混音', publish: '发布',
  idle: '空闲',
}

function stepIndex(step: string | undefined): number {
  if (!step) return -1
  // Map dubbing step → unified STEP_ORDER position
  // tasks.type carries current step; for completed/failed, fallback.
  return STEP_ORDER.indexOf(step)
}

async function loadVideoTitles() {
  try {
    const res = await api.get<{ items: { id: number; title: string }[]; total: number }>('/videos', {
      params: { page: 1, page_size: 200 },
    })
    const map: Record<number, string> = {}
    res.data.items.forEach((v) => { map[v.id] = v.title })
    videoTitles.value = map
  } catch (e) {
    console.error('loadVideoTitles failed', e)
  }
}

function taskTitle(row: any): string {
  // v3.2: Backend now includes video_title in task response
  return row.video_title || videoTitles.value[row.video_id] || `视频 #${row.video_id}`
}

function currentStepOf(row: any): string {
  // The backend task `type` field represents the current step (download/transcribe/...).
  // For completed/failed rows, the type is still the step in which it ended.
  if (row.status === 'completed') return 'publish'
  return row.type || row.current_step || 'download'
}

// ── Dedupe tasks by video_id ──
// 每个视频按 D-14 拆成 5 个 Task (download/transcribe/translate/synthesize/compose)，
// UI 上应该按视频聚合：每个视频只显示一行，状态按聚合规则推导。
const DUB_TYPE_ORDER: Record<string, number> = {
  download: 0, transcribe: 1, translate: 2, synthesize: 3, compose: 4, publish: 5,
}

const dedupedByVideo = computed(() => {
  const byVideo = new Map<number, any[]>()
  for (const t of store.tasks) {
    const arr = byVideo.get(t.video_id) || []
    arr.push(t)
    byVideo.set(t.video_id, arr)
  }
  const result: any[] = []
  for (const [vid, arr] of byVideo) {
    if (arr.length === 1) {
      result.push(arr[0])
      continue
    }
    // 聚合规则：
    //   - 任一 failed → failed（取第一个 failed 任务代表）
    //   - 任一 running/pending/downloading/transcribing → running（取最新一条 running）
    //   - 全部 completed → completed（取最后一步 compose 作为代表）
    //   - 混合（含 paused 等）→ 取最新更新的代表
    const failed = arr.find((t) => t.status === 'failed')
    if (failed) { result.push(failed); continue }
    const running = arr.find((t) =>
      ['running', 'pending', 'downloading', 'transcribing'].includes(t.status))
    if (running) {
      // 取 running 中 DUB_TYPE_ORDER 最大的（最远的步骤）
      const runningTasks = arr.filter((t) =>
        ['running', 'pending', 'downloading', 'transcribing'].includes(t.status))
      runningTasks.sort((a, b) =>
        (DUB_TYPE_ORDER[b.type] ?? -1) - (DUB_TYPE_ORDER[a.type] ?? -1))
      result.push(runningTasks[0])
      continue
    }
    const allCompleted = arr.every((t) => t.status === 'completed')
    if (allCompleted) {
      // 取 compose / publish / 最后一步作为代表
      const sorted = [...arr].sort((a, b) =>
        (DUB_TYPE_ORDER[b.type] ?? -1) - (DUB_TYPE_ORDER[a.type] ?? -1))
      result.push(sorted[0])
      continue
    }
    // 其它情况：按 updated_at 取最新
    const sorted = [...arr].sort((a, b) =>
      new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    result.push(sorted[0])
    void vid
  }
  // 按 updated_at 倒序
  result.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
  return result
})

// ── Group tasks by lifecycle status ──
const groupedTasks = computed(() => {
  const groups: { key: string; label: string; items: any[] }[] = [
    { key: 'running', label: '进行中', items: [] },
    { key: 'completed', label: '已完成', items: [] },
    { key: 'failed', label: '失败', items: [] },
    { key: 'paused', label: '已暂停', items: [] },
  ]
  const runningSet = new Set(['running', 'pending', 'downloading', 'transcribing'])
  const pausedSet = new Set(['paused', 'cancelled'])
  for (const t of dedupedByVideo.value) {
    if (runningSet.has(t.status)) groups[0].items.push(t)
    else if (t.status === 'completed') groups[1].items.push(t)
    else if (t.status === 'failed') groups[2].items.push(t)
    else if (pausedSet.has(t.status)) groups[3].items.push(t)
  }
  return groups.filter((g) => g.items.length > 0 || g.key === 'running')
})

const expandedGroups = ref<string[]>(['running', 'failed'])

function toggleGroup(key: string) {
  const idx = expandedGroups.value.indexOf(key)
  if (idx >= 0) expandedGroups.value.splice(idx, 1)
  else expandedGroups.value.push(key)
}

// ── Actions ──
async function handleResume(videoId: number) {
  try {
    await ElMessageBox.confirm(
      `确认对视频 #${videoId} 执行断点续跑？将从最近失败的步骤继续。`,
      '断点续跑',
      { type: 'warning' },
    )
    await dubApi.resume(videoId)
    ElMessage.success('已提交续跑请求')
    await refresh()
  } catch (e: any) {
    if (e === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '续跑失败')
  }
}

async function handleRetry(taskId: number) {
  try {
    await store.retryTask(taskId)
    ElMessage.success('任务已重试')
  } catch {
    ElMessage.error('重试失败')
  }
}

async function handleCancel(taskId: number) {
  try {
    await ElMessageBox.confirm('确定取消该任务？', '确认')
    await store.cancelTask(taskId)
    ElMessage.success('已取消')
  } catch {}
}

async function handleAutoPublish(videoId: number) {
  try {
    await ElMessageBox.confirm(`确认把视频 #${videoId} 自动发布到所有已启用平台？`, '自动发布', { type: 'warning' })
    ElMessage.info('自动发布已启动')
    const res = await publishApi.autoPublish(videoId)
    const results = res.data.results
    const success = Object.values(results).filter((r) => r.status === 'published')
    const failed = Object.values(results).filter((r) => r.status !== 'published')
    if (success.length > 0) ElMessage.success(`${success.length} 个平台发布成功`)
    failed.forEach((r) => ElMessage.error(`${r.platform} 发布失败: ${r.error || ''}`))
  } catch (e: any) {
    if (e === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '自动发布失败')
  }
}

// ── AI title dialog ──
const aiTitleVisible = ref(false)
const aiTitleVideoId = ref(0)
function openAiTitleDialog(videoId: number) {
  aiTitleVideoId.value = videoId
  aiTitleVisible.value = true
}

// ── Preview dialog (single, replaces popover) ──
const previewState = ref<{ open: boolean; videoId: number; kind: 'dubbing' | 'final' | 'original' }>({
  open: false, videoId: 0, kind: 'dubbing',
})
function openPreview(videoId: number) {
  previewState.value = { open: true, videoId, kind: 'dubbing' }
}
function previewUrl(videoId: number, kind: 'dubbing' | 'final' | 'original') {
  return dubApi.previewUrl(videoId, kind)
}

// ── v3.2: Task Detail Dialog ──
import type { TaskDetailResponse } from '@/api'

const detailState = ref<{ open: boolean; taskId: number; loading: boolean }>({
  open: false, taskId: 0, loading: false,
})
const detailData = ref<TaskDetailResponse | null>(null)

async function openDetail(taskId: number) {
  detailState.value = { open: true, taskId, loading: true }
  detailData.value = null
  try {
    const res = await taskDetailApi.get(taskId)
    detailData.value = res.data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载详情失败')
    detailState.value.open = false
  } finally {
    detailState.value.loading = false
  }
}

// Find subtitle by language
function srtByLang(lang: string) {
  return detailData.value?.subtitles.find(s => s.language === lang)
}
function srtContent(lang: string): string {
  const s = srtByLang(lang)
  if (!s?.content) return '(无字幕数据)'
  // Limit display to 100 lines
  const lines = s.content.split('\n')
  if (lines.length > 100) return lines.slice(0, 100).join('\n') + `\n\n... (共 ${lines.length} 行)`
  return s.content
}

// ── New Dub Dialog ──
const dubDialogVisible = ref(false)

// ── Batch toolbar ──
async function runBatch(action: 'pause' | 'resume' | 'retry' | 'delete') {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先选择任务')
    return
  }
  const labels = { pause: '暂停', resume: '恢复', retry: '重试', delete: '删除' }
  try {
    await ElMessageBox.confirm(
      `确定对 ${selectedIds.value.length} 个任务执行「${labels[action]}」？`,
      '批量操作',
      { type: 'warning' },
    )
    const res = await batchApi.run({ action, ids: selectedIds.value })
    const r = res.data
    ElMessage.success(`成功 ${r.success_count} 个` + (r.failed_count ? `，失败 ${r.failed_count} 个` : ''))
    selectedIds.value = []
    await refresh()
  } catch (e: any) {
    if (e === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '批量操作失败')
  }
}

async function exportTasks(format: 'csv' | 'json') {
  try {
    const res = await exportApi.tasks(format, {
      status: statusFilter.value || undefined,
      type: typeFilter.value || undefined,
      source: sourceFilter.value || undefined,
      include_deleted: includeDeleted.value,
    })
    const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
    exportApi.downloadBlob(res.data as Blob, `tasks_export_${ts}.${format}`)
    ElMessage.success(`已导出 ${format.toUpperCase()}`)
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  }
}

function toggleSelect(id: number, ev?: MouseEvent) {
  // Ctrl/Cmd-click adds to selection (DESIGN.md R6).
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
  void ev
}

function isSelected(id: number): boolean {
  return selectedIds.value.includes(id)
}

// ── Filters ──
function applyFilters() {
  store.fetchTasks({
    page: 1,
    page_size: store.pageSize,
    status: statusFilter.value || undefined,
    type: typeFilter.value || undefined,
    source: sourceFilter.value || undefined,
    include_deleted: includeDeleted.value,
  } as any)
}

function refresh() {
  return store.fetchTasks({ page: store.currentPage, page_size: store.pageSize, include_deleted: includeDeleted.value } as any)
}

// ── Keyboard shortcuts (R6) ──
function onKeydown(e: KeyboardEvent) {
  // Skip if user is typing in an input/textarea.
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  if ((e.target as HTMLElement)?.isContentEditable) return

  if (e.key === 'n' || e.key === 'N') {
    e.preventDefault()
    dubDialogVisible.value = true
  } else if (e.key === 'r' || e.key === 'R') {
    e.preventDefault()
    refresh()
  }
}

let unsub: (() => void) | null = null
let keydownRegistered = false

onMounted(async () => {
  await Promise.all([
    store.fetchTasks({ page: 1, page_size: store.pageSize }),
    loadVideoTitles(),
  ])
  unsub = wsStore.subscribe((msg) => {
    const applied = store.applyWsEvent(msg)
    if (!applied) refresh()
  })
  window.addEventListener('keydown', onKeydown)
  keydownRegistered = true
})

onBeforeUnmount(() => {
  if (unsub) { unsub(); unsub = null }
  if (keydownRegistered) {
    window.removeEventListener('keydown', onKeydown)
    keydownRegistered = false
  }
})

// Stats summary
const summary = computed(() => {
  const total = store.tasks.length
  const running = store.tasks.filter((t) => ['running', 'pending', 'downloading', 'transcribing'].includes(t.status)).length
  const completed = store.tasks.filter((t) => t.status === 'completed').length
  const failed = store.tasks.filter((t) => t.status === 'failed').length
  return { total, running, completed, failed }
})
</script>

<template>
  <div class="tasks-view">
    <div class="page-header">
      <h1 class="page-title">任务</h1>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="refresh">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="dubDialogVisible = true">新建</el-button>
      </div>
    </div>

    <!-- Tabs (channels + publish merged per §3.1) -->
    <el-tabs v-model="activeTab" class="task-tabs">
      <el-tab-pane label="任务" name="tasks" />

      <!-- Channels inline (embed ChannelsView) -->
      <el-tab-pane label="频道" name="channels" lazy>
        <ChannelsViewInline v-if="activeTab === 'channels'" />
      </el-tab-pane>

      <!-- Publish history inline -->
      <el-tab-pane label="发布历史" name="publish" lazy>
        <PublishHistoryInline v-if="activeTab === 'publish'" />
      </el-tab-pane>
    </el-tabs>

    <!-- Filter bar (only on tasks tab) -->
    <div v-if="activeTab === 'tasks'" class="filter-bar y2b-card y2b-card-pad">
      <el-input
        v-model="searchQuery"
        :prefix-icon="Search"
        placeholder="搜索标题..."
        clearable
        size="default"
        style="width: 240px;"
      />
      <el-select v-model="statusFilter" placeholder="状态" clearable style="width: 140px;" @change="applyFilters">
        <el-option label="全部状态" value="" />
        <el-option label="等待中" value="pending" />
        <el-option label="运行中" value="running" />
        <el-option label="已完成" value="completed" />
        <el-option label="失败" value="failed" />
      </el-select>
      <el-select v-model="typeFilter" placeholder="步骤" clearable style="width: 140px;" @change="applyFilters">
        <el-option label="全部步骤" value="" />
        <el-option label="下载" value="download" />
        <el-option label="转写" value="transcribe" />
        <el-option label="翻译" value="translate" />
        <el-option label="合成配音" value="synthesize" />
        <el-option label="混音 + 成片" value="compose" />
      </el-select>
      <el-select v-model="sourceFilter" placeholder="来源" clearable style="width: 120px;" @change="applyFilters">
        <el-option label="全部来源" value="" />
        <el-option label="手动" value="manual" />
        <el-option label="频道扫描" value="channel" />
      </el-select>
      <div class="filter-spacer" />
      <el-checkbox v-model="includeDeleted" @change="applyFilters">显示已删除</el-checkbox>
      <el-button @click="exportTasks('csv')">导出 CSV</el-button>
      <el-button @click="exportTasks('json')">导出 JSON</el-button>
    </div>

    <!-- Batch toolbar -->
    <div v-if="activeTab === 'tasks' && selectedIds.length > 0" class="batch-bar y2b-card y2b-card-pad">
      <span class="batch-count">已选 <strong class="num-mono">{{ selectedIds.length }}</strong> 项</span>
      <el-button size="small" @click="runBatch('pause')" type="warning">暂停</el-button>
      <el-button size="small" @click="runBatch('resume')" type="success">恢复</el-button>
      <el-button size="small" @click="runBatch('retry')" type="primary">重试</el-button>
      <el-button size="small" @click="runBatch('delete')" type="danger">删除</el-button>
      <el-button text size="small" @click="selectedIds = []">取消选择</el-button>
    </div>

    <!-- Card groups -->
    <div v-if="activeTab === 'tasks'" v-loading="store.loading" class="groups">
      <section
        v-for="g in groupedTasks"
        :key="g.key"
        class="task-group"
      >
        <header class="group-header" @click="toggleGroup(g.key)">
          <el-icon class="caret">
            <ArrowDown v-if="expandedGroups.includes(g.key)" />
            <ArrowRight v-else />
          </el-icon>
          <h2 class="group-title">{{ g.label }}</h2>
          <span class="status-badge is-info num-mono">{{ g.items.length }}</span>
        </header>

        <div v-if="expandedGroups.includes(g.key)" class="card-grid">
          <article
            v-for="row in g.items"
            :key="row.id"
            class="task-card y2b-card"
            :class="{ selected: isSelected(row.id) }"
            @click.ctrl="toggleSelect(row.id, $event)"
            @click.meta="toggleSelect(row.id, $event)"
          >
            <div class="card-top">
              <div
                class="card-thumb"
                :style="row.video_thumbnail_url ? { backgroundImage: `url(${row.video_thumbnail_url})` } : undefined"
              />
              <div class="card-meta">
                <div class="card-title" :title="taskTitle(row)">{{ taskTitle(row) }}</div>
                <div class="card-sub text-caption">
                  #{{ row.id }} · {{ new Date(row.created_at).toLocaleString('zh-CN') }}
                </div>
              </div>
              <el-checkbox
                :model-value="isSelected(row.id)"
                @click.stop
                @update:model-value="() => toggleSelect(row.id)"
              />
            </div>

            <!-- Horizontal stepper -->
            <div class="card-stepper">
              <div class="h-stepper">
                <template v-for="(step, idx) in STEP_ORDER" :key="step">
                  <span
                    class="step-dot"
                    :class="{
                      'is-done': stepIndex(currentStepOf(row)) > idx,
                      'is-current': stepIndex(currentStepOf(row)) === idx && row.status !== 'failed',
                      'is-failed': stepIndex(currentStepOf(row)) === idx && row.status === 'failed',
                    }"
                  />
                  <span
                    v-if="idx < STEP_ORDER.length - 1"
                    class="step-bar"
                    :class="{ 'is-done': stepIndex(currentStepOf(row)) > idx }"
                  />
                </template>
              </div>
              <div class="step-labels">
                <span
                  v-for="(step, idx) in STEP_ORDER"
                  :key="step"
                  class="step-label"
                  :class="{
                    'is-current': stepIndex(currentStepOf(row)) === idx,
                    'is-done': stepIndex(currentStepOf(row)) > idx,
                    'is-failed': stepIndex(currentStepOf(row)) === idx && row.status === 'failed',
                  }"
                >{{ STEP_LABELS[step] }}</span>
              </div>
              <div class="card-progress">
                <el-progress
                  :percentage="Math.round(row.progress || 0)"
                  :status="row.status === 'failed' ? 'exception' : row.status === 'completed' ? 'success' : undefined"
                  :stroke-width="6"
                  :show-text="false"
                />
                <span class="num-mono text-caption">{{ Math.round(row.progress || 0) }}%</span>
              </div>
              <div v-if="row.status === 'failed' && row.error_msg" class="card-error is-danger-text">
                失败：{{ row.error_msg }}
              </div>
            </div>

            <!-- Card actions -->
            <div class="card-actions">
              <el-button
                text size="small" type="primary"
                :icon="VideoPlay"
                @click.stop="openPreview(row.video_id)"
              >试听</el-button>
              <el-button
                text size="small"
                @click.stop="openDetail(row.id)"
              >详情</el-button>
              <el-button
                text size="small"
                @click.stop="router.push(`/tasks/${row.video_id}/subtitles`)"
              >字幕</el-button>
              <el-button
                v-if="row.status === 'failed'"
                text size="small" type="warning"
                @click.stop="handleRetry(row.id)"
              >重试</el-button>
              <el-button
                v-if="row.status === 'failed'"
                text size="small" type="success"
                @click.stop="handleResume(row.video_id)"
              >续跑</el-button>
              <el-button
                v-if="['running', 'pending'].includes(row.status)"
                text size="small" type="danger"
                @click.stop="handleCancel(row.id)"
              >取消</el-button>
              <template v-if="row.status === 'completed'">
                <el-button text size="small" type="info" @click.stop="openAiTitleDialog(row.video_id)">AI 标题</el-button>
                <el-button text size="small" type="primary" @click.stop="handleAutoPublish(row.video_id)">自动发布</el-button>
              </template>
            </div>
          </article>

          <div v-if="g.items.length === 0" class="empty-group text-caption">
            (无)
          </div>
        </div>
      </section>

      <div class="summary-row text-caption num-mono">
        共 {{ summary.total }} 个任务 · 进行中 {{ summary.running }} · 完成 {{ summary.completed }} · 失败 {{ summary.failed }}
      </div>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="store.currentPage"
          v-model:page-size="store.pageSize"
          :total="store.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="(p: number) => store.fetchTasks({ page: p, page_size: store.pageSize })"
          @size-change="(s: number) => store.fetchTasks({ page: 1, page_size: s })"
        />
      </div>
    </div>

    <!-- Preview dialog -->
    <el-dialog v-model="previewState.open" title="试听" width="420px">
      <el-radio-group v-model="previewState.kind" style="margin-bottom: var(--space-3);">
        <el-radio-button label="dubbing">中文配音</el-radio-button>
        <el-radio-button label="final">最终视频</el-radio-button>
        <el-radio-button label="original">原视频</el-radio-button>
      </el-radio-group>
      <audio
        v-if="previewState.kind === 'dubbing'"
        :src="previewUrl(previewState.videoId, 'dubbing')"
        controls
        style="width: 100%"
      />
      <video
        v-else
        :src="previewUrl(previewState.videoId, previewState.kind)"
        controls
        style="width: 100%; max-height: 320px;"
      />
    </el-dialog>

    <!-- v3.2: Task Detail Dialog (视频简介 + 字幕) -->
    <el-dialog
      v-model="detailState.open"
      :title="detailData?.video?.title || '任务详情'"
      width="760px"
      top="5vh"
    >
      <div v-loading="detailState.loading" v-if="detailData" class="detail-body">
        <!-- 视频简介 -->
        <section class="detail-section">
          <h3 class="detail-head">视频简介</h3>
          <p class="detail-desc">{{ detailData.video.description || '(无简介)' }}</p>
          <div class="detail-meta text-caption">
            <span>频道: {{ detailData.video.channel || '-' }}</span>
            <span>时长: {{ detailData.video.duration ? Math.floor(detailData.video.duration / 60) + ':' + String(detailData.video.duration % 60).padStart(2, '0') : '-' }}</span>
            <span>播放: {{ detailData.video.view_count?.toLocaleString() || '0' }}</span>
            <span>YouTube: <a :href="detailData.video.youtube_url" target="_blank" rel="noopener">打开</a></span>
          </div>
        </section>

        <!-- 原始字幕 (SRT) -->
        <section class="detail-section">
          <h3 class="detail-head">原始字幕 (原语言 SRT)</h3>
          <pre class="detail-srt">{{ srtContent('original') }}</pre>
        </section>

        <!-- 翻译后字幕 (SRT) -->
        <section class="detail-section">
          <h3 class="detail-head">翻译后字幕 (中文 SRT)</h3>
          <pre class="detail-srt">{{ srtContent('zh') }}</pre>
        </section>
      </div>
      <div v-else-if="!detailState.loading" style="text-align: center; padding: var(--space-6); color: var(--color-text-secondary);">
        暂无数据
      </div>
    </el-dialog>

    <!-- AI Title -->
    <AiTitleSelector v-model:visible="aiTitleVisible" :video-id="aiTitleVideoId" />

    <!-- New Dub Dialog -->
    <DubCreateDialog v-model="dubDialogVisible" @created="refresh" />
  </div>
</template>

<style scoped>
.tasks-view {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.page-title {
  font-size: var(--fs-2xl);
  font-weight: 600;
  margin: 0;
}
.header-actions {
  display: flex;
  gap: var(--space-2);
}

.task-tabs {
  --el-tabs-header-height: 40px;
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.filter-spacer { flex: 1; }

.batch-bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--color-primary-light) !important;
  border-color: var(--color-primary-light-7) !important;
}
.batch-count { font-size: var(--fs-sm); }
.batch-count strong { color: var(--color-primary); }

.groups { display: flex; flex-direction: column; gap: var(--space-6); }

.task-group { display: flex; flex-direction: column; gap: var(--space-3); }
.group-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  user-select: none;
  padding: var(--space-2) 0;
}
.caret { color: var(--color-text-muted); }
.group-title {
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--color-text);
  margin: 0;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: var(--space-4);
}

.task-card {
  padding: var(--space-4);
  cursor: default;
  position: relative;
}
.task-card.selected {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-light-7);
}

.card-top {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.card-thumb {
  width: 80px;
  height: 45px;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, var(--color-bg-soft), var(--color-border));
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  flex-shrink: 0;
}
.card-meta { flex: 1; min-width: 0; }
.card-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-sub { margin-top: 2px; }

.card-stepper {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-2) 0;
}
.step-labels {
  display: flex;
  justify-content: space-between;
}
.step-labels .step-label { flex: 1; font-size: 11px; }
.card-progress {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-1);
}
.card-progress .el-progress { flex: 1; }
.card-error {
  font-size: var(--fs-xs);
  margin-top: var(--space-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  border-top: 1px solid var(--color-border-soft);
  padding-top: var(--space-2);
  margin-top: var(--space-2);
}

.empty-group {
  padding: var(--space-4);
  text-align: center;
}

.summary-row { text-align: right; padding-top: var(--space-2); }

.pagination-wrapper {
  display: flex;
  justify-content: center;
  padding: var(--space-4) 0;
}

/* ── v3.2 Task Detail Dialog ── */
.detail-body {
  max-height: 70vh;
  overflow-y: auto;
}
.detail-section {
  margin-bottom: var(--space-5);
}
.detail-head {
  font-size: var(--fs-base);
  font-weight: 600;
  margin: 0 0 var(--space-2);
  padding-bottom: var(--space-1);
  border-bottom: 1px solid var(--color-border);
}
.detail-desc {
  color: var(--color-text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0 0 var(--space-2);
}
.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin-bottom: var(--space-1);
}
.detail-meta a {
  color: var(--color-primary);
  text-decoration: none;
}
.detail-srt {
  background: var(--color-bg-soft);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  font-size: 12px;
  line-height: 1.5;
  max-height: 260px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
</style>
