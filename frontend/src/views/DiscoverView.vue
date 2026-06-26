<script setup lang="ts">
/**
 * Phase 16: DiscoverView — 智能选题推荐列表.
 *
 * Features:
 *   - Video card grid with composite scores
 *   - Rule selector to switch scoring strategies
 *   - Channel tracking sidebar
 *   - One-click dub from recommendations
 */
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { configApi, type ConfigItem } from '@/api'
import api from '@/api'

interface ScoredVideo {
  youtube_id: string
  title: string
  channel_name: string
  thumbnail_url: string
  composite_score: number
  virality_score: number
  translation_score: number
  quality_score: number
  market_score: number
  cost_score: number
  category: string | null
  view_count: number
  like_count: number
  duration_sec: number
  rationale: string
  source: string
}

interface RuleItem {
  id: number
  name: string
  enabled: boolean
  is_template: boolean
  weights: Record<string, number>
  conditions: any[]
}

interface ChannelItem {
  id: number
  label: string
  source_value: string
  last_scanned_at: string | null
}

const loading = ref(false)
const videos = ref<ScoredVideo[]>([])
const rules = ref<RuleItem[]>([])
const activeRuleId = ref<number | null>(null)
const channels = ref<ChannelItem[]>([])
const detailVideo = ref<ScoredVideo | null>(null)
const showDetail = ref(false)
const dubbing = ref<string | null>(null)

const categories: Record<string, string> = {
  tech: '科技', education: '教育', science: '科普', gaming: '游戏',
  music: '音乐', fitness: '健身', entertainment: '娱乐',
  comedy: '喜剧', news: '新闻', lifestyle: '生活', other: '其他',
}

