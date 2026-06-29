<script setup lang="ts">
/**
 * Phase 12 DashboardView — DESIGN.md §5.1.
 *
 * Layout:
 *   - Hero: welcome + giant CTA
 *   - Left: current in-progress tasks (≤3) with horizontal stepper
 *   - Right: platform account status card → opens PlatformLoginDrawer
 *   - Center: recently completed videos (≤6) with thumbnail + try-listen
 *   - Bottom: onboarding checklist (auto-show if API key missing /
 *             <2 platforms logged in / no completed tasks)
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Plus, VideoPlay, Refresh, Check, Close, Link as LinkIcon,
} from '@element-plus/icons-vue'
import {
  statsApi, dubApi, platformApi, configApi,
  type DashboardData, type PlatformStateItem,
} from '@/api'
import api from '@/api'
import DubCreateDialog from '@/components/DubCreateDialog.vue'
import PlatformLoginDrawer from '@/components/PlatformLoginDrawer.vue'

const router = useRouter()

const dashboard = ref<DashboardData | null>(null)
const loading = ref(false)
const topPicks = ref<any[]>([])
const dialogVisible = ref(false)
const platformDrawerVisible = ref(false)
const platformStates = ref<PlatformStateItem[]>([])

// Onboarding state (DESIGN.md R1 — banner persists until API key set).
const apiKeyConfigured = ref<boolean | null>(null)
const onboardingDismissed = (() => localStorage.getItem('viddub.onboarding_v3_seen') === 'true')()
const showWelcomeModal = ref(!onboardingDismissed)

// Stepper order (DESIGN.md §5.3): download → transcribe → translate → synthesize → compose → publish
const STEP_ORDER = ['download', 'transcribe', 'translate', 'synthesize', 'compose', 'publish']
const STEP_LABELS: Record<string, string> = {
  download: '下载', transcribe: '转写', translate: '翻译',
  synthesize: '合成', compose: '混音', publish: '发布',
}

function stepIndex(step: string | undefined): number {
  if (!step) return -1
  return STEP_ORDER.indexOf(step)
}

async function fetchTopPicks() {
  try {
    const res = await api.get('/scoring/history', { params: { limit: 6 } })
    topPicks.value = (res.data.items || []).sort(
      (a: any, b: any) => b.composite_score - a.composite_score,
    )
  } catch {
    // Scoring not yet available — no worries
  }
}

function formatViews(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function scoreClass(s: number): string {
  if (s >= 80) return 'score-high'
  if (s >= 60) return 'score-mid'
  return 'score-low'
}

async function fetchDashboard() {
  loading.value = true
  try {
    const res = await statsApi.dashboard()
    dashboard.value = res.data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '获取仪表盘数据失败')
  } finally {
    loading.value = false
  }
}

async function fetchPlatformStates() {
  try {
    const res = await platformApi.allState()
    platformStates.value = res.data.platforms
  } catch {
    platformStates.value = []
  }
}

async function fetchApiKeyConfigured() {
  try {
    const res = await configApi.list()
    const item = (res.data as any[]).find((c) => c.key === 'siliconflow_api_key')
    apiKeyConfigured.value = !!(item && item.value && String(item.value).trim())
  } catch {
    apiKeyConfigured.value = null
  }
}

const inProgressTasks = computed(() => {
  if (!dashboard.value) return []
  const recent = dashboard.value.recent_tasks || []
  return recent
    .filter((t) => !['completed', 'failed', 'cancelled'].includes(t.status))
    .slice(0, 3)
})

const completedTasks = computed(() => {
  if (!dashboard.value) return []
  return (dashboard.value.recent_tasks || [])
    .filter((t) => t.status === 'completed')
    .slice(0, 6)
})

const failedTasks = computed(() => dashboard.value?.failed_tasks || [])

// Onboarding checklist gates (DESIGN.md §5.1).
const checklist = computed(() => [
  {
    id: 'api_key',
    label: '配置 SiliconFlow API Key',
    done: apiKeyConfigured.value === true,
    action: () => router.push('/settings'),
    actionLabel: apiKeyConfigured.value === true ? '已完成' : '前往配置',
  },
  {
    id: 'platform',
    label: '登录至少一个平台',
    done: platformStates.value.filter((p) => p.logged_in).length >= 1,
    action: () => { platformDrawerVisible.value = true },
    actionLabel: platformStates.value.filter((p) => p.logged_in).length >= 1 ? '已完成' : '扫码登录',
  },
  {
    id: 'first_dub',
    label: '完成首次配音',
    done: completedTasks.value.length > 0,
    action: () => { dialogVisible.value = true },
    actionLabel: completedTasks.value.length > 0 ? '已完成' : '开始 →',
  },
])

const checklistAllDone = computed(() => checklist.value.every((c) => c.done))
const showChecklist = computed(() => !checklistAllDone.value)

function statusLabel(status: string): string {
  const m: Record<string, string> = {
    pending: '等待中', running: '处理中', downloading: '下载中', downloaded: '已下载',
    transcribing: '转写中', transcribed: '已转写', translated: '已翻译',
    synthesized: '已合成配音', composed: '已混音', completed: '已完成',
    failed: '失败', cancelled: '已取消',
  }
  return m[status] || status
}

function statusBadgeClass(status: string): string {
  if (status === 'completed') return 'is-success'
  if (status === 'failed') return 'is-danger'
  if (['running', 'downloading', 'transcribing', 'pending'].includes(status)) return 'is-warning'
  return 'is-info'
}

function stepLabel(step: string | undefined): string {
  if (!step) return '空闲'
  return STEP_LABELS[step] || step
}

function thumbnailForTask(t: any): string | null {
  // v3.2: Backend now includes thumbnail_url in dashboard recent/failed tasks
  return t.thumbnail_url || null
}

async function onResumeFailed(videoId: number) {
  try {
    await dubApi.resume(videoId)
    ElMessage.success(`已提交续跑 #${videoId}`)
    await fetchDashboard()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '续跑失败')
  }
}

function onTasksCreated() {
  fetchDashboard()
  router.push('/tasks')
}

function openExternal(url: string) {
  window.open(url, '_blank', 'noopener')
}

function dismissOnboarding() {
  localStorage.setItem('viddub.onboarding_v3_seen', 'true')
  showWelcomeModal.value = false
}

function dismissWelcomeOnly() {
  showWelcomeModal.value = false
  // Don't persist — show again next session until checklist complete.
}

onMounted(() => {
  fetchDashboard()
  fetchPlatformStates()
  fetchApiKeyConfigured()
  fetchTopPicks()
})
</script>

<template>
  <div class="dashboard" v-loading="loading">

    <!-- ── Hero (DESIGN.md §5.1) ── -->
    <section class="hero">
      <div class="hero-text">
        <h1 class="hero-title">👋 你好，欢迎使用 VidDub</h1>
        <p class="hero-subtitle">把 YouTube 视频自动配音并发布到 B 站 / 西瓜。</p>
      </div>
      <el-button
        type="primary"
        size="large"
        :icon="Plus"
        class="hero-cta"
        @click="dialogVisible = true"
      >
        开始一个新配音
      </el-button>
    </section>

    <!-- ── API Key missing banner (DESIGN.md R1) ── -->
    <el-alert
      v-if="apiKeyConfigured === false"
      type="warning"
      show-icon
      :closable="false"
      class="key-banner"
    >
      <template #title>
        SiliconFlow API Key 尚未配置 — 大部分功能无法使用。
        <el-button text type="primary" size="small" @click="router.push('/settings')">
          立即配置 →
        </el-button>
      </template>
    </el-alert>

    <!-- ── 今日推荐（智能选题）── -->
    <section v-if="topPicks.length > 0" class="section-card y2b-card y2b-card-pad-lg picks-section">
      <div class="section-header">
        <h2 class="section-title">推荐视频</h2>
        <el-button text type="primary" size="small" @click="router.push('/discover')">
          查看全部 →
        </el-button>
      </div>
      <div class="picks-grid">
        <div
          v-for="v in topPicks"
          :key="v.youtube_id"
          class="pick-card"
          @click="router.push('/discover')"
        >
          <img
            v-if="v.thumbnail_url"
            :src="v.thumbnail_url"
            :alt="v.title"
            class="pick-thumb"
            loading="lazy"
          />
          <div v-else class="pick-thumb pick-thumb-placeholder">
            <el-icon :size="20"><VideoPlay /></el-icon>
          </div>
          <div class="pick-body">
            <div class="pick-title">{{ v.title }}</div>
            <div class="pick-channel">{{ v.channel_name }}</div>
            <span class="pick-score" :class="scoreClass(v.composite_score)">
              {{ v.composite_score?.toFixed(0) || '-' }}分
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- ── In-Progress + Platform Account row ── -->
    <el-row :gutter="24" class="main-row">
      <el-col :xs="24" :md="14">
        <div class="section-card y2b-card y2b-card-pad-lg">
          <div class="section-header">
            <h2 class="section-title">进行中</h2>
            <span class="text-caption num-mono">{{ inProgressTasks.length }} 个任务</span>
          </div>

          <div v-if="inProgressTasks.length === 0" class="empty-block">
            <p class="text-caption">当前没有正在处理的任务。</p>
            <el-button type="primary" :icon="Plus" @click="dialogVisible = true">
              新建配音任务
            </el-button>
          </div>

          <div v-else class="in-progress-list">
            <div
              v-for="t in inProgressTasks"
              :key="t.video_id"
              class="ip-task-row"
              @click="router.push('/tasks')"
            >
              <div
                class="ip-thumb-placeholder"
                :style="thumbnailForTask(t) ? { backgroundImage: `url(${thumbnailForTask(t)})` } : undefined"
              />
              <div class="ip-body">
                <div class="ip-title-row">
                  <span class="ip-title" :title="t.title">{{ t.title || `视频 #${t.video_id}` }}</span>
                  <span class="status-badge" :class="statusBadgeClass(t.status)">
                    {{ statusLabel(t.status) }}
                  </span>
                </div>

                <!-- Horizontal stepper (DESIGN.md §5.3) -->
                <div class="h-stepper ip-stepper">
                  <template v-for="(step, idx) in STEP_ORDER" :key="step">
                    <span
                      class="step-dot"
                      :class="{
                        'is-done': stepIndex(t.current_step) > idx,
                        'is-current': stepIndex(t.current_step) === idx,
                      }"
                    />
                    <span
                      v-if="idx < STEP_ORDER.length - 1"
                      class="step-bar"
                      :class="{ 'is-done': stepIndex(t.current_step) > idx }"
                    />
                  </template>
                </div>
                <div class="step-labels ip-step-labels">
                  <span
                    v-for="(step, idx) in STEP_ORDER"
                    :key="step"
                    class="step-label"
                    :class="{
                      'is-current': stepIndex(t.current_step) === idx,
                      'is-done': stepIndex(t.current_step) > idx,
                    }"
                  >
                    {{ STEP_LABELS[step] }}
                  </span>
                </div>

                <div class="ip-progress-row">
                  <el-progress
                    :percentage="Math.round(t.progress_pct || 0)"
                    :stroke-width="6"
                    :show-text="false"
                  />
                  <span class="num-mono text-caption">{{ Math.round(t.progress_pct || 0) }}%</span>
                </div>
                <div class="text-caption">当前步骤：{{ stepLabel(t.current_step) }}</div>
              </div>
            </div>
          </div>

          <div class="section-footer" v-if="inProgressTasks.length > 0">
            <el-button text type="primary" @click="router.push('/tasks')">
              查看全部任务 →
            </el-button>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :md="10">
        <div class="section-card y2b-card y2b-card-pad-lg platform-card">
          <div class="section-header">
            <h2 class="section-title">平台账号</h2>
          </div>

          <div class="platform-mini-list">
            <div
              v-for="p in platformStates"
              :key="p.platform"
              class="platform-mini"
              :class="{ 'not-logged': !p.logged_in }"
              @click="platformDrawerVisible = true"
            >
              <div class="pm-left">
                <div class="pm-logo">{{ p.platform === 'bilibili' ? 'B' : '西' }}</div>
                <div class="pm-info">
                  <div class="pm-name">{{ p.display_name }}</div>
                  <div v-if="p.logged_in" class="pm-user is-success-text">
                    ✓ {{ p.user_info?.username || p.user_info?.uname || '已登录' }}
                  </div>
                  <div v-else class="pm-user is-danger-text">⚠ 未登录</div>
                </div>
              </div>
              <div class="pm-action">
                <el-button v-if="!p.logged_in" type="primary" size="small">扫码登录</el-button>
                <el-button v-else size="small" @click.stop="platformDrawerVisible = true">管理</el-button>
              </div>
            </div>
            <div v-if="platformStates.length === 0" class="empty-block">
              <p class="text-caption">尚未加载平台状态。</p>
              <el-button @click="fetchPlatformStates">刷新</el-button>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- ── Recently completed (DESIGN.md §5.1 center) ── -->
    <section class="section-card y2b-card y2b-card-pad-lg completed-section">
      <div class="section-header">
        <h2 class="section-title">最近完成</h2>
        <el-button text type="primary" @click="router.push('/tasks')">查看更多 →</el-button>
      </div>

      <div v-if="completedTasks.length === 0" class="empty-block">
        <p class="text-caption">暂无已完成的配音。完成第一个视频后将出现在这里。</p>
      </div>

      <div v-else class="completed-grid">
        <div v-for="t in completedTasks" :key="t.video_id" class="completed-card">
          <div
            class="cc-thumb"
            :style="thumbnailForTask(t) ? { backgroundImage: `url(${thumbnailForTask(t)})` } : undefined"
          />
          <div class="cc-title" :title="t.title">{{ t.title || `视频 #${t.video_id}` }}</div>
          <div class="cc-actions">
            <el-button
              text
              size="small"
              type="primary"
              :icon="VideoPlay"
              @click="router.push('/tasks')"
            >试听</el-button>
            <el-button
              v-if="t.final_url"
              text
              size="small"
              :icon="LinkIcon"
              @click="openExternal(t.final_url!)"
            >打开 URL</el-button>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Failed tasks (collapsed) ── -->
    <section v-if="failedTasks.length > 0" class="section-card y2b-card y2b-card-pad-lg failed-section">
      <el-collapse>
        <el-collapse-item>
          <template #title>
            <div class="failed-header">
              <span class="is-danger-text">失败任务（{{ failedTasks.length }} 个）</span>
              <span class="text-caption">点击展开处理</span>
            </div>
          </template>
          <div class="failed-list">
            <div v-for="t in failedTasks" :key="t.video_id" class="failed-row">
              <div class="fr-body">
                <div class="fr-title">{{ t.title || `视频 #${t.video_id}` }}</div>
                <div class="text-caption is-danger-text">{{ t.error_msg || '未知原因' }}</div>
              </div>
              <div class="fr-actions">
                <el-button size="small" type="success" plain @click="onResumeFailed(t.video_id)">续跑</el-button>
              </div>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </section>

    <!-- ── Onboarding checklist (DESIGN.md §5.1 bottom) ── -->
    <section v-if="showChecklist" class="section-card y2b-card y2b-card-pad-lg onboarding-section">
      <div class="section-header">
        <h2 class="section-title">新手指南</h2>
      </div>
      <ol class="checklist">
        <li v-for="c in checklist" :key="c.id" class="checklist-row">
          <span class="cl-icon" :class="c.done ? 'is-done' : 'is-todo'">
            <el-icon v-if="c.done"><Check /></el-icon>
            <span v-else>{{ checklist.indexOf(c) + 1 }}</span>
          </span>
          <span class="cl-label" :class="{ 'is-done-text': c.done }">{{ c.label }}</span>
          <el-button
            v-if="!c.done"
            text
            type="primary"
            size="small"
            @click="c.action()"
          >{{ c.actionLabel }}</el-button>
          <span v-else class="status-badge is-success">已完成</span>
        </li>
      </ol>
    </section>

    <!-- ── Welcome modal (DESIGN.md §9 onboarding tour) ── -->
    <el-dialog
      v-model="showWelcomeModal"
      title="欢迎使用 VidDub"
      width="520px"
      :close-on-click-modal="false"
      :show-close="true"
    >
      <div class="welcome-body">
        <p class="welcome-intro">3 步开始你的第一次配音发布：</p>
        <ol class="welcome-steps">
          <li>
            <strong>1. 配置 API Key</strong>
            <p class="text-caption">从 SiliconFlow 获取 Key，粘贴到设置页。</p>
          </li>
          <li>
            <strong>2. 扫码登录平台</strong>
            <p class="text-caption">用 B 站 / 西瓜 App 扫码，授权后自动发布。</p>
          </li>
          <li>
            <strong>3. 粘贴 YouTube URL 启动</strong>
            <p class="text-caption">点击首页巨型按钮，按向导完成首次配音。</p>
          </li>
        </ol>
      </div>
      <template #footer>
        <el-button @click="dismissWelcomeOnly">稍后看</el-button>
        <el-button type="primary" @click="dismissOnboarding">我知道了</el-button>
      </template>
    </el-dialog>

    <!-- Dialogs / Drawers -->
    <DubCreateDialog v-model="dialogVisible" @created="onTasksCreated" />
    <PlatformLoginDrawer v-model:visible="platformDrawerVisible" />
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

/* ── Hero ── */
.hero {
  background: var(--color-primary-light);
  border-radius: var(--radius-lg);
  padding: var(--space-8) var(--space-6);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
}
.hero-title {
  font-size: var(--fs-2xl);
  font-weight: 600;
  margin: 0 0 var(--space-2) 0;
  color: var(--color-text);
}
.hero-subtitle {
  margin: 0;
  color: var(--color-text-regular);
  font-size: var(--fs-sm);
}
.hero-cta {
  flex-shrink: 0;
}

