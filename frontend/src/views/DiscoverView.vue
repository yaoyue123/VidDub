<script setup lang="ts">
/**
 * DiscoverView.vue — Phase 10 rewrite + enhancements.
 *
 * Four tabs: Search (YouTube keyword search + filters + sort + save-as-source),
 * Keywords (keyword-type discovery source management),
 * Channels (channel-type discovery source management),
 * Scan Results (view DiscoveryResult video cards with source filter).
 *
 * Requirements: UI-01, UI-02, UI-03, UI-04
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Refresh, Search as SearchIcon, Delete, EditPen,
  SortUp, SortDown, Download,
} from '@element-plus/icons-vue'
import { useDiscoveryStore } from '@/stores/discoveryStore'
import VideoCard from '@/components/VideoCard.vue'
import type { DiscoverySourceItem, DiscoverySourceCreateBody, DiscoverySourceUpdateBody, DiscoveryItem, DiscoveryResultItem } from '@/api'

const store = useDiscoveryStore()
const router = useRouter()

// ── Tab state ──
const activeTab = ref<'search' | 'keywords' | 'channels' | 'results'>('search')

function onTabChange(tab: string) {
  store.setActiveTab(tab as any)
  if (tab === 'keywords' || tab === 'channels') {
    loadSources()
  } else if (tab === 'results') {
    loadResults()
  }
}

// ── Search tab state ──
const searchQuery = ref('')
const filterMinViews = ref<number | null>(null)
const filterMaxViews = ref<number | null>(null)
const filterMinDuration = ref<number | null>(null)
const filterMaxDuration = ref<number | null>(null)
const filterPublishedWithin = ref<number | null>(null)
const sortBy = ref<string>('relevance')
const sortOrder = ref<string>('desc')

async function doSearch() {
  if (!searchQuery.value.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  // Sync to store filters
  store.filters.minViews = filterMinViews.value
  store.filters.maxViews = filterMaxViews.value
  store.filters.minDuration = filterMinDuration.value
  store.filters.maxDuration = filterMaxDuration.value
  store.filters.publishedWithinHours = filterPublishedWithin.value
  store.filters.sortBy = sortBy.value
  store.filters.sortOrder = sortOrder.value
  await store.search(searchQuery.value, 20)
  if (store.error) {
    ElMessage.error(store.error)
  }
}

function toggleSortOrder() {
  sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
}

function clearResults() {
  store.clearSearch()
  searchQuery.value = ''
  filterMinViews.value = null
  filterMaxViews.value = null
  filterMinDuration.value = null
  filterMaxDuration.value = null
  filterPublishedWithin.value = null
}

// ── Save search as source ──
const saveSearchDialogVisible = ref(false)
const saveSearchForm = reactive({
  label: '',
  scan_interval_hours: 24,
})

function openSaveSearch() {
  saveSearchForm.label = searchQuery.value.trim()
  saveSearchDialogVisible.value = true
}

async function saveSearchAsSource() {
  if (!saveSearchForm.label.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  try {
    const { discoveryApi } = await import('@/api')
    await discoveryApi.createSource({
      type: 'keyword',
      source_value: searchQuery.value.trim(),
      label: saveSearchForm.label.trim(),
      scan_interval_hours: saveSearchForm.scan_interval_hours,
      max_results_per_scan: 20,
    })
    saveSearchDialogVisible.value = false
    ElMessage.success('已保存为关键词跟踪源')
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '保存失败'
    ElMessage.error(msg)
  }
}

// ── Source management state ──
const sourceDialogVisible = ref(false)
const sourceDialogMode = ref<'create' | 'edit'>('create')
const editingSourceId = ref<number | null>(null)
const sourceForm = reactive<{
  type: 'keyword' | 'channel'
  source_value: string
  label: string
  scan_interval_hours: number
  max_results_per_scan: number
  enabled: boolean
}>({
  type: 'keyword',
  source_value: '',
  label: '',
  scan_interval_hours: 24,
  max_results_per_scan: 20,
  enabled: true,
})

const keywordSources = computed(() =>
  store.sources.filter((s) => s.type === 'keyword'),
)
const channelSources = computed(() =>
  store.sources.filter((s) => s.type === 'channel'),
)

async function loadSources() {
  await store.fetchSources()
}

function openCreateSource(type: 'keyword' | 'channel') {
  sourceDialogMode.value = 'create'
  editingSourceId.value = null
  sourceForm.type = type
  sourceForm.source_value = ''
  sourceForm.label = ''
  sourceForm.scan_interval_hours = 24
  sourceForm.max_results_per_scan = 20
  sourceForm.enabled = true
  sourceDialogVisible.value = true
}

function openEditSource(source: DiscoverySourceItem) {
  sourceDialogMode.value = 'edit'
  editingSourceId.value = source.id
  sourceForm.type = source.type as 'keyword' | 'channel'
  sourceForm.source_value = source.source_value
  sourceForm.label = source.label
  sourceForm.scan_interval_hours = source.scan_interval_hours
  sourceForm.max_results_per_scan = source.max_results_per_scan
  sourceForm.enabled = source.enabled
  sourceDialogVisible.value = true
}

async function saveSource() {
  if (!sourceForm.label.trim() || !sourceForm.source_value.trim()) {
    ElMessage.warning('名称和值不能为空')
    return
  }
  try {
    if (sourceDialogMode.value === 'create') {
      const body: DiscoverySourceCreateBody = {
        type: sourceForm.type,
        source_value: sourceForm.source_value.trim(),
        label: sourceForm.label.trim(),
        scan_interval_hours: sourceForm.scan_interval_hours,
        max_results_per_scan: sourceForm.max_results_per_scan,
      }
      await store.addSource(body)
      ElMessage.success('跟踪源已添加')
    } else if (editingSourceId.value !== null) {
      const body: DiscoverySourceUpdateBody = {
        label: sourceForm.label.trim(),
        enabled: sourceForm.enabled,
        scan_interval_hours: sourceForm.scan_interval_hours,
        max_results_per_scan: sourceForm.max_results_per_scan,
      }
      await store.updateSource(editingSourceId.value, body)
      ElMessage.success('跟踪源已更新')
    }
    sourceDialogVisible.value = false
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '保存失败'
    ElMessage.error(msg)
  }
}

async function deleteSource(source: DiscoverySourceItem) {
  try {
    await ElMessageBox.confirm(
      `确定删除跟踪源「${source.label}」？`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await store.removeSource(source.id)
    ElMessage.success('已删除')
  } catch (e: any) {
    if (e === 'cancel') return
    const msg = e?.response?.data?.detail || e?.message || '删除失败'
    ElMessage.error(msg)
  }
}

async function toggleEnabled(source: DiscoverySourceItem) {
  try {
    await store.updateSource(source.id, { enabled: !source.enabled })
    ElMessage.success(source.enabled ? '已禁用' : '已启用')
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '操作失败'
    ElMessage.error(msg)
  }
}

async function scanSource(source: DiscoverySourceItem) {
  ElMessage.info(`正在扫描「${source.label}」...`)
  try {
    await store.triggerScan(source.id)
    ElMessage.success('扫描已触发，可在「扫描结果」标签查看')
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '扫描失败'
    ElMessage.error(msg)
  }
}

// ── Scan Results tab state ──
const resultsSourceFilter = ref<number | null>(null)
const scanResultsLoading = ref(false)

/** Map DiscoveryResultItem to DiscoveryItem for VideoCard compatibility */
function resultToDiscoveryItem(r: DiscoveryResultItem): DiscoveryItem {
  return {
    youtube_id: r.youtube_id,
    title: r.title,
    channel: r.channel_name,
    duration: r.duration_sec ?? 0,
    view_count: r.view_count ?? 0,
    like_count: r.like_count ?? 0,
    thumbnail_url: r.thumbnail_url ?? '',
    youtube_url: `https://www.youtube.com/watch?v=${r.youtube_id}`,
  }
}