function formatViews(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function scoreColor(s: number): string {
  if (s >= 80) return '#22c55e'
  if (s >= 60) return '#f59e0b'
  return '#ef4444'
}

function categoryLabel(cat: string | null): string {
  return categories[cat || ''] || cat || '未知'
}

async function fetchVideos() {
  loading.value = true
  try {
    // Auto-discover: first call seeds sources + fetches trending + scores all
    const res = await api.get('/scoring/discover', { params: { limit: 40 } })
    videos.value = (res.data.items || []).sort(
      (a: any, b: any) => b.composite_score - a.composite_score,
    )
    videoSource.value = res.data.source || 'cache'
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '发现失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

const videoSource = ref<string>('cache')

async function fetchRules() {
  try {
    const res = await api.get('/rules')
    rules.value = (res.data.items || []).filter((r: RuleItem) => r.enabled)
    if (rules.value.length > 0 && !activeRuleId.value) {
      activeRuleId.value = rules.value[0].id
    }
  } catch {
    // Rules not yet seeded — no worries
  }
}

async function fetchChannels() {
  try {
    const res = await api.get('/discovery/channels')
    channels.value = res.data.items || []
  } catch {
    // Discovery not configured yet
  }
}

async function evaluateRule() {
  if (!activeRuleId.value) return
  loading.value = true
  try {
    const res = await api.post(`/rules/${activeRuleId.value}/evaluate`, null, {
      params: { limit: 50 },
    })
    videos.value = res.data.matches || []
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '规则评估失败')
  } finally {
    loading.value = false
  }
}

async function dubVideo(video: ScoredVideo) {
  dubbing.value = video.youtube_id
  try {
    const youtubeUrl = `https://www.youtube.com/watch?v=${video.youtube_id}`
    const res = await api.post('/dub', { youtube_url: youtubeUrl })
    ElMessage.success(`已创建配音任务: ${video.title.slice(0, 40)}`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建任务失败')
  } finally {
    dubbing.value = null
  }
}

function openDetail(video: ScoredVideo) {
  detailVideo.value = video
  showDetail.value = true
}

onMounted(() => {
  fetchVideos()
  fetchRules()
  fetchChannels()
})
</script>

<template>
  <div class="discover-view">
    <!-- Top bar -->
    <div class="page-header">
      <h1 class="page-title">智能发现</h1>
      <div class="header-actions">
        <span v-if="videoSource === 'fresh'" class="source-tag">实时数据</span>
        <span v-else-if="videoSource === 'cache'" class="source-tag source-cache">缓存</span>
        <el-select
          v-model="activeRuleId"
          placeholder="选择评分策略"
          style="width: 200px; margin: 0 12px"
          @change="evaluateRule"
        >
          <el-option
            v-for="r in rules"
            :key="r.id"
            :label="r.name + (r.is_template ? ' (模板)' : '')"
            :value="r.id"
          />
        </el-select>
        <el-button :icon="Refresh" @click="fetchVideos" :loading="loading">
          发现新视频
        </el-button>
      </div>
    </div>

    <div class="discover-layout">
      <!-- Main video grid -->
      <div class="video-grid" v-loading="loading">
        <el-empty v-if="!loading && videos.length === 0"
          description="还没有评分数据。添加扫描源或先给一些视频打分。">
          <el-button type="primary" @click="$router.push('/settings')">
            前往设置
          </el-button>
        </el-empty>

        <div
          v-for="v in videos"
          :key="v.youtube_id"
          class="video-card y2b-card y2b-card-pad"
          @click="openDetail(v)"
        >
          <div class="card-thumb">
            <img
              v-if="v.thumbnail_url"
              :src="v.thumbnail_url"
              :alt="v.title"
              loading="lazy"
            />
            <div v-else class="thumb-placeholder">
              <el-icon :size="32"><VideoPlay /></el-icon>
            </div>
            <span class="duration-badge">{{ formatDuration(v.duration_sec) }}</span>
            <span
              class="score-badge"
              :style="{ background: scoreColor(v.composite_score) }"
            >
              {{ v.composite_score.toFixed(0) }}
            </span>
          </div>

          <div class="card-body">
            <h3 class="card-title">{{ v.title }}</h3>
            <p class="card-channel">{{ v.channel_name }}</p>
            <div class="card-meta">
              <span>{{ formatViews(v.view_count || 0) }} 观看</span>
              <el-tag size="small" type="info">{{ categoryLabel(v.category) }}</el-tag>
            </div>
            <p v-if="v.rationale" class="card-rationale">{{ v.rationale }}</p>
            <el-button
              size="small"
              type="primary"
              :icon="Plus"
              :loading="dubbing === v.youtube_id"
              @click.stop="dubVideo(v)"
              style="margin-top: 8px; width: 100%"
            >
              加入配音
            </el-button>
          </div>
        </div>
      </div>

      <!-- Right sidebar: channels -->
      <aside class="discover-sidebar">
        <div class="sidebar-card y2b-card y2b-card-pad">
          <h3 class="sidebar-title">追踪频道</h3>
          <el-empty
            v-if="channels.length === 0"
            description="暂无追踪频道"
            :image-size="48"
          />
          <div v-for="ch in channels" :key="ch.id" class="channel-row">
            <span class="channel-name">{{ ch.label }}</span>
            <span class="channel-time">
              {{ ch.last_scanned_at ? '已扫描' : '未扫描' }}
            </span>
          </div>
        </div>

        <div class="sidebar-card y2b-card y2b-card-pad" style="margin-top: 16px">
          <h3 class="sidebar-title">评分维度说明</h3>
          <div class="dim-legend">
            <div class="dim-row">
              <span class="dim-dot" style="background:#f43f5e"></span> 传播潜力 (30%)
            </div>
            <div class="dim-row">
              <span class="dim-dot" style="background:#8b5cf6"></span> 翻译适配 (25%)
            </div>
            <div class="dim-row">
              <span class="dim-dot" style="background:#3b82f6"></span> 内容质量 (20%)
            </div>
            <div class="dim-row">
              <span class="dim-dot" style="background:#f59e0b"></span> 市场潜力 (15%)
            </div>
            <div class="dim-row">
              <span class="dim-dot" style="background:#22c55e"></span> 制作成本 (10%)
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- Score detail dialog -->
    <el-dialog v-model="showDetail" title="评分详情" width="520px">
      <div v-if="detailVideo" class="score-detail">
        <img
          v-if="detailVideo.thumbnail_url"
          :src="detailVideo.thumbnail_url"
          style="width:100%;border-radius:8px;margin-bottom:12px"
        />
        <h3>{{ detailVideo.title }}</h3>
        <p style="color:var(--color-text-placeholder)">{{ detailVideo.channel_name }}</p>

        <div class="dim-bars" style="margin-top:16px">
          <div class="dim-bar-row" v-for="dim in [
            {key:'virality_score',label:'传播潜力',color:'#f43f5e'},
            {key:'translation_score',label:'翻译适配',color:'#8b5cf6'},
            {key:'quality_score',label:'内容质量',color:'#3b82f6'},
            {key:'market_score',label:'市场潜力',color:'#f59e0b'},
            {key:'cost_score',label:'制作成本',color:'#22c55e'},
          ]" :key="dim.key">
            <span class="dim-label">{{ dim.label }}</span>
            <div class="dim-track">
              <div
                class="dim-fill"
                :style="{
                  width: (detailVideo as any)[dim.key] + '%',
                  background: dim.color,
                }"
              ></div>
            </div>
            <span class="dim-value">{{ (detailVideo as any)[dim.key].toFixed(0) }}</span>
          </div>
        </div>

        <div style="margin-top:16px;text-align:center">
          <span style="font-size:24px;font-weight:700;color:var(--color-primary)">
            {{ detailVideo.composite_score.toFixed(0) }}
          </span>
          <span style="color:var(--color-text-placeholder)"> 综合分</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.discover-view {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-5);
}
.page-title { font-size: var(--fs-2xl); font-weight: 600; margin: 0; }
.header-actions { display: flex; align-items: center; }
.source-tag {
  font-size: var(--fs-xs); padding: 1px 10px; border-radius: var(--radius-sm);
  background: #dcfce7; color: #16a34a; font-weight: 500;
}
.source-cache { background: var(--color-bg-page); color: var(--color-text-placeholder); }