.key-banner { border-radius: var(--radius-md); }

/* ── Section card ── */
.section-card { background: var(--color-bg); }
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-4);
}
.section-title {
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--color-text);
  margin: 0;
}
.section-footer {
  margin-top: var(--space-3);
  display: flex;
  justify-content: flex-end;
}

.main-row { margin: 0 !important; }

/* ── In-progress task ── */
.empty-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-8) 0;
  text-align: center;
}
.in-progress-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.ip-task-row {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.ip-task-row:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-subtle);
}
.ip-thumb-placeholder {
  width: 120px;
  height: 68px;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, var(--color-bg-soft), var(--color-border));
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  flex-shrink: 0;
}
.ip-body { flex: 1; display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; }
.ip-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
}
.ip-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}
.ip-stepper { margin-top: var(--space-1); }
.ip-step-labels { display: flex; justify-content: space-between; margin-top: var(--space-1); }
.ip-step-labels .step-label { flex: 1; }
.ip-progress-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.ip-progress-row .el-progress { flex: 1; }

/* ── Platform card ── */
.platform-mini-list { display: flex; flex-direction: column; gap: var(--space-3); }
.platform-mini {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color 0.2s;
}
.platform-mini:hover { border-color: var(--color-primary); }
.platform-mini.not-logged { border-color: var(--color-danger); background: rgba(239, 68, 68, 0.04); }
.pm-left { display: flex; align-items: center; gap: var(--space-3); }
.pm-logo {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: var(--color-primary);
  color: #fff;
  font-weight: 600;
  font-size: var(--fs-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.pm-info { display: flex; flex-direction: column; gap: 2px; }
.pm-name { font-size: var(--fs-sm); font-weight: 600; color: var(--color-text); }
.pm-user { font-size: var(--fs-xs); }
.is-success-text { color: var(--color-success); }
.is-danger-text { color: var(--color-danger); }
.is-warning-text { color: var(--color-warning); }

/* ── Completed ── */
.completed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--space-4);
}
.completed-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.completed-card:hover { border-color: var(--color-primary); box-shadow: var(--shadow-subtle); }
.cc-thumb {
  width: 100%;
  aspect-ratio: 16/9;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, var(--color-bg-soft), var(--color-border));
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
}
.cc-title {
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--color-text);
  line-height: 1.4;
  height: 2.8em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.cc-actions { display: flex; gap: var(--space-1); flex-wrap: wrap; }