async function loadResults() {
  scanResultsLoading.value = true
  try {
    await store.fetchResults({ source_id: resultsSourceFilter.value ?? undefined })
  } finally {
    scanResultsLoading.value = false
  }
}

// ── Add-to-pipeline (UI-03) ──
async function addToPipeline(video: any) {
  try {
    const youtubeUrl = video.youtube_url || `https://www.youtube.com/watch?v=${video.youtube_id}`
    await store.addToPipeline(youtubeUrl)
    ElMessage.success(`已创建搬运任务: ${(video.title || '').slice(0, 40)}`)
    router.push('/tasks')
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '创建任务失败'
    ElMessage.error(msg)
  }
}

// ── Formatting helpers ──
function formatTime(s?: string | null): string {
  if (!s) return '-'
  try {
    return new Date(s).toLocaleString('zh-CN')
  } catch {
    return s
  }
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    new: '新发现', scored: '已评分', dubbed: '已搬运', ignored: '已忽略',
  }
  return map[status] || status
}

function statusType(status: string): 'success' | 'info' | 'warning' | 'danger' | '' {
  const map: Record<string, 'success' | 'info' | 'warning' | 'danger' | ''> = {
    new: 'info', scored: '', dubbed: 'success', ignored: 'info',
  }
  return map[status] || 'info'
}

