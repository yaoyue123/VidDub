<script setup lang="ts">
/**
 * Phase 9 F2: 频道管理 (D9-03, D9-07).
 *
 * - 表格列出所有频道（启用/扫描间隔/最近扫描时间）
 * - 新建/编辑/删除
 * - 立即扫描按钮
 * - 扫描日志抽屉
 */
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Delete, EditPen, View as ViewIcon } from '@element-plus/icons-vue'
import {
  channelApi,
  type ChannelItem,
  type ChannelSaveBody,
  type ScanLogItem,
} from '@/api'

const channels = ref<ChannelItem[]>([])
const loading = ref(false)

// 编辑/新建 dialog
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const form = ref<ChannelSaveBody>({
  name: '',
  url: '',
  enabled: true,
  scan_interval_hours: 6,
  filter_min_views: null,
  filter_max_duration_sec: null,
  filter_min_duration_sec: null,
  auto_publish: false,
})
const editingId = ref<number | null>(null)

// 扫描日志抽屉
const logsDrawerVisible = ref(false)
const logsChannelId = ref<number | null>(null)
const logsChannelName = ref('')
const scanLogs = ref<ScanLogItem[]>([])
const logsLoading = ref(false)

async function loadChannels() {
  loading.value = true
  try {
    const res = await channelApi.list()
    channels.value = res.data.items
  } catch (e: any) {
    ElMessage.error(e?.message || '加载频道失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  dialogMode.value = 'create'
  editingId.value = null
  form.value = {
    name: '', url: '', enabled: true, scan_interval_hours: 6,
    filter_min_views: null, filter_max_duration_sec: null,
    filter_min_duration_sec: null, auto_publish: false,
  }
  dialogVisible.value = true
}

function openEdit(row: ChannelItem) {
  dialogMode.value = 'edit'
  editingId.value = row.id
  form.value = {
    name: row.name, url: row.url, enabled: row.enabled,
    scan_interval_hours: row.scan_interval_hours,
    filter_min_views: row.filter_min_views ?? null,
    filter_max_duration_sec: row.filter_max_duration_sec ?? null,
    filter_min_duration_sec: row.filter_min_duration_sec ?? null,
    auto_publish: row.auto_publish,
  }
  dialogVisible.value = true
}

async function save() {
  if (!form.value.name || !form.value.url) {
    ElMessage.warning('名称和 URL 不能为空')
    return
  }
  try {
    if (dialogMode.value === 'create') {
      await channelApi.create(form.value)
      ElMessage.success('频道已添加')
    } else if (editingId.value !== null) {
      await channelApi.update(editingId.value, form.value)
      ElMessage.success('已更新')
    }
    dialogVisible.value = false
    await loadChannels()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  }
}

async function remove(row: ChannelItem) {
  try {
    await ElMessageBox.confirm(`确定删除频道「${row.name}」？`, '确认', { type: 'warning' })
    await channelApi.remove(row.id)
    ElMessage.success('已删除')
    await loadChannels()
  } catch (e: any) {
    if (e === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

async function scanNow(row: ChannelItem) {
  try {
    ElMessage.info(`正在扫描「${row.name}」...`)
    const res = await channelApi.scanNow(row.id)
    if (res.data.error_msg) {
      ElMessage.error(`扫描出错：${res.data.error_msg}`)
    } else {
      ElMessage.success(`扫描完成：发现 ${res.data.found_count}，新增 ${res.data.added_count}`)
    }
    await loadChannels()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '扫描失败')
  }
}

async function toggleEnabled(row: ChannelItem) {
  try {
    await channelApi.update(row.id, { enabled: !row.enabled })
    ElMessage.success(row.enabled ? '已禁用' : '已启用')
    await loadChannels()
  } catch (e: any) {
    ElMessage.error(e?.message || '切换失败')
  }
}

async function openLogs(row: ChannelItem) {
  logsChannelId.value = row.id
  logsChannelName.value = row.name
  logsDrawerVisible.value = true
  logsLoading.value = true
  try {
    const res = await channelApi.scanLogs(row.id, 50)
    scanLogs.value = res.data.items
  } catch (e: any) {
    ElMessage.error(e?.message || '加载日志失败')
  } finally {
    logsLoading.value = false
  }
}

function formatTime(s?: string | null): string {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN')
}

onMounted(() => {
  loadChannels()
})
</script>

<template>
  <div class="channels-view">
    <div class="header-row">
      <h2 class="page-title">频道管理</h2>
      <div>
        <el-button :icon="Refresh" @click="loadChannels">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">添加频道</el-button>
      </div>
    </div>

    <el-card shadow="never" v-loading="loading">
      <el-table :data="channels" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="名称" min-width="140">
          <template #default="{ row }">
            <span class="ch-name">{{ row.name }}</span>
            <div class="ch-url" :title="row.url">{{ row.url }}</div>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" @change="toggleEnabled(row)" />
          </template>
        </el-table-column>
        <el-table-column label="间隔(时)" width="100" prop="scan_interval_hours" />
        <el-table-column label="过滤" min-width="180">
          <template #default="{ row }">
            <div class="filter-cell">
              <span v-if="row.filter_min_views !== null && row.filter_min_views !== undefined">
                观看 ≥ {{ row.filter_min_views }}
              </span>
              <span v-if="row.filter_min_duration_sec !== null && row.filter_min_duration_sec !== undefined">
                时长 ≥ {{ row.filter_min_duration_sec }}s
              </span>
              <span v-if="row.filter_max_duration_sec !== null && row.filter_max_duration_sec !== undefined">
                ≤ {{ row.filter_max_duration_sec }}s
              </span>
              <span v-if="
                (row.filter_min_views === null || row.filter_min_views === undefined) &&
                (row.filter_min_duration_sec === null || row.filter_min_duration_sec === undefined) &&
                (row.filter_max_duration_sec === null || row.filter_max_duration_sec === undefined)
              ">
                -
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="自动发布" width="100">
          <template #default="{ row }">
            <el-tag :type="row.auto_publish ? 'success' : 'info'" size="small">
              {{ row.auto_publish ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近扫描" width="170">
          <template #default="{ row }">
            {{ formatTime(row.last_scanned_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="scanNow(row)">扫描</el-button>
            <el-button text size="small" :icon="ViewIcon" @click="openLogs(row)">日志</el-button>
            <el-button text type="warning" size="small" :icon="EditPen" @click="openEdit(row)">编辑</el-button>
            <el-button text type="danger" size="small" :icon="Delete" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建/编辑 dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '添加频道' : '编辑频道'"
      width="600"
    >
      <el-form :model="form" label-width="120px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="频道别名" />
        </el-form-item>
        <el-form-item label="频道 URL" required>
          <el-input v-model="form.url" placeholder="https://www.youtube.com/@handle" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="扫描间隔(小时)">
          <el-select v-model="form.scan_interval_hours" style="width: 100%">
            <el-option :value="1" label="每 1 小时" />
            <el-option :value="3" label="每 3 小时" />
            <el-option :value="6" label="每 6 小时（默认）" />
            <el-option :value="12" label="每 12 小时" />
            <el-option :value="24" label="每天" />
          </el-select>
        </el-form-item>
        <el-form-item label="最小观看数">
          <el-input-number v-model="form.filter_min_views" :min="0" :step="1000" controls-position="right" />
        </el-form-item>
        <el-form-item label="时长过滤(秒)">
          <div style="display:flex; gap:8px; align-items:center;">
            <el-input-number v-model="form.filter_min_duration_sec" :min="0" :step="30" controls-position="right" placeholder="最短" />
            <span>~</span>
            <el-input-number v-model="form.filter_max_duration_sec" :min="0" :step="60" controls-position="right" placeholder="最长" />
          </div>
        </el-form-item>
        <el-form-item label="自动发布">
          <el-switch v-model="form.auto_publish" />
          <span style="color:#909399; margin-left:8px;">扫描入库的视频配音完成后自动发布</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 扫描日志抽屉 -->
    <el-drawer
      v-model="logsDrawerVisible"
      :title="`扫描日志 - ${logsChannelName}`"
      size="500"
      direction="rtl"
    >
      <el-table :data="scanLogs" v-loading="logsLoading" stripe size="small">
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ formatTime(row.scanned_at) }}</template>
        </el-table-column>
        <el-table-column prop="found_count" label="发现" width="80" />
        <el-table-column prop="added_count" label="新增" width="80" />
        <el-table-column label="错误" min-width="200">
          <template #default="{ row }">
            <span :style="{ color: row.error_msg ? '#f56c6c' : '#909399' }">
              {{ row.error_msg || 'OK' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<style scoped>
.channels-view { max-width: 1400px; }
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}
.ch-name { font-weight: 500; }
.ch-url {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}
.filter-cell {
  display: flex;
  flex-direction: column;
  font-size: 11px;
  color: #606266;
}
.filter-cell span { white-space: nowrap; }
</style>