/* ── Failed ── */
.failed-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
}
.failed-list { display: flex; flex-direction: column; gap: var(--space-2); }
.failed-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: rgba(239, 68, 68, 0.04);
  border-radius: var(--radius-sm);
}
.fr-body { flex: 1; min-width: 0; }
.fr-title { font-size: var(--fs-sm); font-weight: 500; color: var(--color-text); }
.fr-actions { flex-shrink: 0; }

/* ── Onboarding checklist ── */
.checklist {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.checklist-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) 0;
}
.cl-icon {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--fs-xs);
  font-weight: 600;
  flex-shrink: 0;
}
.cl-icon.is-done { background: var(--color-success); color: #fff; }
.cl-icon.is-todo { background: var(--color-bg-soft); color: var(--color-text-muted); border: 1px solid var(--color-border); }
.cl-label {
  flex: 1;
  font-size: var(--fs-sm);
  color: var(--color-text);
}
.cl-label.is-done-text {
  color: var(--color-text-muted);
  text-decoration: line-through;
}

/* ── Welcome modal ── */
.welcome-body { padding: 0 var(--space-2); }
.welcome-intro { font-size: var(--fs-sm); color: var(--color-text-regular); margin: 0 0 var(--space-4); }
.welcome-steps {
  margin: 0;
  padding-left: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.welcome-steps li { font-size: var(--fs-sm); }
.welcome-steps strong { color: var(--color-text); display: block; margin-bottom: var(--space-1); }
.welcome-steps p { margin: 0; }

/* ── Recommendation picks ── */
.picks-section { margin-bottom: var(--space-6); }
.picks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--space-3);
  margin-top: var(--space-3);
}
.pick-card {
  cursor: pointer; border-radius: var(--radius-md);
  overflow: hidden; background: var(--color-bg-page);
  transition: transform 0.15s;
}
.pick-card:hover { transform: translateY(-2px); }
.pick-thumb {
  width: 100%; aspect-ratio: 16/9; object-fit: cover;
  display: block;
}
.pick-thumb-placeholder {
  background: var(--color-bg); display: flex;
  align-items: center; justify-content: center;
  color: var(--color-text-placeholder);
}
.pick-body { padding: var(--space-2) var(--space-3); }
.pick-title {
  font-size: var(--fs-xs); font-weight: 500;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; margin-bottom: 2px;
}
.pick-channel { font-size: 11px; color: var(--color-text-placeholder); }
.pick-score {
  display: inline-block; margin-top: 4px; padding: 1px 8px;
  border-radius: var(--radius-sm); font-size: 11px; font-weight: 600;
  color: #fff;
}
.score-high { background: #22c55e; }
.score-mid  { background: #f59e0b; }
.score-low  { background: #ef4444; }
</style>