onMounted(() => {
  loadSources()
})
</script>

<template>
  <div class="discover-view">
    <!-- Page header -->
    <div class="page-header">
      <h1 class="page-title">内容发现</h1>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="loadSources">刷新</el-button>
      </div>
    </div>

    <!-- Tabs -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="搜索" name="search" />
      <el-tab-pane label="关键词跟踪" name="keywords" />
      <el-tab-pane label="频道跟踪" name="channels" />
      <el-tab-pane label="扫描结果" name="results" />
    </el-tabs>

    <!-- ─── Search Tab ─── -->
    <div v-if="activeTab === 'search'" class="search-tab">
      <!-- Search bar -->
      <div class="search-bar">
        <el-input
          v-model="searchQuery"
          placeholder="搜索 YouTube 视频..."
          prefix-icon="Search"
          clearable
          @keyup.enter="doSearch"
        >
          <template #prefix>
            <el-icon><SearchIcon /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" :loading="store.searchLoading" @click="doSearch">
          搜索
        </el-button>
        <el-button v-if="store.searchResults.length > 0 || store.error" @click="clearResults">
          清空
        </el-button>
        <el-button
          v-if="store.searchResults.length > 0"
          type="success"
          :icon="Download"
          @click="openSaveSearch"
        >
          保存为跟踪源
        </el-button>
      </div>

      <!-- Sort + Filter bar -->
      <div class="filter-bar">
        <div class="filter-item">
          <label class="filter-label">排序</label>
          <el-select v-model="sortBy" style="width: 110px" size="small">
            <el-option value="relevance" label="相关性" />
            <el-option value="views" label="播放量" />
            <el-option value="duration" label="时长" />
            <el-option value="date" label="发布日期" />
          </el-select>
          <el-button
            :icon="sortOrder === 'desc' ? SortDown : SortUp"
            size="small"
            @click="toggleSortOrder"
          />
        </div>
        <div class="filter-item">
          <label class="filter-label">最少播放</label>
          <el-input-number
            v-model="filterMinViews"
            :min="0"
            :step="10000"
            controls-position="right"
            placeholder="0"
            size="small"
          />
        </div>
        <div class="filter-item">
          <label class="filter-label">最多播放</label>
          <el-input-number
            v-model="filterMaxViews"
            :min="0"
            :step="100000"
            controls-position="right"
            placeholder="不限"
            size="small"
          />
        </div>
        <div class="filter-item">
          <label class="filter-label">最短(秒)</label>
          <el-input-number
            v-model="filterMinDuration"
            :min="0"
            :step="60"
            controls-position="right"
            placeholder="0"
            size="small"
          />
        </div>
        <div class="filter-item">
          <label class="filter-label">最长(秒)</label>
          <el-input-number
            v-model="filterMaxDuration"
            :min="0"
            :step="60"
            controls-position="right"
            placeholder="不限"
            size="small"
          />
        </div>
        <div class="filter-item">
          <label class="filter-label">发布时间</label>
          <el-select v-model="filterPublishedWithin" placeholder="不限" size="small" style="width: 100px" clearable>
            <el-option :value="24" label="24小时" />
            <el-option :value="72" label="3天" />
            <el-option :value="168" label="一周" />
            <el-option :value="720" label="一月" />
          </el-select>
        </div>
      </div>

      <!-- Error state -->
      <el-alert
        v-if="store.error && store.searchResults.length === 0"
        :title="store.error"
        type="error"
        show-icon
        closable
        style="margin-bottom: var(--space-4)"
      >
        <template #title>
          <span>{{ store.error }}</span>
          <el-button text size="small" type="primary" @click="doSearch" style="margin-left: 8px;">
            重试
          </el-button>
        </template>
      </el-alert>

      <!-- Loading state -->
      <div v-loading="store.searchLoading" class="video-grid-container">
        <!-- Empty state -->
        <el-empty
          v-if="!store.searchLoading && store.searchResults.length === 0"
          description="输入关键词搜索 YouTube 视频"
        />

        <!-- Results grid -->
        <div v-else-if="store.searchResults.length > 0" class="video-grid">
          <VideoCard
            v-for="v in store.searchResults"
            :key="v.youtube_id"
            :video="v"
            @add-to-pipeline="addToPipeline(v)"
          />
        </div>
      </div>
    </div>

    <!-- ─── Keywords Tab ─── -->
    <div v-if="activeTab === 'keywords'" class="source-tab">
      <div class="section-header">
        <h2 class="section-title">关键词跟踪源</h2>
        <el-button type="primary" :icon="Plus" @click="openCreateSource('keyword')">
          添加关键词
        </el-button>
      </div>

      <!-- Error state -->
      <el-alert
        v-if="store.error && keywordSources.length === 0"
        :title="store.error"
        type="error"
        show-icon
        closable
        style="margin-bottom: var(--space-4)"
      />

      <!-- Loading + list -->
      <div v-loading="store.loading" class="source-list">
        <el-empty
          v-if="!store.loading && keywordSources.length === 0"
          description="暂无跟踪关键词"
        />

        <el-table v-else :data="keywordSources" stripe style="width: 100%">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column label="名称" min-width="140">
            <template #default="{ row }">
              <span class="source-label">{{ row.label }}</span>
              <div class="source-value" :title="row.source_value">{{ row.source_value }}</div>
            </template>
          </el-table-column>
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled" @change="toggleEnabled(row)" />
            </template>
          </el-table-column>
          <el-table-column label="间隔(时)" width="100" prop="scan_interval_hours" />
          <el-table-column label="每次最多" width="100" prop="max_results_per_scan" />
          <el-table-column label="最近扫描" width="170">
            <template #default="{ row }">
              {{ formatTime(row.last_scanned_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="scanSource(row)">扫描</el-button>
              <el-button text type="warning" size="small" :icon="EditPen" @click="openEditSource(row)">编辑</el-button>
              <el-button text type="danger" size="small" :icon="Delete" @click="deleteSource(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- ─── Channels Tab ─── -->
    <div v-if="activeTab === 'channels'" class="source-tab">
      <div class="section-header">
        <h2 class="section-title">频道跟踪源</h2>
        <el-button type="primary" :icon="Plus" @click="openCreateSource('channel')">
          添加频道
        </el-button>
      </div>

      <!-- Error state -->
      <el-alert
        v-if="store.error && channelSources.length === 0"
        :title="store.error"
        type="error"
        show-icon
        closable
        style="margin-bottom: var(--space-4)"
      />

      <!-- Loading + list -->
      <div v-loading="store.loading" class="source-list">
        <el-empty
          v-if="!store.loading && channelSources.length === 0"
          description="暂无跟踪频道"
        />

        <el-table v-else :data="channelSources" stripe style="width: 100%">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column label="名称" min-width="140">
            <template #default="{ row }">
              <span class="source-label">{{ row.label }}</span>
              <div class="source-value" :title="row.source_value">{{ row.source_value }}</div>
            </template>
          </el-table-column>
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled" @change="toggleEnabled(row)" />
            </template>
          </el-table-column>
          <el-table-column label="间隔(时)" width="100" prop="scan_interval_hours" />
          <el-table-column label="每次最多" width="100" prop="max_results_per_scan" />
          <el-table-column label="最近扫描" width="170">
            <template #default="{ row }">
              {{ formatTime(row.last_scanned_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="scanSource(row)">扫描</el-button>
              <el-button text type="warning" size="small" :icon="EditPen" @click="openEditSource(row)">编辑</el-button>
              <el-button text type="danger" size="small" :icon="Delete" @click="deleteSource(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- ─── Scan Results Tab ─── -->
    <div v-if="activeTab === 'results'" class="results-tab">

      <div class="section-header">
        <h2 class="section-title">扫描结果</h2>
        <div class="results-toolbar">
          <el-select
            v-model="resultsSourceFilter"
            placeholder="按跟踪源筛选"
            clearable
            size="small"
            style="width: 200px; margin-right: 8px"
            @change="loadResults"
          >
            <el-option
              v-for="s in store.sources"
              :key="s.id"
              :value="s.id"
              :label="`${s.label} (${s.type === 'keyword' ? '关键词' : '频道'})`"
            />
          </el-select>
          <el-button :icon="Refresh" size="small" @click="loadResults" :loading="scanResultsLoading">
            刷新
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="store.error && store.scanResults.length === 0"
        :title="store.error"
        type="error"
        show-icon
        closable
        style="margin-bottom: var(--space-4)"
      />

      <div v-loading="scanResultsLoading" class="video-grid-container">
        <el-empty
          v-if="!scanResultsLoading && store.scanResults.length === 0"
          description="暂无扫描结果，对跟踪源执行扫描后将在此显示"
        />

        <div v-else-if="store.scanResults.length > 0" class="video-grid">
          <div
            v-for="r in store.scanResults"
            :key="r.id"
            class="result-card-wrap"
          >
            <div class="result-header">
              <el-tag :type="statusType(r.status)" size="small" effect="plain">
                {{ statusLabel(r.status) }}
              </el-tag>
              <span class="result-source-label">
                {{ store.sources.find(s => s.id === r.source_id)?.label || `#${r.source_id}` }}
              </span>
            </div>
            <VideoCard
              :video="resultToDiscoveryItem(r)"
              @add-to-pipeline="addToPipeline(r)"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- ─── Source Dialog (create/edit) ─── -->
    <el-dialog
      v-model="sourceDialogVisible"
      :title="sourceDialogMode === 'create' ? '添加跟踪源' : '编辑跟踪源'"
      width="560"
      :close-on-click-modal="false"
    >
      <el-form :model="sourceForm" label-width="120px">
        <el-form-item label="类型" v-if="sourceDialogMode === 'create'">
          <el-select v-model="sourceForm.type" style="width: 100%">
            <el-option value="keyword" label="关键词" />
            <el-option value="channel" label="频道" />
          </el-select>
        </el-form-item>
        <el-form-item label="值" required>
          <el-input
            v-model="sourceForm.source_value"
            :placeholder="sourceForm.type === 'keyword' ? '搜索关键词' : 'YouTube 频道 URL'"
            :disabled="sourceDialogMode === 'edit'"
          />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="sourceForm.label" placeholder="便于识别的名称" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="sourceForm.enabled" />
        </el-form-item>
        <el-form-item label="扫描间隔">
          <el-select v-model="sourceForm.scan_interval_hours" style="width: 100%">
            <el-option :value="1" label="每 1 小时" />
            <el-option :value="3" label="每 3 小时" />
            <el-option :value="6" label="每 6 小时" />
            <el-option :value="12" label="每 12 小时" />
            <el-option :value="24" label="每天（默认）" />
          </el-select>
        </el-form-item>
        <el-form-item label="每次最大结果">
          <el-input-number v-model="sourceForm.max_results_per_scan" :min="5" :max="50" :step="5" controls-position="right" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sourceDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveSource">保存</el-button>
      </template>
    </el-dialog>

    <!-- ─── Save Search Dialog ─── -->
    <el-dialog
      v-model="saveSearchDialogVisible"
      title="保存搜索为跟踪源"
      width="480"
      :close-on-click-modal="false"
    >
      <el-form :model="saveSearchForm" label-width="100px">
        <el-form-item label="搜索关键词">
          <el-input :model-value="searchQuery" disabled />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="saveSearchForm.label" placeholder="便于识别的名称" />
        </el-form-item>
        <el-form-item label="扫描间隔">
          <el-select v-model="saveSearchForm.scan_interval_hours" style="width: 100%">
            <el-option :value="1" label="每 1 小时" />
            <el-option :value="3" label="每 3 小时" />
            <el-option :value="6" label="每 6 小时" />
            <el-option :value="12" label="每 12 小时" />
            <el-option :value="24" label="每天（默认）" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveSearchDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveSearchAsSource">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.discover-view {
  max-width: 1200px;
  margin: 0 auto;
}

/* ── Page header ── */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-5);
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

/* ── Search tab ── */
.search-bar {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.search-bar .el-input {
  flex: 1;
}

.filter-bar {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
  padding: var(--space-3);
  background: var(--color-bg-soft);
  border-radius: var(--radius-md);
}
.filter-row {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
  align-items: center;
}
.filter-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.filter-label {
  font-size: var(--fs-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
}
.filter-item .el-input-number {
  width: 120px;
}

.video-grid-container {
  min-height: 200px;
}
.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: var(--space-4);
}

/* ── Source tabs ── */
.source-tab {
  margin-top: var(--space-4);
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-3);
}
.section-title {
  font-size: var(--fs-lg);
  font-weight: 600;
  margin: 0;
}

.source-list {
  min-height: 120px;
}
.source-label {
  font-weight: 500;
}
.source-value {
  font-size: var(--fs-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

/* ── Results tab ── */
.results-tab {
  margin-top: var(--space-4);
}
.results-toolbar {
  display: flex;
  align-items: center;
}
.result-card-wrap {
  display: flex;
  flex-direction: column;
}
.result-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
  padding: 0 4px;
}
.result-source-label {
  font-size: var(--fs-2xs);
  color: var(--color-text-muted);
}
</style>
