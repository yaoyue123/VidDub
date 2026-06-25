<script setup lang="ts">
/**
 * Phase 7 F3: 发布历史查看页.
 *
 * 表格列出所有 publish_records 记录：
 *   - 过滤：平台 / 状态 / 视频ID
 *   - 操作：查看平台 URL / 重试失败记录
 */
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { publishApi, type PublishRecordOut, type PublishPlatformName } from '@/api'
import AiTitleSelector from '@/components/AiTitleSelector.vue'

const records = ref<PublishRecordOut[]>([])
const total = ref(0)
const loading = ref(false)

const platformFilter = ref<string>('')
const statusFilter = ref<string>('')
const videoIdFilter = ref<number | undefined>(undefined)

const pageSize = ref(20)
const currentPage = ref(1)

async function load() {
  loading.value = true
  try {
    const res = await publishApi.listRecords({
      platform: (platformFilter.value || undefined) as PublishPlatformName | undefined,
      status: statusFilter.value || undefined,
      video_id: videoIdFilter.value,
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value,
    })
    records.value = res.data.items
    total.value = res.data.total
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载发布记录失败')
  } finally {
    loading.value = false
  }
}

async function retry(rec: PublishRecordOut) {
  try {
    await ElMessageBox.confirm(
      `确认重试发布记录 #${rec.id} (${rec.platform})？`,
      '重试发布',
      { type: 'warning' },
    )
    const res = await publishApi.retryRecord(rec.id)
    if (res.data.status === 'published') {
      ElMessage.success('发布成功')
    } else {
      ElMessage.warning(`发布未成功：${res.data.error || '未知原因'}`)
    }
    await load()
  } catch (e: any) {
    if (e === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '重试失败')
  }
}

function statusTagType(s: string): 'success' | 'info' | 'warning' | 'danger' {
  switch (s) {
    case 'published': return 'success'
    case 'publishing': return 'warning'
    case 'pending': return 'info'
    case 'failed': return 'danger'
    default: return 'info'
  }
}

function statusLabel(s: string): string {
  const m: Record<string, string> = {
    published: '已发布',
    publishing: '发布中',
    pending: '待发布',
    failed: '失败',
  }
  return m[s] || s
}

function platformLabel(p: string): string {
  const labels: Record<string, string> = {
    douyin: '抖音',
    bilibili: '哔哩哔哩',
    ixigua: '西瓜视频',
  }
  return labels[p] || p
}

function openUrl(url: string | null | undefined) {
  if (url) window.open(url, '_blank', 'noopener')
}

function applyFilters() {
  currentPage.value = 1
  load()
}

// ── Phase 8 F4: 发布前 AI 标题预览/编辑 ──
const aiTitleVisible = ref(false)
const aiTitleVideoId = ref<number>(0)

function openAiTitleBeforePublish(videoId: number) {
  aiTitleVideoId.value = videoId
  aiTitleVisible.value = true
}

onMounted(() => {
  load()
})
</script>

<template>
  <div class="publish-history-view">
    <h2 class="page-title">发布历史</h2>

    <el-card shadow="never" style="margin-bottom: 16px">
      <el-row :gutter="16">
        <el-col :span="6">
          <el-select
            v-model="platformFilter"
            placeholder="平台"
            clearable
            style="width: 100%"
            @change="applyFilters"
          >
            <el-option label="全部平台" value="" />
            <el-option label="抖音" value="douyin" />
            <el-option label="哔哩哔哩" value="bilibili" />
            <el-option label="西瓜视频" value="ixigua" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-select
            v-model="statusFilter"
            placeholder="状态"
            clearable
            style="width: 100%"
            @change="applyFilters"
          >
            <el-option label="全部状态" value="" />
            <el-option label="已发布" value="published" />
            <el-option label="发布中" value="publishing" />
            <el-option label="失败" value="failed" />
            <el-option label="待发布" value="pending" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-input-number
            v-model="videoIdFilter"
            placeholder="视频 ID"
            :min="1"
            :controls="false"
            style="width: 100%"
            @change="applyFilters"
          />
        </el-col>
        <el-col :span="6" style="text-align: right">
          <el-button @click="load">刷新</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never">
      <el-table :data="records" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="视频" width="100">
          <template #default="{ row }">
            <span>#{{ row.video_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平台" width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ platformLabel(row.platform) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
            <el-tag
              v-if="row.needs_relogin"
              type="danger"
              size="small"
              effect="dark"
              style="margin-left: 4px"
            >需重登</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标题" min-width="220">
          <template #default="{ row }">
            <span :title="row.title_used || ''">{{ row.title_used || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="标签" min-width="160">
          <template #default="{ row }">
            <span :title="row.tags_used || ''" class="cell-truncate">{{ row.tags_used || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平台 URL" min-width="200">
          <template #default="{ row }">
            <el-link
              v-if="row.platform_video_url"
              type="primary"
              :href="row.platform_video_url"
              target="_blank"
              :underline="false"
            >
              {{ row.platform_video_url }}
            </el-link>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="错误" min-width="180">
          <template #default="{ row }">
            <span v-if="row.error_msg" style="color: #f56c6c" :title="row.error_msg">
              {{ row.error_msg }}
            </span>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'failed'"
              text
              type="warning"
              size="small"
              @click="retry(row)"
            >重试</el-button>
            <el-button
              text
              type="info"
              size="small"
              @click="openAiTitleBeforePublish(row.video_id)"
            >AI 标题</el-button>
            <el-button
              v-if="row.platform_video_url"
              text
              type="primary"
              size="small"
              @click="openUrl(row.platform_video_url)"
            >打开</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="load"
          @size-change="load"
        />
      </div>
    </el-card>

    <!-- Phase 8 F4: 发布前 AI 标题/标签选择 -->
    <AiTitleSelector
      v-model:visible="aiTitleVisible"
      :video-id="aiTitleVideoId"
    />
  </div>
</template>

<style scoped>
.publish-history-view {
  max-width: 1400px;
}
.page-title {
  margin: 0 0 16px;
  font-size: 24px;
  font-weight: 600;
}
.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.cell-truncate {
  display: inline-block;
  max-width: 160px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}
</style>