.discover-layout {
  display: flex;
  gap: var(--space-4);
}

.video-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: var(--space-4);
  align-content: start;
}

.video-card {
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  overflow: hidden;
  padding: 0;
}
.video-card:hover { transform: translateY(-2px); }

.card-thumb {
  position: relative;
  aspect-ratio: 16/9;
  background: var(--color-bg-page);
  overflow: hidden;
}
.card-thumb img { width: 100%; height: 100%; object-fit: cover; }
.thumb-placeholder {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  color: var(--color-text-placeholder);
}

.duration-badge {
  position: absolute; bottom: 4px; right: 4px;
  background: rgba(0,0,0,0.75); color: #fff;
  padding: 1px 6px; border-radius: 4px;
  font-size: var(--fs-xs);
}

.score-badge {
  position: absolute; top: 8px; right: 8px;
  color: #fff; width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%; font-weight: 700; font-size: var(--fs-sm);
}

.card-body { padding: var(--space-3); }
.card-title {
  font-size: var(--fs-sm); font-weight: 600;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; margin: 0 0 4px 0;
}
.card-channel { font-size: var(--fs-xs); color: var(--color-text-placeholder); margin: 0 0 4px 0; }
.card-rationale {
  font-size: 11px; color: var(--color-primary); margin: 4px 0;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-meta {
  display: flex; align-items: center; justify-content: space-between;
  font-size: var(--fs-xs); color: var(--color-text-regular);
}

.discover-sidebar { width: 240px; flex-shrink: 0; }
.sidebar-card { margin-bottom: 0; }
.sidebar-title { font-size: var(--fs-sm); font-weight: 600; margin: 0 0 8px 0; }
.channel-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 4px 0; font-size: var(--fs-xs);
}
.channel-name { color: var(--color-text); }
.channel-time { color: var(--color-text-placeholder); }

.dim-legend { display: flex; flex-direction: column; gap: 6px; font-size: var(--fs-xs); }
.dim-row { display: flex; align-items: center; gap: 6px; }
.dim-dot { width: 8px; height: 8px; border-radius: 50%; }

.score-detail h3 { margin: 0 0 4px 0; }
.dim-bars { display: flex; flex-direction: column; gap: 10px; }
.dim-bar-row { display: flex; align-items: center; gap: 8px; }
.dim-label { width: 70px; font-size: var(--fs-xs); text-align: right; flex-shrink: 0; }
.dim-track {
  flex: 1; height: 8px; background: var(--color-bg-page);
  border-radius: 4px; overflow: hidden;
}
.dim-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.dim-value { width: 30px; font-size: var(--fs-xs); font-weight: 600; text-align: right; }
</style>
